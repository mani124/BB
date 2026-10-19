"""Read-only check: does this Dhan account return MCX commodity and NSE currency data?

Run on a market day (MCX 09:00-23:30 IST, currency 09:00-17:00 IST), from the VM or any machine:

    python3 check_mcx_currency_data.py --ws        (self-contained; needs httpx and websockets, e.g. the app venv)

The Dhan client id and access token come from DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN or a hidden prompt; they are never printed or written. The script places no
orders; it only downloads the public instrument master and calls Dhan's read endpoints (expiry list,
option chain, quote, intraday candles, optionally one WebSocket tick). It prints PASS / FAIL / SKIP per
capability per underlying and exits 1 if anything FAILed.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
API_BASE = "https://api.dhan.co/v2"

# underlying symbol -> (future instrument type, option instrument type, Dhan segment string, exchange id)
UNDERLYINGS: dict[str, tuple[str, str, str, str]] = {
    "CRUDEOIL": ("FUTCOM", "OPTFUT", "MCX_COMM", "MCX"),
    "GOLDM": ("FUTCOM", "OPTFUT", "MCX_COMM", "MCX"),
    "USDINR": ("FUTCUR", "OPTCUR", "NSE_CURRENCY", "NSE"),
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _matches(r: dict, symbol: str, exchange: str) -> bool:
    """Same matching as app/services/cx_instruments.py: MCX needs the exact underlying (CRUDEOIL is not CRUDEOILM);
    currency also accepts a symbol or display name that starts with the pair."""
    if _key(r.get("UNDERLYING_SYMBOL")) == symbol:
        return True
    return exchange == "NSE" and any(_key(r.get(c)).startswith(symbol) for c in ("SYMBOL_NAME", "DISPLAY_NAME", "UNDERLYING_SYMBOL"))


def nearest_futures(rows: list[dict], symbol: str, today: Optional[datetime] = None, limit: int = 2) -> list[dict]:
    """Futures of `symbol` expiring AFTER today (one expiring today is already rolled past), earliest first."""
    fut_type, _opt_type, _seg, exch = UNDERLYINGS[symbol]
    today = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    found: list[tuple[datetime, dict]] = []
    for r in rows:
        if (r.get("INSTRUMENT") or "").strip().upper() != fut_type:
            continue
        if (r.get("EXCH_ID") or "").strip().upper() not in ("", exch):
            continue
        if not _matches(r, symbol, exch):
            continue
        exp = _parse_date(r.get("SM_EXPIRY_DATE") or "")
        if exp is None or exp <= today:
            continue
        found.append((exp, r))
    found.sort(key=lambda x: x[0])
    return [{"security_id": str(r["SECURITY_ID"]).strip(), "lot_size": int(_num(r.get("LOT_SIZE"), 0)),
             "expiry": exp.strftime("%Y-%m-%d"), "display": (r.get("DISPLAY_NAME") or r.get("SYMBOL_NAME") or "").strip()}
            for exp, r in found[:limit]]


def diagnose_missing(rows: list[dict], symbol: str) -> list[str]:
    """Why no future was found: what the master holds for this symbol and instrument type."""
    fut_type, _o, _s, exch = UNDERLYINGS[symbol]
    out = []
    by_type: dict[tuple, int] = {}
    for r in rows:
        if _key(symbol) in (_key(r.get("UNDERLYING_SYMBOL")), _key(r.get("SYMBOL_NAME"))[:len(symbol)], _key(r.get("DISPLAY_NAME"))[:len(symbol)]):
            k = (r.get("EXCH_ID"), r.get("SEGMENT"), r.get("INSTRUMENT"))
            by_type[k] = by_type.get(k, 0) + 1
    out.append(f"rows mentioning {symbol} by (EXCH_ID, SEGMENT, INSTRUMENT): {by_type or 'none'}")
    futs = [r for r in rows if (r.get("INSTRUMENT") or "").strip().upper() == fut_type][:3]
    for r in futs:
        out.append("sample " + fut_type + " row: " + json.dumps({k: r.get(k) for k in ("EXCH_ID", "SEGMENT", "SECURITY_ID", "INSTRUMENT", "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME", "SM_EXPIRY_DATE", "LOT_SIZE")}))
    if not futs:
        types = sorted({(r.get("INSTRUMENT") or "") for r in rows})[:40]
        out.append(f"no {fut_type} rows at all; INSTRUMENT values in the file: {types}")
    return out


def summarize_chain(chain: dict) -> dict:
    """Quality summary of an /optionchain `oc` mapping (strike -> {ce, pe})."""
    strikes = len(chain)
    legs = [leg for row in chain.values() if isinstance(row, dict) for leg in (row.get("ce"), row.get("pe")) if isinstance(leg, dict)]
    with_quote = sum(1 for leg in legs if _num(leg.get("last_price")) > 0)
    with_bidask = sum(1 for leg in legs if _num(leg.get("top_bid_price")) > 0 and _num(leg.get("top_ask_price")) > 0)
    with_greeks = sum(1 for leg in legs if isinstance(leg.get("greeks"), dict) and leg["greeks"].get("delta") not in (None, 0))
    with_oi = sum(1 for leg in legs if _num(leg.get("oi")) > 0)
    return {"strikes": strikes, "legs": len(legs), "with_price": with_quote, "with_bid_ask": with_bidask,
            "with_greeks": with_greeks, "with_oi": with_oi}


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, symbol: str, check: str, status: str, detail: str = "") -> None:
        self.items.append({"symbol": symbol, "check": check, "status": status, "detail": detail})
        print(f"[{status:4}] {symbol:9} {check:16} {detail}")

    @property
    def failed(self) -> bool:
        return any(i["status"] == "FAIL" for i in self.items)


async def _post(client: httpx.AsyncClient, headers: dict, path: str, body: dict) -> tuple[int, Any]:
    await asyncio.sleep(1.1)  # stay well under Dhan's per-second limits
    resp = await client.post(path, headers=headers, json=body)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text[:200]


def parity_atm(chain: dict) -> Optional[float]:
    """Strike where the call and put last prices are closest: the chain's own at-the-money forward."""
    best, gap = None, None
    for k, row in chain.items():
        ce, pe = (row.get("ce") or {}), (row.get("pe") or {})
        if _num(ce.get("last_price")) > 0 and _num(pe.get("last_price")) > 0:
            g = abs(_num(ce["last_price"]) - _num(pe["last_price"]))
            if gap is None or g < gap:
                best, gap = _num(k), g
    return best


async def check_symbol(client: httpx.AsyncClient, headers: dict, rep: Report, symbol: str, fut: dict, with_ws: bool,
                       client_id: str, token: str, tag: str = "") -> None:
    _fut_type, _opt_type, seg, _exch = UNDERLYINGS[symbol]
    sec_id = fut["security_id"]
    rep.add(symbol, "instrument" + tag, "PASS", f"{fut['display']} id={sec_id} lot={fut['lot_size']} expiry={fut['expiry']}")
    if fut["lot_size"] <= 0:
        rep.add(symbol, "lot size", "FAIL", "lot size missing in master")

    # quote
    code, data = await _post(client, headers, "/marketfeed/quote", {seg: [int(sec_id)]})
    q = (data.get("data", {}).get(seg, {}).get(sec_id) if isinstance(data, dict) else None) or {}
    ltp = _num(q.get("last_price"))
    rep.add(symbol, "quote", "PASS" if code == 200 and ltp > 0 else "FAIL", f"http={code} ltp={ltp}")

    # expiry list + option chain (the underlying of an MCX / currency option is the future)
    code, data = await _post(client, headers, "/optionchain/expirylist", {"UnderlyingScrip": int(sec_id), "UnderlyingSeg": seg})
    expiries = data.get("data") if isinstance(data, dict) else None
    if code == 200 and expiries:
        rep.add(symbol, "expiry list", "PASS", f"{len(expiries)} expiries, first {expiries[0]}")
        code, data = await _post(client, headers, "/optionchain",
                                 {"UnderlyingScrip": int(sec_id), "UnderlyingSeg": seg, "Expiry": expiries[0]})
        oc = (data.get("data", {}) or {}).get("oc", {}) if isinstance(data, dict) else {}
        s = summarize_chain(oc) if isinstance(oc, dict) else {"strikes": 0}
        ok = code == 200 and s.get("strikes", 0) > 0 and s.get("with_price", 0) > 0
        rep.add(symbol, "option chain", "PASS" if ok else "FAIL", f"http={code} {s}")
        atm = parity_atm(oc) if isinstance(oc, dict) else None
        if ok and atm and ltp > 0:
            off = abs(atm - ltp) / ltp * 100
            rep.add(symbol, "chain vs future", "PASS" if off <= 3.0 else "FAIL",
                    f"future ltp {ltp}, chain parity ATM strike {atm} ({off:.2f}% apart): "
                    + ("this future is the chain's underlying" if off <= 3.0 else "this future is probably NOT the chain's underlying month"))
        if ok and s.get("with_greeks", 0) == 0:
            rep.add(symbol, "chain greeks", "FAIL", "no delta in chain (setups would use assumed delta)")
        elif ok:
            rep.add(symbol, "chain greeks", "PASS", f"{s['with_greeks']} legs with delta")
    else:
        rep.add(symbol, "expiry list", "FAIL", f"http={code} {str(data)[:120]}")
        rep.add(symbol, "option chain", "SKIP", "no expiry list")

    # intraday candles (5m, last 5 days)
    now = datetime.now()
    body = {"securityId": sec_id, "exchangeSegment": seg, "instrument": UNDERLYINGS[symbol][0], "interval": "5", "oi": False,
            "fromDate": (now - timedelta(days=5)).strftime("%Y-%m-%d 09:00:00"), "toDate": now.strftime("%Y-%m-%d %H:%M:%S")}
    code, data = await _post(client, headers, "/charts/intraday", body)
    n = len((data or {}).get("close", [])) if isinstance(data, dict) else 0
    first_ts = ((data or {}).get("start_Time") or (data or {}).get("timestamp") or [None])[0] if n else None
    rep.add(symbol, "5m candles", "PASS" if code == 200 and n >= 50 else "FAIL", f"http={code} bars={n} first_ts={first_ts}")

    if with_ws:
        await check_ws(rep, symbol, seg, sec_id, client_id, token)


async def check_ws(rep: Report, symbol: str, seg: str, sec_id: str, client_id: str, token: str) -> None:
    try:
        import websockets
    except ImportError:
        rep.add(symbol, "websocket", "SKIP", "websockets package missing")
        return
    url = f"wss://api-feed.dhan.co?version=2&token={token}&clientId={client_id}&authType=2"
    sub = {"RequestCode": 15, "InstrumentCount": 1, "InstrumentList": [{"ExchangeSegment": seg, "SecurityId": sec_id}]}
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            await ws.send(json.dumps(sub))
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            size = len(msg) if isinstance(msg, (bytes, str)) else 0
            rep.add(symbol, "websocket", "PASS" if size else "FAIL", f"first packet {size} bytes")
    except Exception as exc:  # noqa: BLE001 - report any failure, do not crash the check
        rep.add(symbol, "websocket", "FAIL", f"{type(exc).__name__}: {str(exc)[:100]} (no tick outside session hours is normal)")


async def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=list(UNDERLYINGS), help="default: %(default)s")
    ap.add_argument("--ws", action="store_true", help="also wait for one WebSocket packet per symbol")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON at the end")
    ap.add_argument("--master-file", help="use a local copy of the instrument master CSV instead of downloading")
    args = ap.parse_args(argv)

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    if (not client_id or not token) and sys.stdin.isatty():
        # The app never stores the Dhan token on the server (the browser sends it per request), so ask for it.
        import getpass
        client_id = client_id or input("Dhan client id: ").strip()
        token = token or getpass.getpass("Dhan access token (hidden): ").strip()
    if not client_id or not token:
        print("Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in the environment (they are never printed).", file=sys.stderr)
        return 2
    unknown = [s for s in args.symbols if s not in UNDERLYINGS]
    if unknown:
        print(f"Unknown symbols: {unknown}; known: {list(UNDERLYINGS)}", file=sys.stderr)
        return 2

    rep = Report()
    headers = {"client-id": client_id, "access-token": token, "Content-Type": "application/json", "Accept": "application/json"}
    async with httpx.AsyncClient(base_url=API_BASE, timeout=20.0) as client:
        try:
            if args.master_file:
                with open(args.master_file, newline="", encoding="utf-8") as fh:
                    text = fh.read()
            else:
                resp = await client.get(MASTER_URL, timeout=60.0)
                resp.raise_for_status()
                text = resp.text
            rows = list(csv.DictReader(io.StringIO(text)))
            rep.add("-", "instrument master", "PASS" if rows else "FAIL", f"{len(rows)} rows")
        except Exception as exc:  # noqa: BLE001
            rep.add("-", "instrument master", "FAIL", f"{type(exc).__name__}: {str(exc)[:100]}")
            rows = []
        for sym in args.symbols:
            futs = nearest_futures(rows, sym) if rows else []
            if not futs:
                rep.add(sym, "instrument", "FAIL", "no live future found in master")
                for line in diagnose_missing(rows, sym):
                    print("       " + line)
                continue
            for i, fut in enumerate(futs):
                await check_symbol(client, headers, rep, sym, fut, args.ws and i == 0, client_id, token, f" #{i + 1}")

    print("\nRESULT:", "FAIL (see FAIL lines above)" if rep.failed else "PASS")
    if args.json:
        print(json.dumps(rep.items, indent=2))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
