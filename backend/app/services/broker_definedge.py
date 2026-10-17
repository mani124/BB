"""Definedge Securities (Integrate API) adapter.

Endpoints and enums follow the vendor's open-source ``pyintegrate`` client (v3.0.0): base
``https://integrate.definedgesecurities.com/dart/v1/``, the session key goes in the ``Authorization`` header,
``POST placeorder``, ``GET cancel/{id}``, ``GET orders``, ``GET order/{id}``, ``GET positions``, ``GET limits``.
The response field names of order and position rows are not documented in that client, so they are read
through alias lists (``_pick``). Verify them with a dry run before enabling live (see docs/LIVE_ROUTING.md).

Credentials: the API token and secret come from the environment (``DEFINEDGE_API_TOKEN`` / ``DEFINEDGE_API_SECRET``),
the one-time 6-digit TOTP is typed into the dashboard, and the resulting session key lives in memory only.
Nothing here writes a credential to disk or to a log.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import logging
import os
import time
import zipfile
from datetime import date, datetime
from typing import Any, Optional

import httpx

from app.services.broker_adapter import (
    CANCELED, COMPLETE, NEW, OPEN, REJECTED, UNKNOWN, BrokerAuthExpired, BrokerError, BrokerNotSent,
    BrokerRejected, BrokerTimeout, Contract, OrderRequest, OrderResult,
)

logger = logging.getLogger(__name__)


class _HideLoginUrls(logging.Filter):
    """httpx logs each request URL at INFO, and the login URL carries the API token in its path."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "debroking/dsbpkc" not in record.getMessage()


logging.getLogger("httpx").addFilter(_HideLoginUrls())

BASE_URL = "https://integrate.definedgesecurities.com/dart/v1/"
LOGIN_URL = "https://signin.definedgesecurities.com/auth/realms/debroking/dsbpkc/"
MASTER_URL = "https://app.definedgesecurities.com/public/allmaster.zip"
OPTION_SEGMENTS = ("NFO", "BFO")
_EXPIRY_FORMATS = ("%d%m%Y", "%d-%b-%Y", "%d%b%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d%b%y", "%d-%b-%y")

_STATUS_MAP = {
    "NEW": NEW, "PENDING": OPEN, "OPEN": OPEN, "TRIGGER PENDING": OPEN, "PARTIALLY FILLED": OPEN, "REPLACED": OPEN,
    "COMPLETE": COMPLETE, "COMPLETED": COMPLETE, "TRADED": COMPLETE, "FILLED": COMPLETE,
    "CANCELED": CANCELED, "CANCELLED": CANCELED, "REJECTED": REJECTED,
}


def _pick(row: dict, *keys: str, default: Any = None) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = lowered.get(k.lower())
        if v not in (None, ""):
            return v
    return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows(payload: Any, *list_keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in list_keys + ("data", "result"):
            v = payload.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def parse_expiry(text: str) -> Optional[date]:
    s = str(text or "").strip()
    for fmt in _EXPIRY_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_order_row(row: dict) -> OrderResult:
    raw_status = str(_pick(row, "order_status", "status", "orderstatus", default="")).strip().upper()
    status = _STATUS_MAP.get(raw_status, UNKNOWN)
    filled = int(_num(_pick(row, "filled_qty", "filledqty", "fillshares", "traded_qty", "executed_qty"), 0))
    qty = int(_num(_pick(row, "quantity", "qty", "order_qty"), 0))
    if status == OPEN and filled > 0 and qty and filled >= qty:
        status = COMPLETE
    return OrderResult(
        broker_order_id=str(_pick(row, "order_id", "orderid", "norenordno", "id", default="")),
        status=status, filled_qty=filled,
        avg_price=_num(_pick(row, "average_traded_price", "avg_price", "average_price", "avgprc", "avg_traded_price"), 0.0),
        message=str(_pick(row, "message", "reason", "rejection_reason", "rejreason", default=""))[:300],
        raw={k: row[k] for k in list(row)[:40]},
    )


class MasterIndex:
    """Option rows of Definedge's public instrument master, keyed for exact lookup."""

    def __init__(self) -> None:
        self.rows: dict[tuple, Contract] = {}
        self.loaded_on: Optional[date] = None

    def load_csv(self, text: str) -> int:
        self.rows = {}
        for line in csv.reader(io.StringIO(text)):
            try:
                segment, symbol, trading_symbol = line[0].strip(), line[2].strip().upper(), line[3].strip()
                opt = line[8].strip().upper()
                if segment not in OPTION_SEGMENTS or opt not in ("CE", "PE"):
                    continue
                expiry = parse_expiry(line[5])
                strike = int(line[9]) / (int(line[11]) * 10 ** int(line[10]))
                if expiry is None:
                    continue
                lot = int(float(line[7]))
                self.rows[(segment, symbol, expiry, int(round(strike)), opt)] = Contract(segment, trading_symbol, lot)
            except (IndexError, ValueError, ZeroDivisionError):
                continue
        self.loaded_on = date.today()
        return len(self.rows)

    def find(self, segment: str, underlying: str, expiry: date, strike: float, option_type: str) -> Optional[Contract]:
        return self.rows.get((segment, underlying.upper(), expiry, int(round(strike)), option_type.upper()))


class DefinedgeBroker:
    name = "definedge"

    def __init__(self, data_dir: Optional[str] = None, timeout: float = 10.0, min_spacing: float = 0.2) -> None:
        self._data_dir = data_dir
        self._timeout = timeout
        self._min_spacing = min_spacing
        self._last = 0.0
        self._pace: Optional[asyncio.Lock] = None  # created lazily inside the running loop
        self._client: Optional[httpx.AsyncClient] = None
        self._session_key: str = ""
        self._uid = ""
        self._master = MasterIndex()
        self.master_loader = self._download_master  # replaced in tests

    # ---------------------------------------------------------------- session
    def has_session(self) -> bool:
        return bool(self._session_key)

    def clear_session(self) -> None:
        self._session_key = ""

    def masked_account(self) -> str:
        return (self._uid[:2] + "***") if self._uid else ""

    async def login(self, totp: str) -> None:
        """Exchange the API token/secret (environment) and a fresh TOTP for a session key kept in memory."""
        token = os.getenv("DEFINEDGE_API_TOKEN", "").strip()
        secret = os.getenv("DEFINEDGE_API_SECRET", "").strip()
        if not token or not secret:
            raise BrokerError("DEFINEDGE_API_TOKEN and DEFINEDGE_API_SECRET are not set on the server.")
        totp = (totp or "").strip()
        if not (totp.isdigit() and len(totp) == 6):
            raise BrokerError("Enter the 6-digit TOTP.")
        try:
            first = await self._http("GET", f"{LOGIN_URL}login/{token}", headers={"api_secret": secret}, auth=False)
            otp_token = str(first["otp_token"])
            ac = hashlib.sha256(f"{otp_token}{totp}{secret}".encode()).hexdigest()
            data = await self._http("POST", f"{LOGIN_URL}token", json={"otp_token": otp_token, "otp": totp, "ac": ac},
                                    auth=False)
            self._session_key = str(data["api_session_key"])
            self._uid = str(data.get("uid", ""))
        except (KeyError, TypeError):
            raise BrokerError("Definedge login failed: unexpected response.") from None
        except BrokerTimeout:
            raise BrokerError("Definedge login timed out.") from None

    async def verify_session(self) -> None:
        if not self._session_key:
            raise BrokerAuthExpired("No Definedge session. Log in first.")
        await self._http("GET", BASE_URL + "limits")

    # ---------------------------------------------------------------- http
    async def _http(self, method: str, url: str, *, json: Any = None, headers: Optional[dict] = None,
                    auth: bool = True) -> Any:
        if self._pace is None:
            self._pace = asyncio.Lock()
        async with self._pace:
            wait = self._min_spacing - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        hdrs = dict(headers or {})
        if auth:
            if not self._session_key:
                raise BrokerAuthExpired("No Definedge session. Log in first.")
            hdrs["Authorization"] = self._session_key
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, connect=5.0))
        try:
            resp = await self._client.request(method, url, json=json, headers=hdrs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise BrokerNotSent(f"could not connect: {type(exc).__name__}") from None
        except httpx.RequestError as exc:
            raise BrokerTimeout(f"no answer: {type(exc).__name__}") from None
        if resp.status_code in (401, 403):
            self._session_key = ""
            raise BrokerAuthExpired(f"HTTP {resp.status_code}: session rejected")
        try:
            data = resp.json()
        except ValueError:
            raise BrokerTimeout(f"unreadable answer (HTTP {resp.status_code})") from None
        if isinstance(data, dict) and str(data.get("status", "")).upper() == "ERROR":
            msg = str(data.get("message", ""))[:300]
            if "session expired" in msg.lower():
                self._session_key = ""
                raise BrokerAuthExpired(msg)
            raise BrokerRejected(msg or "broker returned ERROR")
        if resp.status_code >= 500:
            raise BrokerTimeout(f"HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise BrokerRejected(f"HTTP {resp.status_code}")
        return data

    # ---------------------------------------------------------------- contracts
    async def _download_master(self) -> str:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.get(MASTER_URL)
            r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            return z.read("allmaster.csv").decode("utf-8", "replace")

    async def resolve_contract(self, *, underlying: str, expiry: str, strike: float, option_type: str,
                               segment: str) -> Contract:
        exp = parse_expiry(expiry)
        if exp is None:
            raise BrokerError(f"unreadable expiry {expiry!r}")
        if self._master.loaded_on != date.today() or not self._master.rows:
            try:
                text = await self.master_loader()
            except Exception as exc:
                raise BrokerError(f"instrument master unavailable: {type(exc).__name__}") from None
            if self._master.load_csv(text) == 0:
                raise BrokerError("instrument master has no option rows")
        found = self._master.find(segment, underlying, exp, strike, option_type)
        if found is None:
            raise BrokerError(f"no contract for {underlying} {exp} {int(strike)} {option_type} on {segment}")
        return found

    # ---------------------------------------------------------------- orders
    async def place_order(self, req: OrderRequest) -> OrderResult:
        body = {
            "exchange": req.contract.exchange, "order_type": req.side, "price": req.price if req.order_type == "LIMIT" else 0,
            "price_type": req.order_type, "product_type": req.product, "quantity": req.quantity,
            "tradingsymbol": req.contract.trading_symbol, "algo_id": req.algo_id, "validity": req.validity,
            "remarks": req.tag,
        }
        data = await self._http("POST", BASE_URL + "placeorder", json=body)
        oid = str(_pick(data, "order_id", "orderid", "norenordno", default="")) if isinstance(data, dict) else ""
        if not oid:
            # The broker answered without an order id: we cannot say whether it is working.
            raise BrokerTimeout("placeorder answered without an order id")
        return OrderResult(broker_order_id=oid, status=NEW, message=str(_pick(data, "message", default=""))[:300])

    async def get_order(self, broker_order_id: str) -> OrderResult:
        data = await self._http("GET", BASE_URL + f"order/{broker_order_id}")
        row = data if isinstance(data, dict) and not _rows(data, "orders") else (_rows(data, "orders") or [{}])[0]
        res = parse_order_row(row)
        res.broker_order_id = res.broker_order_id or broker_order_id
        return res

    async def find_order_by_tag(self, tag: str) -> Optional[OrderResult]:
        data = await self._http("GET", BASE_URL + "orders")
        for row in _rows(data, "orders"):
            if str(_pick(row, "remarks", "remark", default="")) == tag:
                return parse_order_row(row)
        return None

    async def cancel_order(self, broker_order_id: str) -> None:
        await self._http("GET", BASE_URL + f"cancel/{broker_order_id}")

    async def net_positions(self) -> dict[str, int]:
        data = await self._http("GET", BASE_URL + "positions")
        out: dict[str, int] = {}
        for row in _rows(data, "positions"):
            sym = str(_pick(row, "tradingsymbol", "trading_symbol", "tsym", default="")).strip()
            if not sym:
                continue
            net = _pick(row, "net_quantity", "netqty", "net_qty", "quantity")
            if net is None:
                net = _num(_pick(row, "buy_quantity", "buyqty", default=0)) - _num(_pick(row, "sell_quantity", "sellqty", default=0))
            out[sym] = out.get(sym, 0) + int(_num(net))
        return out

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
