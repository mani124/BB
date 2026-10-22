"""Audit trail of every state-changing request: who asked for what, and what happened. Never stores request bodies.

The table is created additively. A failed audit write is logged and swallowed: auditing must never change the outcome
of the action it records.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.services import db, market_hours

logger = logging.getLogger(__name__)

MUTATING = ("POST", "PUT", "DELETE", "PATCH")
MAX_DETAIL = 300

# (method, route regex, action verb). The regex is matched against the path after the /api prefix; a named group
# `target` becomes the audit row's target. Order matters: the first match wins.
ACTION_MAP: list[tuple[str, re.Pattern, str]] = [(m, re.compile(p), a) for m, p, a in [
    ("POST", r"^/auth/session$", "auth.session"),
    ("POST", r"^/auth/oauth/login-url$", "auth.oauth_login_url"),
    ("POST", r"^/auth/oauth/token$", "auth.oauth_token"),
    ("POST", r"^/auth/verify$", "auth.verify"),
    ("POST", r"^/auth/disconnect$", "auth.disconnect"),
    ("POST", r"^/paper/trade$", "paper.trade"),
    ("POST", r"^/paper/close/(?P<target>[^/]+)$", "paper.close"),
    ("POST", r"^/paper/settings$", "paper.settings"),
    ("POST", r"^/paper/reset$", "paper.reset"),
    ("POST", r"^/paper/kill-switch/release$", "kill_switch.release"),
    ("POST", r"^/paper/kill-switch$", "kill_switch.engage"),
    ("POST", r"^/signals/scan-now$", "signals.scan_now"),
    ("POST", r"^/signals/close/(?P<target>[^/]+)$", "signals.close"),
    ("PUT", r"^/settings$", "settings.update"),
    ("POST", r"^/settings/(?P<target>[^/]+)/reset$", "settings.reset"),
    ("POST", r"^/live/mode$", "live.mode"),
    ("POST", r"^/live/arm$", "live.arm"),
    ("POST", r"^/live/enable$", "live.enable"),
    ("POST", r"^/live/resume$", "live.resume"),
    ("POST", r"^/live/reconcile$", "live.reconcile"),
    ("POST", r"^/live/positions/(?P<target>[^/]+)/retry-exit$", "live.retry_exit"),
    ("POST", r"^/live/broker/login$", "live.broker_login"),
    ("POST", r"^/live/broker/logout$", "live.broker_logout"),
    ("POST", r"^/earnings/calendar/sync$", "earnings.calendar_sync"),
    ("POST", r"^/earnings/calendar$", "earnings.calendar_save"),
    ("DELETE", r"^/earnings/calendar/(?P<target>[^/]+/[^/]+)$", "earnings.calendar_delete"),
    ("POST", r"^/earnings/iv-history$", "earnings.iv_import"),
    ("POST", r"^/earnings/run-cycle$", "earnings.run_cycle"),
    ("POST", r"^/earnings/square-off$", "earnings.square_off"),
    ("POST", r"^/swing/run$", "swing.run"),
    ("POST", r"^/telemetry/purge$", "telemetry.purge"),
    ("PUT", r"^/journal/trades/(?P<target>[^/]+)$", "journal.save"),
    ("PUT", r"^/ui/layouts/(?P<target>[^/]+)$", "ui.layout.save"),
    ("DELETE", r"^/ui/layouts/(?P<target>[^/]+)$", "ui.layout.delete"),
    ("POST", r"^/ui/layouts/(?P<target>[^/]+)/restore/[^/]+$", "ui.layout.restore"),
]]

# Their request bodies and error text may carry secrets (tokens, TOTP codes, arming codes): only the action and the
# outcome are stored for these.
SENSITIVE_PREFIXES = ("/auth/", "/live/broker/", "/live/enable")

_JWT = re.compile(r"eyJ[a-zA-Z0-9_\-\.]{15,}")


def classify(method: str, path: str, api_prefix: str = "/api") -> tuple[str, Optional[str], bool]:
    """Returns (action, target, sensitive) for a mutating request."""
    rel = path[len(api_prefix):] if path.startswith(api_prefix) else path
    sensitive = rel.startswith(SENSITIVE_PREFIXES)
    for m, rx, action in ACTION_MAP:
        if m == method:
            hit = rx.match(rel)
            if hit:
                target = hit.groupdict().get("target")
                return action, (target[:120] if target else None), sensitive
    return f"unknown.{rel.strip('/').replace('/', '.') or 'root'}", None, sensitive


def outcome_of(status: int) -> str:
    if status in (401, 403):
        return "denied"
    return "ok" if status < 400 else "error"


def clean_detail(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = _JWT.sub("[token]", str(text))
    return text[:MAX_DETAIL]


class ActionAudit:
    def __init__(self, db_path: str):
        self.db_path = db_path
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
        try:
            with self._conn() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS action_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL, method TEXT NOT NULL, route TEXT NOT NULL,
                        action TEXT NOT NULL, target TEXT, outcome TEXT NOT NULL, status INTEGER NOT NULL,
                        detail TEXT, client TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_action_audit_ts ON action_audit(ts);
                    """
                )
        except Exception:
            logger.warning("action audit table could not be created", exc_info=True)

    def record(self, method: str, route: str, action: str, target: Optional[str], outcome: str, status: int,
               detail: Optional[str] = None, client: Optional[str] = None) -> bool:
        """Best effort: returns False (and logs) instead of raising."""
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO action_audit (ts, method, route, action, target, outcome, status, detail, client) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (market_hours.now_ist().isoformat(), method, route[:200], action, target, outcome, status,
                     clean_detail(detail), (client or "")[:64] or None),
                )
            return True
        except Exception:
            logger.warning("action audit write failed", exc_info=True)
            return False

    def list_actions(self, limit: int = 200, since: Optional[str] = None, action: Optional[str] = None,
                     outcome: Optional[str] = None) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        where, args = [], []
        if since:
            where.append("ts >= ?"); args.append(since)
        if action:
            where.append("action = ?"); args.append(action)
        if outcome:
            where.append("outcome = ?"); args.append(outcome)
        sql = "SELECT * FROM action_audit" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?;"
        with self._conn() as conn:
            rows = conn.execute(sql, (*args, limit)).fetchall()
        return [dict(r) for r in rows]
