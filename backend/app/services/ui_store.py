"""Server-side dashboard layouts (Dockview workspaces) and their snapshots.

Own tables, created additively with IF NOT EXISTS, so the trading engine and its migrations are untouched. A layout is
just JSON the browser owns; the server validates size and names only.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.services import db, market_hours

MAX_BODY_BYTES = 256 * 1024
MAX_SNAPSHOTS = 20
SNAPSHOT_GAP_S = 60
NAME_RE = re.compile(r"^[A-Za-z0-9 :_.\-]{1,80}$")


class UiStoreError(Exception):
    """Raised with an HTTP-ish status so the API layer can map it."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now() -> str:
    return market_hours.now_ist().isoformat()


def kind_of(name: str) -> str:
    return "workspace" if name.startswith("workspace:") else "custom"


def validate_name(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise UiStoreError(422, "Layout names use letters, digits, spaces and : _ . - only (80 characters at most).")
    if not (name.startswith("workspace:") or name.startswith("custom:")):
        raise UiStoreError(422, "Layout names start with 'workspace:' or 'custom:'.")


class UiStore:
    def __init__(self, db_path: str, snapshot_gap_s: float = SNAPSHOT_GAP_S):
        self.db_path = db_path
        self.snapshot_gap_s = snapshot_gap_s
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = db.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ui_layouts (
                    name TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ui_layout_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    body TEXT NOT NULL,
                    taken_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ui_snap_name ON ui_layout_snapshots(name, id);
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return {
            "name": row["name"], "kind": row["kind"], "schema_version": row["schema_version"],
            "body": json.loads(row["body"]), "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ui_layouts ORDER BY name;").fetchall()
        out = []
        for r in rows:
            try:
                out.append(self._row(r))
            except (ValueError, TypeError):
                continue  # a damaged row must not hide the others
        return out

    def get(self, name: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM ui_layouts WHERE name = ?;", (name,)).fetchone()
        return self._row(row) if row else None

    def _snapshot(self, conn: sqlite3.Connection, name: str, body: str, force: bool = False) -> None:
        last = conn.execute("SELECT taken_at FROM ui_layout_snapshots WHERE name = ? ORDER BY id DESC LIMIT 1;", (name,)).fetchone()
        if last and not force and self.snapshot_gap_s > 0:
            try:
                age = (market_hours.now_ist() - datetime.fromisoformat(last["taken_at"])).total_seconds()
                if age < self.snapshot_gap_s:
                    return
            except ValueError:
                pass
        conn.execute("INSERT INTO ui_layout_snapshots (name, body, taken_at) VALUES (?, ?, ?);", (name, body, _now()))
        conn.execute(
            "DELETE FROM ui_layout_snapshots WHERE name = ? AND id NOT IN "
            "(SELECT id FROM ui_layout_snapshots WHERE name = ? ORDER BY id DESC LIMIT ?);",
            (name, name, MAX_SNAPSHOTS),
        )

    def put(self, name: str, body: dict, schema_version: int) -> dict:
        validate_name(name)
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise UiStoreError(422, "schema_version must be an integer.")
        text = json.dumps(body, separators=(",", ":"), allow_nan=False)
        if len(text.encode()) > MAX_BODY_BYTES:
            raise UiStoreError(413, "Layout is larger than 256 KB.")
        with self._conn() as conn:
            prev = conn.execute("SELECT body FROM ui_layouts WHERE name = ?;", (name,)).fetchone()
            if prev and prev["body"] != text:
                self._snapshot(conn, name, prev["body"])  # the state before this edit, at most once per gap
            conn.execute(
                "INSERT INTO ui_layouts (name, kind, schema_version, body, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET kind = excluded.kind, schema_version = excluded.schema_version, "
                "body = excluded.body, updated_at = excluded.updated_at;",
                (name, kind_of(name), schema_version, text, _now()),
            )
        return self.get(name)  # type: ignore[return-value]

    def delete(self, name: str) -> bool:
        validate_name(name)
        if kind_of(name) != "custom":
            raise UiStoreError(403, "Built-in workspaces cannot be deleted; reset them instead.")
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM ui_layouts WHERE name = ?;", (name,))
            conn.execute("DELETE FROM ui_layout_snapshots WHERE name = ?;", (name,))
        return cur.rowcount > 0

    def snapshots(self, name: str) -> list[dict]:
        validate_name(name)
        with self._conn() as conn:
            rows = conn.execute("SELECT id, taken_at FROM ui_layout_snapshots WHERE name = ? ORDER BY id DESC;", (name,)).fetchall()
        return [{"id": r["id"], "taken_at": r["taken_at"]} for r in rows]

    def restore(self, name: str, snapshot_id: int) -> dict:
        validate_name(name)
        with self._conn() as conn:
            snap = conn.execute("SELECT body FROM ui_layout_snapshots WHERE id = ? AND name = ?;", (snapshot_id, name)).fetchone()
            if not snap:
                raise UiStoreError(404, "Snapshot not found.")
            cur = conn.execute("SELECT body, schema_version FROM ui_layouts WHERE name = ?;", (name,)).fetchone()
            if cur:
                self._snapshot(conn, name, cur["body"], force=True)  # the state being replaced is kept
            version = cur["schema_version"] if cur else json.loads(snap["body"]).get("schema_version", 1)
            conn.execute(
                "INSERT INTO ui_layouts (name, kind, schema_version, body, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at;",
                (name, kind_of(name), int(version) if isinstance(version, int) else 1, snap["body"], _now()),
            )
        return self.get(name)  # type: ignore[return-value]
