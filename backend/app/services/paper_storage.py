from __future__ import annotations
import sqlite3
import os
import json
from app.services import market_hours
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.paper_trader import PaperPosition

class PaperStorage:
    """SQLite-backed persistent storage for Paper Trading Engine."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                symbol TEXT,
                option_type TEXT,
                strike_symbol TEXT,
                timeframe TEXT,
                setup_type TEXT,
                entry_time TEXT,
                underlying_entry REAL,
                underlying_sl REAL,
                underlying_target_1 REAL,
                underlying_target_2 REAL,
                option_entry REAL,
                option_sl REAL,
                option_target_1 REAL,
                option_target_2 REAL,
                lot_size INTEGER,
                lots INTEGER,
                quantity INTEGER,
                current_underlying REAL,
                current_option_price REAL,
                pnl_points REAL,
                pnl_rupees REAL,
                status TEXT,
                exit_time TEXT,
                exit_reason TEXT,
                initial_lots INTEGER,
                initial_quantity INTEGER,
                booked_lots INTEGER,
                booked_pnl_rupees REAL,
                option_security_id TEXT,
                feed_mode TEXT DEFAULT 'demo',
                theoretical_entry REAL DEFAULT 0.0,
                entry_slippage REAL DEFAULT 0.0,
                theoretical_exit REAL DEFAULT 0.0,
                exit_slippage REAL DEFAULT 0.0,
                total_slippage_cost REAL DEFAULT 0.0,
                gross_pnl REAL DEFAULT 0.0,
                total_charges REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,
                charges_json TEXT DEFAULT '',
                booked_slippage_cost REAL DEFAULT 0.0,
                pending_spot_exit TEXT DEFAULT NULL,
                pending_spot_tp1 INTEGER DEFAULT 0,
                entry_datetime TEXT DEFAULT NULL,
                exit_datetime TEXT DEFAULT NULL,
                quarantine_reason TEXT DEFAULT NULL
            );
            """)

            # Auto-migrate table if columns do not exist
            migrations = [
                "ALTER TABLE positions ADD COLUMN option_security_id TEXT;",
                "ALTER TABLE positions ADD COLUMN feed_mode TEXT DEFAULT 'demo';",
                "ALTER TABLE positions ADD COLUMN theoretical_entry REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN entry_slippage REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN theoretical_exit REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN exit_slippage REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN total_slippage_cost REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN gross_pnl REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN total_charges REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN net_pnl REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN charges_json TEXT DEFAULT '';",
                "ALTER TABLE positions ADD COLUMN booked_slippage_cost REAL DEFAULT 0.0;",
                "ALTER TABLE positions ADD COLUMN pending_spot_exit TEXT DEFAULT NULL;",
                "ALTER TABLE positions ADD COLUMN pending_spot_tp1 INTEGER DEFAULT 0;",
                "ALTER TABLE positions ADD COLUMN entry_datetime TEXT DEFAULT NULL;",
                "ALTER TABLE positions ADD COLUMN exit_datetime TEXT DEFAULT NULL;",
                "ALTER TABLE positions ADD COLUMN quarantine_reason TEXT DEFAULT NULL;",
                "ALTER TABLE positions ADD COLUMN entry_estimated INTEGER DEFAULT 0;",
                "ALTER TABLE positions ADD COLUMN archived_at TEXT DEFAULT NULL;",
            ]
            for stmt in migrations:
                try:
                    cursor.execute(stmt)
                except sqlite3.OperationalError:
                    pass

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_signals (
                signal_id TEXT PRIMARY KEY,
                created_at TEXT
            );
            """)
            # Additive: per-trade chart candles so closed trades and trades from before a restart still chart.
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_candles (
                position_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                bars_json TEXT NOT NULL,
                updated_at TEXT,
                PRIMARY KEY (position_id, kind)
            );
            """)
            self._backfill_datetimes(cursor)
            conn.commit()

    @staticmethod
    def _backfill_datetimes(cursor) -> None:
        """Non-destructive migration for rows written before entry/exit datetimes existed.

        entry_datetime is recovered from the epoch embedded in the position id
        (``POS_<sym>_<CE|PE>_<epoch>_<hex>``), falling back to processed_signals.created_at.
        exit_datetime is entry date + the stored HH:MM:SS exit_time (next day if earlier
        than the entry time). Original entry_time/exit_time columns are left untouched.
        """
        from app.services.market_hours import IST
        rows = cursor.execute(
            "SELECT p.id, p.entry_time, p.exit_time, p.status, s.created_at "
            "FROM positions p LEFT JOIN processed_signals s ON s.signal_id = p.signal_id "
            "WHERE p.entry_datetime IS NULL;"
        ).fetchall()
        for pid, entry_time, exit_time, status, created_at in rows:
            entry_dt = None
            parts = str(pid).split("_")
            if len(parts) >= 2:
                try:
                    entry_dt = datetime.fromtimestamp(int(parts[-2]), IST).replace(microsecond=0)
                except (ValueError, OverflowError, OSError):
                    entry_dt = None
            if entry_dt is None and created_at:
                try:
                    entry_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
                except ValueError:
                    entry_dt = None
            if entry_dt is None:
                continue
            exit_dt_str = None
            if exit_time and status not in ("OPEN", "TARGET_1"):
                try:
                    et = datetime.strptime(exit_time, "%H:%M:%S").time()
                    exit_dt = datetime.combine(entry_dt.date(), et, tzinfo=IST)
                    if exit_dt < entry_dt:
                        exit_dt += timedelta(days=1)
                    exit_dt_str = exit_dt.isoformat(timespec="seconds")
                except ValueError:
                    pass
            cursor.execute(
                "UPDATE positions SET entry_datetime = ?, exit_datetime = COALESCE(exit_datetime, ?) WHERE id = ?;",
                (entry_dt.isoformat(timespec="seconds"), exit_dt_str, pid),
            )

    _COLUMNS = (
        "id", "signal_id", "symbol", "option_type", "strike_symbol", "timeframe", "setup_type",
        "entry_time", "underlying_entry", "underlying_sl", "underlying_target_1", "underlying_target_2",
        "option_entry", "option_sl", "option_target_1", "option_target_2",
        "lot_size", "lots", "quantity", "current_underlying", "current_option_price",
        "pnl_points", "pnl_rupees", "status", "exit_time", "exit_reason",
        "initial_lots", "initial_quantity", "booked_lots", "booked_pnl_rupees",
        "option_security_id", "feed_mode",
        "theoretical_entry", "entry_slippage", "theoretical_exit", "exit_slippage",
        "total_slippage_cost", "gross_pnl", "total_charges", "net_pnl", "charges_json",
        "booked_slippage_cost", "pending_spot_exit", "pending_spot_tp1",
        "entry_datetime", "exit_datetime", "quarantine_reason", "entry_estimated",
    )
    # Columns that never change after the row is first inserted.
    # (underlying_sl / option_sl are deliberately absent: they move to entry at Target 1 and must persist.)
    _IMMUTABLE = frozenset({
        "id", "signal_id", "symbol", "option_type", "strike_symbol", "timeframe", "setup_type",
        "entry_time", "underlying_entry", "underlying_target_1", "underlying_target_2",
        "option_entry", "option_target_1", "option_target_2", "lot_size",
        "initial_lots", "initial_quantity",
    })

    @classmethod
    def _upsert_sql(cls) -> str:
        placeholders = ", ".join("?" for _ in cls._COLUMNS)
        sets = []
        for col in cls._COLUMNS:
            if col in cls._IMMUTABLE:
                continue
            if col == "option_security_id":
                sets.append("option_security_id=COALESCE(excluded.option_security_id, positions.option_security_id)")
            elif col == "entry_datetime":
                sets.append("entry_datetime=COALESCE(positions.entry_datetime, excluded.entry_datetime)")
            else:
                sets.append(f"{col}=excluded.{col}")
        return (
            f"INSERT INTO positions ({', '.join(cls._COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {', '.join(sets)};"
        )

    @staticmethod
    def _row_params(pos: PaperPosition) -> tuple:
        charges_json = json.dumps(pos.charges_breakdown) if pos.charges_breakdown else ""
        return (
            pos.id, pos.signal_id, pos.symbol, pos.option_type, pos.strike_symbol, pos.timeframe, pos.setup_type,
            pos.entry_time, pos.underlying_entry, pos.underlying_sl, pos.underlying_target_1, pos.underlying_target_2,
            pos.option_entry, pos.option_sl, pos.option_target_1, pos.option_target_2,
            pos.lot_size, pos.lots, pos.quantity, pos.current_underlying, pos.current_option_price,
            pos.pnl_points, pos.pnl_rupees, pos.status, pos.exit_time, pos.exit_reason,
            pos.initial_lots, pos.initial_quantity, pos.booked_lots, pos.booked_pnl_rupees,
            pos.option_security_id, getattr(pos, "feed_mode", "demo"),
            pos.theoretical_entry, pos.entry_slippage, pos.theoretical_exit, pos.exit_slippage,
            pos.total_slippage_cost, pos.gross_pnl, pos.total_charges, pos.net_pnl, charges_json,
            getattr(pos, "booked_slippage_cost", 0.0), getattr(pos, "pending_spot_exit", None),
            1 if getattr(pos, "pending_spot_tp1", False) else 0,
            getattr(pos, "entry_datetime", None), getattr(pos, "exit_datetime", None),
            getattr(pos, "quarantine_reason", None),
            1 if getattr(pos, "entry_estimated", False) else 0,
        )

    def upsert_position(self, pos: PaperPosition):
        with self._get_connection() as conn:
            conn.execute(self._upsert_sql(), self._row_params(pos))
            conn.commit()

    def record_entry(self, pos: PaperPosition, signal_id: str, created_at: str = "") -> None:
        """Atomically persist a newly opened position together with its processed signal id.

        Both rows are committed in one transaction so a crash or reload can never leave a
        position without its processed-signal marker (which would let the same signal open
        a second position after restart)."""
        with self._get_connection() as conn:
            conn.execute(self._upsert_sql(), self._row_params(pos))
            conn.execute(
                "INSERT OR IGNORE INTO processed_signals (signal_id, created_at) VALUES (?, ?);",
                (signal_id, created_at),
            )
            conn.commit()

    def batch_upsert_positions(self, positions: list[PaperPosition]):
        """Persist multiple positions in a single SQLite transaction."""
        if not positions:
            return
        with self._get_connection() as conn:
            conn.executemany(self._upsert_sql(), [self._row_params(p) for p in positions])
            conn.commit()

    def set_quarantine(self, position_ids: list[str], reason: str) -> int:
        """Flag rows as quarantined (excluded from performance totals). Never deletes."""
        if not position_ids:
            return 0
        with self._get_connection() as conn:
            cur = conn.executemany(
                "UPDATE positions SET quarantine_reason = ? WHERE id = ?;",
                [(reason, pid) for pid in position_ids],
            )
            conn.commit()
            return cur.rowcount

    def clear_quarantine(self, position_ids: list[str]) -> int:
        if not position_ids:
            return 0
        with self._get_connection() as conn:
            cur = conn.executemany(
                "UPDATE positions SET quarantine_reason = NULL WHERE id = ?;",
                [(pid,) for pid in position_ids],
            )
            conn.commit()
            return cur.rowcount

    def load_all_positions(self):
        """Returns (active_positions, closed_trades)."""
        from app.services.paper_trader import PaperPosition
        active: list[PaperPosition] = []
        closed: list[PaperPosition] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Archived rows (from a portfolio reset) stay in the table but are not loaded.
            cursor.execute(
                "SELECT * FROM positions WHERE archived_at IS NULL "
                "ORDER BY (entry_datetime IS NOT NULL), COALESCE(entry_datetime, entry_time) ASC;"
            )
            rows = cursor.fetchall()
            for row in rows:
                d = dict(row)
                d.pop("archived_at", None)
                charges_str = d.pop("charges_json", None)
                if charges_str:
                    try:
                        d["charges_breakdown"] = json.loads(charges_str)
                    except Exception:
                        d["charges_breakdown"] = None
                else:
                    d["charges_breakdown"] = None

                d["theoretical_entry"] = float(d.get("theoretical_entry") or 0.0)
                d["entry_slippage"] = float(d.get("entry_slippage") or 0.0)
                d["theoretical_exit"] = float(d["theoretical_exit"]) if d.get("theoretical_exit") is not None else None
                d["exit_slippage"] = float(d.get("exit_slippage") or 0.0)
                d["total_slippage_cost"] = float(d.get("total_slippage_cost") or 0.0)
                gross_val = d.get("gross_pnl")
                d["gross_pnl"] = float(gross_val if gross_val is not None and gross_val != 0.0 else (d.get("pnl_rupees") or 0.0))
                d["total_charges"] = float(d.get("total_charges") or 0.0)
                net_val = d.get("net_pnl")
                d["net_pnl"] = float(net_val if net_val is not None and net_val != 0.0 else (d["gross_pnl"] - d["total_charges"]))
                if not d.get("feed_mode"):
                    d["feed_mode"] = "demo"
                d["booked_slippage_cost"] = float(d.get("booked_slippage_cost") or 0.0)
                d["pending_spot_exit"] = d.get("pending_spot_exit") or None
                d["pending_spot_tp1"] = bool(d.get("pending_spot_tp1") or 0)
                d["entry_datetime"] = d.get("entry_datetime") or None
                d["exit_datetime"] = d.get("exit_datetime") or None
                d["quarantine_reason"] = d.get("quarantine_reason") or None
                d["entry_estimated"] = bool(d.get("entry_estimated") or 0)

                pos = PaperPosition(**d)
                if pos.status in ["OPEN", "TARGET_1"]:
                    active.append(pos)
                else:
                    closed.append(pos)
        return active, closed

    def save_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);", (key, str(value)))
            conn.commit()

    def load_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default

    def add_processed_signal(self, signal_id: str, created_at: str = ""):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO processed_signals (signal_id, created_at) VALUES (?, ?);", (signal_id, created_at))
            conn.commit()

    def load_processed_signals(self) -> set[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT signal_id FROM processed_signals;")
            rows = cursor.fetchall()
            return {r["signal_id"] for r in rows}

    TRADE_CANDLE_CAP = 150          # bars kept per series (about two 5m sessions: warm-up for the bands)
    TRADE_CANDLE_RETENTION_DAYS = 90

    def save_trade_candles(self, position_id: str, kind: str, bars: list[dict]) -> None:
        """Store (replace) the candle series for one trade; `kind` is 'option' or 'underlying'."""
        if not bars:
            return
        rows = []
        for b in bars[-self.TRADE_CANDLE_CAP:]:
            ts = b.get("timestamp")
            rows.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "open": b.get("open"), "high": b.get("high"), "low": b.get("low"),
                "close": b.get("close"), "volume": b.get("volume", 0),
            })
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO trade_candles (position_id, kind, bars_json, updated_at) VALUES (?, ?, ?, ?);",
                (position_id, kind, json.dumps(rows), market_hours.now_ist().replace(microsecond=0).isoformat()),
            )
            conn.commit()

    def load_trade_candles(self, position_id: str, kind: str) -> list[dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT bars_json FROM trade_candles WHERE position_id = ? AND kind = ?;", (position_id, kind)
            ).fetchone()
        if not row:
            return []
        try:
            return json.loads(row["bars_json"])
        except (TypeError, ValueError):
            return []

    def prune_trade_candles(self) -> int:
        """Drop candle rows with no matching trade, or older than the retention window."""
        cutoff = (market_hours.now_ist() - timedelta(days=self.TRADE_CANDLE_RETENTION_DAYS)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM trade_candles WHERE updated_at < ? OR position_id NOT IN (SELECT id FROM positions);",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount

    def backup_to(self, dest_path: str) -> None:
        """Consistent copy of the whole database (sqlite online backup)."""
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    def clear_all(self):
        """Portfolio reset. Nothing is deleted from the journal: a backup copy is written to
        <db dir>/backups/ and every current row is stamped archived_at, which hides it from
        the dashboard. Only processed signal ids (no trade data) are cleared."""
        from app.services.market_hours import now_ist
        now = now_ist().replace(microsecond=0)
        stamp = now.strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "backups")
        self.backup_to(os.path.join(backup_dir, f"trades-before-reset-{stamp}.db"))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE positions SET archived_at = ? WHERE archived_at IS NULL;",
                (now.isoformat(),),
            )
            cursor.execute("DELETE FROM processed_signals;")
            conn.commit()
