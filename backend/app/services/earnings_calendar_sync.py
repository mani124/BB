"""Earnings calendar from the NSE event calendar (public JSON used by nseindia.com).

NSE lists board meetings with the purpose "Financial Results" and the meeting date. It does not say whether the
result is released before the open or after the close, so synced rows have no session: they follow the
`earnings_default_session` setting until you set a session on the row.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com/"
NSE_EVENTS = "https://www.nseindia.com/api/event-calendar"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
}


async def fetch_nse_events(timeout: float = 25.0) -> list[dict]:
    """Raw event-calendar rows. Raises httpx.HTTPError / ValueError when NSE refuses or returns something unexpected."""
    async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout, follow_redirects=True) as c:
        try:
            await c.get(NSE_HOME)  # sets the cookies NSE likes to see; a refusal here is not fatal
        except httpx.HTTPError:
            pass
        r = await c.get(NSE_EVENTS)
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, list):
        raise ValueError("unexpected NSE response shape")
    return data


def parse_results_rows(events: list[dict], universe: set[str], today: date, horizon_days: int) -> list[dict]:
    """Financial-result board meetings for F&O stocks between today and today + horizon_days."""
    out: dict[tuple[str, str], dict] = {}
    for e in events:
        purpose = str(e.get("purpose", "")).lower()
        sym = str(e.get("symbol", "")).strip().upper()
        if "financial results" not in purpose or sym not in universe:
            continue
        try:
            d = datetime.strptime(str(e.get("date", "")).strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        if d < today or (d - today).days > horizon_days:
            continue
        out[(sym, d.isoformat())] = {"symbol": sym, "earnings_date": d.isoformat(), "note": str(e.get("purpose", ""))[:120]}
    return sorted(out.values(), key=lambda r: (r["earnings_date"], r["symbol"]))
