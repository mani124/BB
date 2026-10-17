"""Per-trade journal notes and tags, kept in their own table next to the trades.

Separate from ``positions`` on purpose: the table is created additively (IF NOT EXISTS), so the
paper-trading engine and its migrations are untouched and a reset never loses what was written.
"""
import sqlite3
from contextlib import contextmanager
from typing import Optional

from app.services import market_hours
from app.services import db

MAX_NOTE_LEN = 1000
MAX_TAG_LEN = 40


class JournalStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = db.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commit / rollback
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_journal (
                    position_id TEXT PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    tag TEXT NOT NULL DEFAULT '',
                    updated_at TEXT
                );
                """
            )
            conn.commit()

    def save(self, position_id: str, note: Optional[str], tag: Optional[str]) -> dict:
        """Upsert; a blank note and tag removes the entry."""
        note = (note or "").strip()
        tag = (tag or "").strip()
        with self._conn() as conn:
            if not note and not tag:
                conn.execute("DELETE FROM trade_journal WHERE position_id = ?;", (position_id,))
            else:
                conn.execute(
                    "INSERT INTO trade_journal (position_id, note, tag, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(position_id) DO UPDATE SET note = excluded.note, tag = excluded.tag, "
                    "updated_at = excluded.updated_at;",
                    (position_id, note, tag, market_hours.now_ist().isoformat()),
                )
            conn.commit()
        return {"position_id": position_id, "note": note, "tag": tag}

    def load_all(self) -> dict[str, dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT position_id, note, tag FROM trade_journal;").fetchall()
        return {r["position_id"]: {"note": r["note"], "tag": r["tag"]} for r in rows}
