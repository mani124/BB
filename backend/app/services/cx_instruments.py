"""Underlyings of the Commodities & Currency book and how to find their live contracts.

MCX and currency options are written on a futures contract (CRUDEOIL, GOLDM, USDINR ...), not on an index, and that
contract rolls every month. The ids and lot sizes are therefore read from Dhan's public instrument master, never
hardcoded; ``nearest_futures`` picks the live contracts and ``ContractResolver`` caches the answer for the day.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from app.services import exchange_sessions as xs
from app.services import market_hours

logger = logging.getLogger(__name__)

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"


@dataclass(frozen=True)
class CxUnderlying:
    symbol: str          # name used in the master (UNDERLYING_SYMBOL) and on the dashboard
    exchange: str        # exchange_sessions.MCX or CURRENCY
    segment: str         # Dhan ExchangeSegment of the future and its options
    fut_type: str        # master INSTRUMENT of the future
    opt_type: str        # master INSTRUMENT of the options
    master_exch: str     # master EXCH_ID
    pool: str            # loss-cap pool: "commodity" or "currency"
    label: str
    price_unit: str      # what an option premium / future price is quoted in
    default_lot: int     # used only when the master gives no lot size; entries are refused if lot_size_known is False
    quote_unit: int = 1  # contract units covered by one quoted price: GOLDM is quoted per 10 g but a lot is 100 g, so 10

    def pnl_multiplier(self, lot_size: int) -> float:
        """Rupees of P&L per 1.0 of premium move for one lot."""
        return lot_size / max(1, self.quote_unit)


UNDERLYINGS: dict[str, CxUnderlying] = {
    "CRUDEOIL": CxUnderlying("CRUDEOIL", xs.MCX, "MCX_COMM", "FUTCOM", "OPTFUT", "MCX", "commodity", "Crude oil", "INR/bbl", 100),
    "GOLDM": CxUnderlying("GOLDM", xs.MCX, "MCX_COMM", "FUTCOM", "OPTFUT", "MCX", "commodity", "Gold mini", "INR/10g", 100, quote_unit=10),
    "USDINR": CxUnderlying("USDINR", xs.CURRENCY, "NSE_CURRENCY", "FUTCUR", "OPTCUR", "NSE", "currency", "USD / INR", "INR/USD", 1000),
}
POOLS = ("commodity", "currency")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_master(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def nearest_futures(rows: list[dict], symbol: str, today: Optional[date] = None, limit: int = 3) -> list[dict]:
    """Live futures of ``symbol`` (expiry today or later), earliest first, as plain dicts."""
    u = UNDERLYINGS[symbol]
    today = today or market_hours.now_ist().date()
    found: list[tuple[date, dict]] = []
    for r in rows:
        if r.get("INSTRUMENT") != u.fut_type or r.get("EXCH_ID") != u.master_exch:
            continue
        if (r.get("UNDERLYING_SYMBOL") or "").strip().upper() != symbol:
            continue
        exp = _parse_date(r.get("SM_EXPIRY_DATE") or "")
        if exp is None or exp < today:
            continue
        found.append((exp, r))
    found.sort(key=lambda x: x[0])
    out = []
    for exp, r in found[:limit]:
        lot = int(_num(r.get("LOT_SIZE"), 0))
        out.append({"symbol": symbol, "security_id": str(r["SECURITY_ID"]).strip(), "expiry": exp.isoformat(),
                    "lot_size": lot if lot > 0 else u.default_lot, "lot_size_known": lot > 0,
                    "display": (r.get("DISPLAY_NAME") or r.get("SYMBOL_NAME") or "").strip()})
    return out


class ContractResolver:
    """Resolves each underlying to its live futures, cached in a small JSON file and refreshed once per day."""

    def __init__(self, cache_path: str, fetch_master=None):
        self.cache_path = cache_path
        self._fetch_master = fetch_master or self._download
        self._cache: dict = {}
        try:
            with open(cache_path) as f:
                self._cache = json.load(f)
        except (OSError, ValueError):
            self._cache = {}

    @staticmethod
    async def _download() -> str:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as c:
            resp = await c.get(MASTER_URL)
            resp.raise_for_status()
            return resp.text

    def cached(self, symbol: str) -> list[dict]:
        return list(self._cache.get("contracts", {}).get(symbol, []))

    async def resolve(self, symbols: list[str], today: Optional[date] = None) -> dict[str, list[dict]]:
        today = today or market_hours.now_ist().date()
        stale = [s for s in symbols if self._cache.get("day") != today.isoformat() or not self.cached(s)
                 or _parse_date(self.cached(s)[0]["expiry"]) < today]
        if stale:
            try:
                rows = parse_master(await self._fetch_master())
                contracts = dict(self._cache.get("contracts", {})) if self._cache.get("day") == today.isoformat() else {}
                for s in stale:
                    contracts[s] = nearest_futures(rows, s, today)
                self._cache = {"day": today.isoformat(), "contracts": contracts}
                tmp = self.cache_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(self._cache, f)
                os.replace(tmp, self.cache_path)
            except Exception:
                logger.warning("instrument master refresh failed; using the cached contracts", exc_info=True)
        return {s: self.cached(s) for s in symbols}
