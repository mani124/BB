"""One way to open the trades database.

Nine modules write to the same SQLite file (paper trades, telemetry, live orders, earnings, journal, settings).
In the default rollback-journal mode a writer blocks every reader and a second writer fails after the timeout, so a
slow journal query or telemetry purge could delay an exit write. ``connect`` turns on WAL (readers and the single
writer no longer block each other), waits up to ``BUSY_TIMEOUT_S`` for a lock instead of failing at once, and uses
``synchronous=NORMAL`` (safe with WAL: a power cut can lose the last commit, never corrupt the file).
"""
from __future__ import annotations

import logging
import sqlite3
import threading

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_S = 15.0
_wal_done: set[str] = set()
_lock = threading.Lock()


class ClosingConnection(sqlite3.Connection):
    """A plain ``with sqlite3.connect(...) as c`` commits or rolls back but leaves the connection open until the
    garbage collector finds it. Every caller here opens one connection per ``with`` block, so close it there."""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def connect(path: str, *, timeout: float = BUSY_TIMEOUT_S) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout, factory=ClosingConnection)
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    with _lock:
        first = path not in _wal_done
    if first:
        # journal_mode is stored in the file, so setting it once per path per process is enough.
        try:
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(mode).lower() not in ("wal", "memory"):
                logger.warning("SQLite WAL not enabled for %s (mode %s)", path, mode)
        except sqlite3.Error as exc:
            logger.warning("Could not enable SQLite WAL for %s: %s", path, type(exc).__name__)
        with _lock:
            _wal_done.add(path)
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
