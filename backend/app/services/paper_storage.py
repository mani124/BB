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
                charges_json TEXT DEFAULT ''
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
            conn.commit()

    def upsert_position(self, pos: PaperPosition):
        charges_json = json.dumps(pos.charges_breakdown) if pos.charges_breakdown else ""
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
                option_security_id, feed_mode,
                theoretical_entry, entry_slippage, theoretical_exit, exit_slippage,
                total_slippage_cost, gross_pnl, total_charges, net_pnl, charges_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                option_security_id=COALESCE(excluded.option_security_id, positions.option_security_id),
                feed_mode=excluded.feed_mode,
                theoretical_entry=excluded.theoretical_entry,
                entry_slippage=excluded.entry_slippage,
                theoretical_exit=excluded.theoretical_exit,
                exit_slippage=excluded.exit_slippage,
                total_slippage_cost=excluded.total_slippage_cost,
                gross_pnl=excluded.gross_pnl,
                total_charges=excluded.total_charges,
                net_pnl=excluded.net_pnl,
                charges_json=excluded.charges_json;
            """, (
                pos.id, pos.signal_id, pos.symbol, pos.option_type, pos.strike_symbol, pos.timeframe, pos.setup_type,
                pos.entry_time, pos.underlying_entry, pos.underlying_sl, pos.underlying_target_1, pos.underlying_target_2,
                pos.option_entry, pos.option_sl, pos.option_target_1, pos.option_target_2,
                pos.lot_size, pos.lots, pos.quantity, pos.current_underlying, pos.current_option_price,
                pos.pnl_points, pos.pnl_rupees, pos.status, pos.exit_time, pos.exit_reason,
                pos.initial_lots, pos.initial_quantity, pos.booked_lots, pos.booked_pnl_rupees,
                pos.option_security_id, getattr(pos, "feed_mode", "demo"),
                pos.theoretical_entry, pos.entry_slippage, pos.theoretical_exit, pos.exit_slippage,
                pos.total_slippage_cost, pos.gross_pnl, pos.total_charges, pos.net_pnl, charges_json
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
