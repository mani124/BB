"""Market-data recorder: keeps every completed 5m/15m bar the scanner sees, so ideas can be tested offline.

Today only the candles of trades that were taken are saved, so a setup idea (or a Setup 5 variant such as an
earlier entry cutoff) can only be judged on the handful of trades it produced. This stores all completed bars from
real data (spot bars from live ticks and the Dhan intraday seed, option bars from live ticks) in its own SQLite file
``market_bars.db`` next to the trades database, so it never slows the trade journal or its nightly backup.

Writes are buffered and flushed in a worker thread at most every ``FLUSH_EVERY_S`` seconds; an insert that already
exists is ignored, so seeding after a restart never duplicates. Recording can never raise into trading code.
Switches and retention are runtime settings (``recorder_enabled``, ``recorder_retention_days``).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from app.core.config import settings
from app.services import db, market_hours

logger = logging.getLogger(__name__)

FLUSH_EVERY_S = 20.0
MAX_BUFFER = 50000  # drop the oldest if the writer cannot keep up, rather than grow without limit
SPOT, OPTION = "spot", "option"


def _ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        try:
            import pandas as pd
            return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


class MarketRecorder:
    def __init__(self, path: Optional[str] = None, runtime: Any = None):
        self.path = path or os.path.join(settings.DATA_DIR, "market_bars.db")
        self.runtime = runtime
        self._buf: list[tuple] = []
        self._lock = threading.Lock()
        self._db_lock = threading.Lock()
        self._last_flush = 0.0
        self._ready = False
        self.recorded = 0
        self.dropped = 0

    # ------------------------------------------------------------------ switches
    def _setting(self, key: str, default: Any) -> Any:
        if self.runtime is None:
            return default
        try:
            return self.runtime.get(key)
        except Exception:
            return default

    @property
    def enabled(self) -> bool:
        return bool(self._setting("recorder_enabled", True))

    # ------------------------------------------------------------------ recording
    def record(self, kind: str, key: str, tf_min: int, bar: dict) -> None:
        """Queue one completed bar. ``bar`` has timestamp/open/high/low/close/volume."""
        if not self.enabled:
            return
        try:
            ts = _ts(bar.get("timestamp"))
            if ts is None:
                return
            row = (kind, str(key), int(tf_min), ts, float(bar["open"]), float(bar["high"]), float(bar["low"]),
                   float(bar["close"]), int(bar.get("volume") or 0))
        except Exception:
            return
        with self._lock:
            self._buf.append(row)
            if len(self._buf) > MAX_BUFFER:
                over = len(self._buf) - MAX_BUFFER
                del self._buf[:over]
                self.dropped += over

    def record_many(self, kind: str, key: str, tf_min: int, bars: Iterable[dict]) -> None:
        for b in bars:
            self.record(kind, key, tf_min, b)

    # ------------------------------------------------------------------ storage
    def _init_db(self) -> None:
        if self._ready:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with db.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS bars (
                kind TEXT NOT NULL, key TEXT NOT NULL, tf INTEGER NOT NULL, ts TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER,
                PRIMARY KEY (kind, key, tf, ts)) WITHOUT ROWID""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_bars_ts ON bars(ts)")
        self._ready = True

    def flush(self) -> int:
        """Write the buffer. Safe to call from a thread. Returns rows offered to the database."""
        with self._lock:
            rows, self._buf = self._buf, []
        self._last_flush = time.monotonic()
        if not rows:
            return 0
        try:
            with self._db_lock:
                self._init_db()
                conn = db.connect(self.path)
                try:
                    with conn:
                        conn.executemany("INSERT OR IGNORE INTO bars VALUES (?,?,?,?,?,?,?,?,?)", rows)
                finally:
                    conn.close()
            self.recorded += len(rows)
            return len(rows)
        except Exception:
            logger.warning("market recorder flush failed; %d bars kept for the next try", len(rows), exc_info=True)
            with self._lock:
                self._buf = (rows + self._buf)[-MAX_BUFFER:]
            return 0

    async def maybe_flush(self, force: bool = False) -> None:
        if not self._buf:
            return
        if not force and time.monotonic() - self._last_flush < FLUSH_EVERY_S:
            return
        await asyncio.to_thread(self.flush)

    def purge(self) -> int:
        days = int(self._setting("recorder_retention_days", 180))
        if days <= 0 or not os.path.exists(self.path):
            return 0
        cutoff = (market_hours.now_ist() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._db_lock:
            self._init_db()
            with db.connect(self.path) as c:
                return c.execute("DELETE FROM bars WHERE ts < ?", (cutoff,)).rowcount

    # ------------------------------------------------------------------ readers
    def status(self) -> dict:
        out = {"enabled": self.enabled, "path": self.path, "buffered": len(self._buf), "recorded_this_run": self.recorded,
               "dropped": self.dropped, "kinds": {}}
        if not os.path.exists(self.path):
            return out
        with self._db_lock:
            self._init_db()
            with db.connect(self.path) as c:
                for kind, n, keys, first, last in c.execute(
                        "SELECT kind, COUNT(*), COUNT(DISTINCT key), MIN(ts), MAX(ts) FROM bars GROUP BY kind"):
                    out["kinds"][kind] = {"bars": n, "keys": keys, "first": first, "last": last}
                out["days"] = [r[0] for r in c.execute(
                    "SELECT DISTINCT substr(ts,1,10) d FROM bars ORDER BY d DESC LIMIT 30")]
        return out

    def bars(self, kind: str, key: str, tf_min: int = 5, day: Optional[str] = None, limit: int = 5000) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        sql = "SELECT ts, open, high, low, close, volume FROM bars WHERE kind=? AND key=? AND tf=?"
        args: list[Any] = [kind, key, tf_min]
        if day:
            sql += " AND substr(ts,1,10)=?"
            args.append(day)
        sql += " ORDER BY ts LIMIT ?"
        args.append(int(limit))
        with self._db_lock:
            self._init_db()
            with db.connect(self.path) as c:
                return [dict(zip(("timestamp", "open", "high", "low", "close", "volume"), r)) for r in c.execute(sql, args)]


recorder = MarketRecorder()
