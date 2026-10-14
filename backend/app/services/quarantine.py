"""P0-6: non-destructive quarantine of suspect historical paper-trade rows.

Rows are only ever *flagged* (positions.quarantine_reason); nothing is deleted. Flagged
rows stay visible but are excluded from performance totals. Clear flags with
``PaperStorage.clear_quarantine``.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from app.services import market_hours

OFF_SESSION_ENTRY = "OFF_SESSION_ENTRY"
STACKED_DUPLICATE = "STACKED_DUPLICATE"


def _dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=market_hours.IST)


def find_suspect_rows(db_path: str) -> dict[str, str]:
    """Return {position_id: reason} for rows that should be quarantined.

    - OFF_SESSION_ENTRY: entered on a weekend/holiday or outside 09:15-15:30 IST.
    - STACKED_DUPLICATE: opened while an earlier row on the same contract (option_security_id,
      else strike_symbol) was still open; the earliest row is kept, later overlaps are flagged.
    Rows already quarantined are skipped. Rows without an entry_datetime are skipped.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, strike_symbol, option_security_id, entry_datetime, exit_datetime, status "
            "FROM positions WHERE quarantine_reason IS NULL AND entry_datetime IS NOT NULL "
            "ORDER BY entry_datetime ASC;"
        ).fetchall()
    finally:
        conn.close()

    suspects: dict[str, str] = {}
    open_until: dict[str, Optional[datetime]] = {}  # contract -> exit of the last kept row (None = still open)
    for r in rows:
        entry = _dt(r["entry_datetime"])
        if entry is None:
            continue
        if not (market_hours.is_trading_day(entry.date())
                and market_hours.MARKET_OPEN <= entry.time() < market_hours.MARKET_CLOSE):
            suspects[r["id"]] = OFF_SESSION_ENTRY
            continue
        key = r["option_security_id"] or r["strike_symbol"]
        if not key:
            continue
        exit_dt = _dt(r["exit_datetime"]) if r["status"] not in ("OPEN", "TARGET_1") else None
        if key in open_until:
            prev_exit = open_until[key]
            if prev_exit is None or entry < prev_exit:
                suspects[r["id"]] = STACKED_DUPLICATE
                continue
        open_until[key] = exit_dt
    return suspects


def apply_quarantine(db_path: str, suspects: dict[str, str]) -> int:
    from app.services.paper_storage import PaperStorage
    storage = PaperStorage(db_path)
    total = 0
    for reason in sorted(set(suspects.values())):
        total += storage.set_quarantine([pid for pid, r in suspects.items() if r == reason], reason)
    return total
