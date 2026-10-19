"""Additive, source-scoped snapshots of evidence recorded when a trade opens."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from app.services import db

BOOKS = {"paper", "cx", "earnings"}


def _db_path(book: str) -> str | None:
    if book == "paper":
        from app.services.paper_trader import paper_trader
        return paper_trader.storage.db_path if paper_trader.storage else None
    if book == "cx":
        from app.services.cx_registry import get_engine
        return get_engine().store.db_path
    from app.services.earnings_registry import get_engine
    return get_engine().store.db_path


def _epoch_ist(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    stamp = datetime.fromisoformat(str(value))
    if stamp.tzinfo:
        from zoneinfo import ZoneInfo
        stamp = stamp.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    return int((stamp - datetime(1970, 1, 1)).total_seconds())


def _bars(raw: dict[str, list[dict]]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for name, rows in raw.items():
        seen: dict[int, dict] = {}
        for row in rows:
            try:
                stamp = _epoch_ist(row.get("time", row.get("timestamp")))
                candle = {"time": stamp, **{k: float(row[k]) for k in ("open", "high", "low", "close")}}
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if candle["low"] <= min(candle["open"], candle["close"]) <= candle["high"] and candle["low"] <= max(candle["open"], candle["close"]):
                seen[stamp] = candle
        result[name] = [seen[t] for t in sorted(seen)]
    return result


def _connection(path: str) -> sqlite3.Connection:
    connection = db.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS dashboard_trade_evidence (
        book TEXT NOT NULL, position_id TEXT NOT NULL, decision_json TEXT NOT NULL, bars_json TEXT NOT NULL,
        PRIMARY KEY(book, position_id))""")
    return connection


def save_trade_evidence(book: str, position_id: str, decision: dict, bars: dict[str, list[dict]],
                        *, db_path: str | None = None) -> None:
    if book not in BOOKS:
        raise ValueError(f"Unknown dashboard book: {book}")
    path = db_path or _db_path(book)
    if not path:
        return
    with _connection(path) as connection:
        prior = connection.execute("SELECT decision_json, bars_json FROM dashboard_trade_evidence WHERE book=? AND position_id=?",
                                   (book, position_id)).fetchone()
        saved_decision = json.loads(prior["decision_json"]) if prior else None
        saved_bars = json.loads(prior["bars_json"]) if prior else {}
        for name, rows in _bars(bars).items():
            saved_bars[name] = _bars({name: [*saved_bars.get(name, []), *rows]})[name]
        connection.execute("""INSERT INTO dashboard_trade_evidence(book, position_id, decision_json, bars_json)
            VALUES(?,?,?,?) ON CONFLICT(book,position_id) DO UPDATE SET
            decision_json=excluded.decision_json, bars_json=excluded.bars_json""",
            (book, position_id, json.dumps(saved_decision or decision, default=str), json.dumps(saved_bars)))


def get_trade_evidence(book: str, position_id: str) -> dict | None:
    if book not in BOOKS:
        return None
    path = _db_path(book)
    if not path:
        return None
    with _connection(path) as connection:
        row = connection.execute("SELECT decision_json, bars_json FROM dashboard_trade_evidence WHERE book=? AND position_id=?",
                                 (book, position_id)).fetchone()
    if not row:
        return None
    return {"decision": json.loads(row["decision_json"]), "bars": json.loads(row["bars_json"])}


def evidence_ids(book: str) -> set[str]:
    """Fetch IDs in one read so listing many trades avoids one query per row."""
    if book not in BOOKS:
        return set()
    try:
        path = _db_path(book)
        if not path:
            return set()
        with _connection(path) as connection:
            return {row["position_id"] for row in connection.execute(
                "SELECT position_id FROM dashboard_trade_evidence WHERE book=?", (book,))}
    except (RuntimeError, sqlite3.Error):
        return set()
