from __future__ import annotations
import sqlite3
import os
import json
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
                option_security_id TEXT
            );
            """)

            # Auto-migrate table if column does not exist
            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN option_security_id TEXT;")
            except sqlite3.OperationalError:
                pass  # Column already exists

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
            conn.commit()

    def upsert_position(self, pos: PaperPosition):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO positions (
                id, signal_id, symbol, option_type, strike_symbol, timeframe, setup_type,
                entry_time, underlying_entry, underlying_sl, underlying_target_1, underlying_target_2,
                option_entry, option_sl, option_target_1, option_target_2,
                lot_size, lots, quantity, current_underlying, current_option_price,
                pnl_points, pnl_rupees, status, exit_time, exit_reason,
                initial_lots, initial_quantity, booked_lots, booked_pnl_rupees,
                option_security_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                lots=excluded.lots,
                quantity=excluded.quantity,
                current_underlying=excluded.current_underlying,
                current_option_price=excluded.current_option_price,
                pnl_points=excluded.pnl_points,
                pnl_rupees=excluded.pnl_rupees,
                status=excluded.status,
                exit_time=excluded.exit_time,
                exit_reason=excluded.exit_reason,
                booked_lots=excluded.booked_lots,
                booked_pnl_rupees=excluded.booked_pnl_rupees,
                option_security_id=COALESCE(excluded.option_security_id, positions.option_security_id);
            """, (
                pos.id, pos.signal_id, pos.symbol, pos.option_type, pos.strike_symbol, pos.timeframe, pos.setup_type,
                pos.entry_time, pos.underlying_entry, pos.underlying_sl, pos.underlying_target_1, pos.underlying_target_2,
                pos.option_entry, pos.option_sl, pos.option_target_1, pos.option_target_2,
                pos.lot_size, pos.lots, pos.quantity, pos.current_underlying, pos.current_option_price,
                pos.pnl_points, pos.pnl_rupees, pos.status, pos.exit_time, pos.exit_reason,
                pos.initial_lots, pos.initial_quantity, pos.booked_lots, pos.booked_pnl_rupees,
                pos.option_security_id
            ))
            conn.commit()

    def load_all_positions(self):
        """Returns (active_positions, closed_trades)."""
        from app.services.paper_trader import PaperPosition
        active: list[PaperPosition] = []
        closed: list[PaperPosition] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions ORDER BY entry_time ASC;")
            rows = cursor.fetchall()
            for row in rows:
                d = dict(row)
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

    def clear_all(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions;")
            cursor.execute("DELETE FROM processed_signals;")
            conn.commit()
