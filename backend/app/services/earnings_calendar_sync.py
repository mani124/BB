"""Earnings calendar from the NSE event calendar (public JSON used by nseindia.com).

NSE lists board meetings with the purpose "Financial Results" and the meeting date. It publishes no
before-open / after-close flag, so the session is inferred from any time of day or wording in the event
(`infer_session`). Rows where nothing usable is found stay empty and follow `earnings_default_session`
(default AMC). A session set by hand on a row always wins over both.
"""
from __future__ import annotations

import logging
import re
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


MARKET_OPEN_MIN = 9 * 60 + 15
# 14:30 style, or 2:30 pm / 2 pm; a bare "2.50" (a dividend, a ratio) is not a time.
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\s*(am|pm)?|\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b", re.I)
_TIME_KEYS = ("bm_timestamp", "broadcastDateTime", "time", "meetingTime", "bm_time", "bm_desc", "purpose", "attachment_text")


def infer_session(event: dict) -> str:
    """BMO / AMC from what NSE put in the event, '' when nothing usable.

    Wording ("before market", "post market") wins; otherwise a time of day in a timestamp or description: before
    09:15 IST is BMO, anything later is AMC (results released during or after a board meeting reach the market
    after the close at the earliest, so the safe reading is AMC)."""
    text = " ".join(str(event.get(k, "")) for k in _TIME_KEYS if event.get(k))
    low = text.lower()
    if re.search(r"before (the )?(market|open)|pre[- ]?market|prior to (market|open)", low):
        return "BMO"
    if re.search(r"after (the )?(market|close)|post[- ]?market", low):
        return "AMC"
    for m in _TIME_RE.finditer(text):
        if m.group(1) is not None:
            h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        else:
            h, mi, ap = int(m.group(4)), int(m.group(5) or 0), m.group(6).lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        if h > 23 or mi > 59:
            continue
        return "BMO" if h * 60 + mi < MARKET_OPEN_MIN else "AMC"
    return ""


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
        out[(sym, d.isoformat())] = {"symbol": sym, "earnings_date": d.isoformat(), "note": str(e.get("purpose", ""))[:120],
                                          "session": infer_session(e)}
    return sorted(out.values(), key=lambda r: (r["earnings_date"], r["symbol"]))
