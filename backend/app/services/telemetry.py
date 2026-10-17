"""Quantitative telemetry: why the engine did or did not trade, what went wrong, and how each trade travelled.

Records, all in the trades database (plus an optional JSONL mirror for pandas):

* ``strategy_decisions``  every ENTERED / SKIPPED / EXITED decision with the reason code and the numbers behind it.
* ``error_events``        warnings and errors from the app's loggers, grouped under a short error code.
* ``trade_excursions``    per position: MFE (best open profit) and MAE (worst open loss) in rupees, and final P&L.

Everything is switchable at runtime (``telemetry_*`` settings) and writing can never raise into trading code.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
import traceback
from collections import Counter, defaultdict
from typing import Any, Optional

from app.services import market_hours
from app.services.runtime_settings import RuntimeSettings
from app.services import db

logger = logging.getLogger(__name__)

DECISIONS = ("ENTERED", "SKIPPED", "EXITED", "HELD")
SEVERITIES = ("INFO", "WARNING", "ERROR", "CRITICAL")


def _now_str() -> str:
    return market_hours.now_ist().strftime("%Y-%m-%d %H:%M:%S")


def _cutoff_str(hours: float) -> str:
    from datetime import timedelta
    return (market_hours.now_ist() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


class Telemetry:
    def __init__(self, db_path: Optional[str], runtime: RuntimeSettings, log_dir: Optional[str] = None):
        self.db_path = db_path
        self.runtime = runtime
        self.log_dir = log_dir
        self._lock = threading.RLock()
        # position_id -> running excursion state, flushed to the database on an interval and at close
        self._exc: dict[str, dict] = {}
        self._last_flush = 0.0
        self._recent_errors: dict[tuple, float] = {}
        if db_path:
            self._init_db()

    # ------------------------------------------------------------------ storage
    def _conn(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS strategy_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, book TEXT, strategy TEXT, symbol TEXT, side TEXT,
                decision TEXT, reason TEXT, metrics TEXT, signal_id TEXT, position_id TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dec_ts ON strategy_decisions(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dec_strategy ON strategy_decisions(strategy, decision, ts)")
            conn.execute("""CREATE TABLE IF NOT EXISTS error_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, code TEXT, component TEXT, severity TEXT,
                message TEXT, stack TEXT, payload TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_err_ts ON error_events(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_err_code ON error_events(code, ts)")
            conn.execute("""CREATE TABLE IF NOT EXISTS trade_excursions (
                position_id TEXT PRIMARY KEY, book TEXT, strategy TEXT, symbol TEXT, side TEXT,
                opened_at TEXT, qty INTEGER, entry_price REAL, risk_rupees REAL,
                mfe REAL DEFAULT 0, mae REAL DEFAULT 0, mfe_at TEXT, mae_at TEXT,
                last_pnl REAL DEFAULT 0, final_pnl REAL, closed INTEGER DEFAULT 0, updated_at TEXT)""")

    def _enabled(self) -> bool:
        try:
            return bool(self.runtime.get("telemetry_enabled"))
        except Exception:
            return False

    def _mirror(self, name: str, record: dict) -> None:
        try:
            if not self.log_dir or not self.runtime.get("telemetry_jsonl_enabled"):
                return
            os.makedirs(self.log_dir, exist_ok=True)
            with open(os.path.join(self.log_dir, f"{name}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            logger.debug("telemetry mirror failed", exc_info=True)

    # ------------------------------------------------------------------ writers
    def decision(self, *, book: str, strategy: str, symbol: str, decision: str, reason: str,
                 side: str = "", metrics: Optional[dict] = None, signal_id: Optional[str] = None,
                 position_id: Optional[str] = None) -> None:
        """Record one decision point. `reason` is a short code (e.g. LOSS_CAP, SPREAD_TOO_WIDE, TARGET_1)."""
        if not self.db_path or not self._enabled():
            return
        if decision == "SKIPPED" and not self.runtime.get("telemetry_skip_logging"):
            return
        ts = _now_str()
        try:
            with self._lock, self._conn() as conn:
                conn.execute(
                    "INSERT INTO strategy_decisions (ts, book, strategy, symbol, side, decision, reason, metrics, signal_id, position_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ts, book, strategy, symbol, side, decision, reason, json.dumps(metrics or {}, default=str),
                     signal_id, position_id))
            self._mirror("strategy_decisions", {"ts": ts, "book": book, "strategy": strategy, "symbol": symbol,
                                                "side": side, "decision": decision, "reason": reason,
                                                "metrics": metrics or {}, "signal_id": signal_id,
                                                "position_id": position_id})
        except Exception:
            logger.debug("telemetry decision write failed", exc_info=True)

    def error(self, *, code: str, component: str, message: str, severity: str = "ERROR",
              stack: str = "", payload: Optional[dict] = None, dedupe_seconds: float = 30.0) -> None:
        if not self.db_path or not self._enabled():
            return
        key = (code, component, message[:160])
        now = time.monotonic()
        with self._lock:
            last = self._recent_errors.get(key)
            if last is not None and now - last < dedupe_seconds:
                return
            self._recent_errors[key] = now
            if len(self._recent_errors) > 2000:
                cutoff = now - dedupe_seconds
                self._recent_errors = {k: v for k, v in self._recent_errors.items() if v >= cutoff}
        ts = _now_str()
        sev = severity.upper() if severity.upper() in SEVERITIES else "ERROR"
        try:
            with self._lock, self._conn() as conn:
                conn.execute("INSERT INTO error_events (ts, code, component, severity, message, stack, payload) VALUES (?,?,?,?,?,?,?)",
                             (ts, code, component, sev, message[:2000], stack[-4000:], json.dumps(payload or {}, default=str)))
            self._mirror("error_events", {"ts": ts, "code": code, "component": component, "severity": sev,
                                          "message": message[:2000], "payload": payload or {}})
        except Exception:
            logger.debug("telemetry error write failed", exc_info=True)

    # ---- excursions ----
    def track(self, pos: Any) -> None:
        """Update the running MFE / MAE of an open position from its gross P&L in rupees."""
        if not self.db_path or not self._enabled():
            return
        try:
            pnl = float(getattr(pos, "booked_pnl_rupees", 0.0) or 0.0) + float(pos.pnl_points) * float(pos.quantity)
        except Exception:
            return
        ts = _now_str()
        with self._lock:
            st = self._exc.get(pos.id)
            if st is None:
                qty = int(getattr(pos, "initial_quantity", None) or pos.quantity)
                risk = abs(float(pos.option_entry) - float(pos.option_sl)) * qty if getattr(pos, "option_sl", None) else 0.0
                st = {"position_id": pos.id, "book": getattr(pos, "feed_mode", "demo"), "strategy": pos.setup_type,
                      "symbol": pos.symbol, "side": pos.option_type, "opened_at": getattr(pos, "entry_datetime", None) or ts,
                      "qty": qty, "entry_price": float(pos.option_entry), "risk_rupees": round(risk, 2),
                      "mfe": 0.0, "mae": 0.0, "mfe_at": None, "mae_at": None, "last_pnl": 0.0, "dirty": True}
                self._exc[pos.id] = st
            if pnl > st["mfe"]:
                st["mfe"], st["mfe_at"], st["dirty"] = round(pnl, 2), ts, True
            if pnl < st["mae"]:
                st["mae"], st["mae_at"], st["dirty"] = round(pnl, 2), ts, True
            st["last_pnl"] = round(pnl, 2)
            interval = float(self.runtime.get("telemetry_excursion_flush_seconds"))
            due = time.monotonic() - self._last_flush >= interval
        if due:
            self.flush()

    def flush(self, only: Optional[str] = None) -> None:
        if not self.db_path:
            return
        with self._lock:
            self._last_flush = time.monotonic()
            targets = [s for pid, s in self._exc.items() if s.get("dirty") and (only is None or pid == only)]
            rows = [dict(s) for s in targets]
            for s in targets:
                s["dirty"] = False
        if not rows:
            return
        ts = _now_str()
        try:
            with self._lock, self._conn() as conn:
                for s in rows:
                    conn.execute(
                        """INSERT INTO trade_excursions (position_id, book, strategy, symbol, side, opened_at, qty, entry_price,
                               risk_rupees, mfe, mae, mfe_at, mae_at, last_pnl, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(position_id) DO UPDATE SET mfe=excluded.mfe, mae=excluded.mae, mfe_at=excluded.mfe_at,
                               mae_at=excluded.mae_at, last_pnl=excluded.last_pnl, updated_at=excluded.updated_at""",
                        (s["position_id"], s["book"], s["strategy"], s["symbol"], s["side"], s["opened_at"], s["qty"],
                         s["entry_price"], s["risk_rupees"], s["mfe"], s["mae"], s["mfe_at"], s["mae_at"], s["last_pnl"], ts))
        except Exception:
            logger.debug("telemetry excursion flush failed", exc_info=True)

    def close_trade(self, pos: Any, final_pnl: float) -> None:
        """Finalise a position's excursions. The realised result also bounds MFE / MAE (a gap can overshoot the last tick)."""
        if not self.db_path or not self._enabled():
            return
        self.track(pos)
        with self._lock:
            st = self._exc.get(pos.id)
            if st is None:
                return
            ts = _now_str()
            if final_pnl > st["mfe"]:
                st["mfe"], st["mfe_at"] = round(final_pnl, 2), ts
            if final_pnl < st["mae"]:
                st["mae"], st["mae_at"] = round(final_pnl, 2), ts
            st["dirty"] = True
        self.flush(only=pos.id)
        try:
            with self._lock, self._conn() as conn:
                conn.execute("UPDATE trade_excursions SET final_pnl = ?, closed = 1 WHERE position_id = ?",
                             (round(final_pnl, 2), pos.id))
        except Exception:
            logger.debug("telemetry close failed", exc_info=True)
        with self._lock:
            self._exc.pop(pos.id, None)

    def purge(self) -> dict:
        days = int(self.runtime.get("telemetry_retention_days"))
        if not self.db_path or days <= 0:
            return {"decisions": 0, "errors": 0, "excursions": 0}
        cutoff = _cutoff_str(days * 24)
        with self._lock, self._conn() as conn:
            d = conn.execute("DELETE FROM strategy_decisions WHERE ts < ?", (cutoff,)).rowcount
            e = conn.execute("DELETE FROM error_events WHERE ts < ?", (cutoff,)).rowcount
            x = conn.execute("DELETE FROM trade_excursions WHERE closed = 1 AND opened_at < ?", (cutoff,)).rowcount
        return {"decisions": d, "errors": e, "excursions": x}

    # ------------------------------------------------------------------ readers
    def decisions(self, *, hours: float = 24, strategy: Optional[str] = None, decision: Optional[str] = None,
                  symbol: Optional[str] = None, book: Optional[str] = None, limit: int = 200) -> list[dict]:
        if not self.db_path:
            return []
        q, args = "SELECT * FROM strategy_decisions WHERE ts >= ?", [_cutoff_str(hours)]
        for col, val in (("strategy", strategy), ("decision", decision), ("symbol", symbol), ("book", book)):
            if val:
                q += f" AND {col} = ?"
                args.append(val)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 2000)))
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute(q, args).fetchall()]
        for r in rows:
            try:
                r["metrics"] = json.loads(r["metrics"] or "{}")
            except ValueError:
                r["metrics"] = {}
        return rows

    def errors(self, *, hours: float = 24, code: Optional[str] = None, limit: int = 200) -> list[dict]:
        if not self.db_path:
            return []
        q, args = "SELECT * FROM error_events WHERE ts >= ?", [_cutoff_str(hours)]
        if code:
            q += " AND code = ?"
            args.append(code)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 2000)))
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute(q, args).fetchall()]
        for r in rows:
            try:
                r["payload"] = json.loads(r["payload"] or "{}")
            except ValueError:
                r["payload"] = {}
        return rows

    def excursions(self, *, hours: float = 24 * 30, strategy: Optional[str] = None, limit: int = 500) -> list[dict]:
        if not self.db_path:
            return []
        self.flush()
        q, args = "SELECT * FROM trade_excursions WHERE opened_at >= ?", [_cutoff_str(hours)]
        if strategy:
            q += " AND strategy = ?"
            args.append(strategy)
        q += " ORDER BY opened_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 5000)))
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(q, args).fetchall()]

    def insights(self, hours: float = 24) -> dict:
        """Aggregates for the telemetry tab: decision ratios, top skip reasons, error buckets, excursions per setup."""
        if not self.db_path:
            return {"hours": hours, "decisions": {}, "by_strategy": {}, "top_skip_reasons": [], "errors": [], "excursions": []}
        cutoff = _cutoff_str(hours)
        with self._conn() as conn:
            dec = Counter()
            by_strategy: dict[str, Counter] = defaultdict(Counter)
            for r in conn.execute("SELECT strategy, decision, COUNT(*) n FROM strategy_decisions WHERE ts >= ? GROUP BY strategy, decision", (cutoff,)):
                dec[r["decision"]] += r["n"]
                by_strategy[r["strategy"]][r["decision"]] += r["n"]
            skips = [dict(r) for r in conn.execute(
                "SELECT reason, strategy, COUNT(*) n FROM strategy_decisions WHERE ts >= ? AND decision = 'SKIPPED' "
                "GROUP BY reason, strategy ORDER BY n DESC LIMIT 25", (cutoff,))]
            errs = [dict(r) for r in conn.execute(
                "SELECT code, component, severity, COUNT(*) n, MAX(ts) last_seen FROM error_events WHERE ts >= ? "
                "GROUP BY code, component, severity ORDER BY n DESC LIMIT 25", (cutoff,))]
        self.flush()
        with self._conn() as conn:
            exc = [dict(r) for r in conn.execute(
                "SELECT strategy, COUNT(*) trades, ROUND(AVG(mfe),2) avg_mfe, ROUND(AVG(mae),2) avg_mae, "
                "ROUND(AVG(final_pnl),2) avg_final FROM trade_excursions WHERE closed = 1 AND opened_at >= ? GROUP BY strategy",
                (cutoff,))]
        total = sum(dec.values())
        return {
            "hours": hours,
            "decisions": {**{k: dec.get(k, 0) for k in DECISIONS}, "total": total},
            "by_strategy": {s: dict(c) for s, c in by_strategy.items()},
            "top_skip_reasons": skips,
            "errors": errs,
            "excursions": exc,
        }


# ---------------------------------------------------------------------------------------------------
# Logging bridge: warnings/errors already emitted across the app become categorised error events.
# ---------------------------------------------------------------------------------------------------
_DQ = re.compile(r"DATA_QUALITY\s+([a-z_]+)", re.I)


def classify_log_record(record: logging.LogRecord) -> tuple[str, str]:
    """Return (error_code, component) for a log record."""
    msg = record.getMessage()
    comp = record.name.rsplit(".", 1)[-1].upper()
    m = _DQ.search(msg)
    if m:
        return f"DATA_QUALITY_{m.group(1).upper()}", comp
    low = msg.lower()
    if "429" in low or "rate limit" in low:
        return "RATE_LIMIT", comp
    if "timeout" in low or "timed out" in low:
        return "NETWORK_TIMEOUT", comp
    if "token" in low and ("expired" in low or "invalid" in low or "401" in low):
        return "AUTH_TOKEN", comp
    if record.exc_info and record.exc_info[0] is not None:
        return record.exc_info[0].__name__.upper(), comp
    if "kill switch" in low:
        return "KILL_SWITCH", comp
    if "loss cap" in low:
        return "LOSS_CAP", comp
    return ("LOG_ERROR" if record.levelno >= logging.ERROR else "LOG_WARNING"), comp


class TelemetryLogHandler(logging.Handler):
    """Attach to the root logger. Never raises, and ignores its own module's logs to avoid feedback loops."""

    def __init__(self, telemetry: Telemetry, level: int = logging.WARNING):
        super().__init__(level)
        self.telemetry = telemetry

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not record.name.startswith("app") or record.name == __name__:
                return
            code, comp = classify_log_record(record)
            stack = ""
            if record.exc_info:
                stack = "".join(traceback.format_exception(*record.exc_info))
            self.telemetry.error(code=code, component=comp, message=record.getMessage(),
                                 severity=record.levelname, stack=stack)
        except Exception:
            pass
