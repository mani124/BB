"""Paper-trading book for daily-timeframe swing equity setups (Setup 15: ATR trend flip).

Pieces:
* ``SwingStore``        positions, run state and cached daily bars in the trades database.
* ``DhanDailyProvider`` daily candles for the F&O stock universe from the Dhan client already used by the scanner.
* ``SwingEngine``       once per trading day, after the daily bar is final: fills queued entries at the open, manages open
                        positions, then scans the close for new signals. ``process_day`` is the whole day and is also what the
                        replay script (``scripts/swing_backtest.py``) calls, so a backtest runs the production rules.

Everything is simulated from daily OHLC bars (paper only, long only, cash delivery). The rules that keep the simulation honest:
a signal read on the close of day t fills at the open of day t+1 plus slippage; a stop that is gapped through fills at the
open, not the stop; when a stop and a target could both be inside one bar the stop is assumed to hit first; exits decided on
a close (trend flip, time stop) fill at the next open.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import pandas as pd

from app.services import db, market_hours
from app.services import swing_signals as sg
from app.services.charges_calculator import calculate_equity_delivery_charges
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry

logger = logging.getLogger(__name__)
BOOK = "swing"
HISTORY_CALENDAR_DAYS = 560  # first fetch: enough for a 200-day average plus the Supertrend window
MAX_CATCH_UP_DAYS = 30  # missed days are replayed in order so stops on them are still checked
BAR_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _day(d: Any) -> str:
    return str(d)[:10]


def _hhmm_minutes(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# ============================================================================================ store
class SwingStore:
    def __init__(self, db_path: Optional[str]):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._mem_pos: dict[str, dict] = {}
        self._mem_meta: dict[str, str] = {}
        self._mem_bars: dict[str, pd.DataFrame] = {}
        if db_path:
            with self._conn() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS swing_positions (
                    id TEXT PRIMARY KEY, symbol TEXT, setup TEXT, status TEXT, signal_day TEXT, opened_day TEXT, body TEXT)""")
                c.execute("CREATE TABLE IF NOT EXISTS swing_meta (key TEXT PRIMARY KEY, value TEXT)")
                c.execute("""CREATE TABLE IF NOT EXISTS swing_daily_bars (
                    symbol TEXT NOT NULL, day TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL,
                    PRIMARY KEY (symbol, day))""")

    def _conn(self) -> sqlite3.Connection:
        c = db.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # ---- positions ----
    def save_position(self, pos: dict) -> None:
        with self._lock:
            if not self.db_path:
                self._mem_pos[pos["id"]] = json.loads(json.dumps(pos))
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO swing_positions (id, symbol, setup, status, signal_day, opened_day, body) VALUES (?,?,?,?,?,?,?)",
                          (pos["id"], pos["symbol"], pos.get("setup", ""), pos["status"], pos.get("signal_day", ""),
                           pos.get("opened_day", ""), json.dumps(pos)))

    def positions(self) -> list[dict]:
        with self._lock:
            if not self.db_path:
                rows = [json.loads(json.dumps(p)) for p in self._mem_pos.values()]
            else:
                with self._conn() as c:
                    rows = [json.loads(r["body"]) for r in c.execute("SELECT body FROM swing_positions")]
        return sorted(rows, key=lambda p: (p.get("signal_day", ""), p["id"]))

    # ---- run state ----
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            if not self.db_path:
                return self._mem_meta.get(key)
            with self._conn() as c:
                r = c.execute("SELECT value FROM swing_meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            if not self.db_path:
                self._mem_meta[key] = value
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO swing_meta (key, value) VALUES (?,?)", (key, value))

    # ---- daily bars cache ----
    def upsert_bars(self, symbol: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        with self._lock:
            if not self.db_path:
                old = self._mem_bars.get(symbol)
                merged = pd.concat([old, df]) if old is not None else df
                self._mem_bars[symbol] = merged.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
                return
            rows = [(symbol, _day(r.date), float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume or 0))
                    for r in df.itertuples()]
            with self._conn() as c:
                c.executemany("INSERT OR REPLACE INTO swing_daily_bars (symbol, day, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)", rows)

    def bars(self, symbol: str) -> pd.DataFrame:
        with self._lock:
            if not self.db_path:
                df = self._mem_bars.get(symbol)
                return df.copy() if df is not None else pd.DataFrame(columns=BAR_COLUMNS)
            with self._conn() as c:
                rows = c.execute("SELECT day, open, high, low, close, volume FROM swing_daily_bars WHERE symbol = ? ORDER BY day", (symbol,)).fetchall()
        return pd.DataFrame([tuple(r) for r in rows], columns=BAR_COLUMNS)

    def last_bar_day(self, symbol: str) -> Optional[str]:
        df = self.bars(symbol)
        return _day(df["date"].iloc[-1]) if len(df) else None


# ============================================================================================ data
class DhanDailyProvider:
    """Daily candles from Dhan, cached in the swing store. Stocks and security ids come from app/data/fno_universe.json."""

    def __init__(self, dhan_client: Any, get_credentials: Callable[[], Optional[tuple[str, str]]], store: SwingStore,
                 universe_path: Optional[str] = None):
        self.dhan = dhan_client
        self.get_credentials = get_credentials
        self.store = store
        self.universe_path = universe_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fno_universe.json")
        self._universe: Optional[dict] = None

    def _load(self) -> dict:
        if self._universe is None:
            try:
                with open(self.universe_path) as f:
                    self._universe = json.load(f)
            except (OSError, ValueError):
                self._universe = {}
        return self._universe

    def has_credentials(self) -> bool:
        return bool(self.get_credentials())

    def symbols(self) -> list[str]:
        return sorted(self._load())

    async def bars(self, symbols: list[str], today: date) -> dict[str, pd.DataFrame]:
        """Refresh the cache for ``symbols`` up to ``today`` and return each symbol's full cached history."""
        creds = self.get_credentials()
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            inst = self._load().get(sym.upper())
            if inst and creds:
                last = self.store.last_bar_day(sym)
                start = (datetime.strptime(last, "%Y-%m-%d").date() - timedelta(days=3)) if last else today - timedelta(days=HISTORY_CALENDAR_DAYS)
                try:
                    fresh = await self.dhan.fetch_daily_candles(
                        creds[0], creds[1], str(inst["security_id"]), inst.get("exchange_segment", "NSE_EQ"),
                        inst.get("instrument_type", "EQUITY"), start.isoformat(), today.isoformat())
                except Exception:
                    logger.warning("daily candles failed for %s", sym, exc_info=True)
                    fresh = None
                if fresh is not None and not fresh.empty:
                    self.store.upsert_bars(sym, fresh)
            out[sym] = self.store.bars(sym)
        return out


# ============================================================================================ engine
class SwingEngine:
    def __init__(self, db_path: Optional[str], runtime: RuntimeSettings, telemetry: Telemetry,
                 provider: Optional[DhanDailyProvider] = None, kill_switch: Optional[Callable[[], bool]] = None,
                 earnings_dates: Optional[Callable[[str], list]] = None):
        self.store = provider.store if provider is not None else SwingStore(db_path)
        self.runtime = runtime
        self.telemetry = telemetry
        self.provider = provider
        self.kill_switch = kill_switch or (lambda: False)
        self.earnings_dates = earnings_dates
        self._lock = asyncio.Lock()
        self.last_cycle: dict = {"status": "never_run"}

    # ---------------------------------------------------------------- config
    def signal_cfg(self) -> sg.Setup15Config:
        g = self.runtime.get
        return sg.Setup15Config(atr_period=int(g("swing_atr_period")), atr_mult=float(g("swing_atr_mult")),
                                sma_filter_days=int(g("swing_sma_filter_days")), min_price=float(g("swing_min_price")),
                                min_avg_volume=float(g("swing_min_avg_volume")))

    def _slip(self) -> float:
        return float(self.runtime.get("swing_slippage_bps")) / 10000.0

    def _log(self, decision: str, symbol: str, reason: str, metrics: Optional[dict] = None, pos_id: Optional[str] = None) -> None:
        self.telemetry.decision(book=BOOK, strategy=sg.SETUP_15, symbol=symbol, decision=decision, reason=reason,
                                metrics=metrics or {}, position_id=pos_id)

    def _charges(self, entry: float, exit_px: float, qty: int) -> float:
        g = self.runtime.get
        return calculate_equity_delivery_charges(entry, exit_px, qty, brokerage_per_order=float(g("swing_brokerage_per_order")),
                                                 dp_charge=float(g("swing_dp_charge"))).total_charges

    # ---------------------------------------------------------------- reads
    def positions(self, status: Optional[str] = None) -> list[dict]:
        return [p for p in self.store.positions() if status is None or p["status"] == status]

    def summary(self) -> dict:
        allp = self.store.positions()
        closed = [p for p in allp if p["status"] == "CLOSED"]
        opens = [p for p in allp if p["status"] == "OPEN"]
        pending = [p for p in allp if p["status"] == "PENDING"]
        start = float(self.runtime.get("swing_starting_capital"))
        pnls = [p.get("net_pnl", 0.0) for p in closed]
        wins, losses = [x for x in pnls if x > 0], [x for x in pnls if x < 0]
        realized = sum(pnls)
        unreal = sum(p.get("unrealized_net", 0.0) for p in opens)
        return {
            "starting_capital": start, "realized_net_pnl": round(realized, 2), "unrealized_net_pnl": round(unreal, 2),
            "equity": round(start + realized + unreal, 2), "open_positions": len(opens), "pending_entries": len(pending),
            "closed_trades": len(closed), "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "total_charges": round(sum(p.get("charges", 0.0) for p in closed), 2),
            "enabled": bool(self.runtime.get("swing_enabled")), "last_processed_day": self.store.get_meta("last_processed_day"),
            "last_cycle": self.last_cycle,
        }

    # ---------------------------------------------------------------- entry gate
    def entry_block(self, symbol: str, day: date, live_positions: list[dict], queued_today: int) -> Optional[tuple[str, str]]:
        """(code, detail) if the book refuses a new entry in ``symbol`` from the close of ``day``, else None."""
        g = self.runtime.get
        if not g("swing_enabled"):
            return "SWING_DISABLED", "swing book is switched off"
        if not g("swing_setup15_enabled"):
            return "SETUP_OFF", "Setup 15 is switched off"
        if self.kill_switch():
            return "KILL_SWITCH", "kill switch is engaged"
        if any(p["symbol"] == symbol for p in live_positions):
            return "ALREADY_HELD", f"{symbol} already has an open or queued swing position"
        if len(live_positions) + queued_today >= int(g("swing_max_positions")):
            return "MAX_OPEN_POSITIONS", f"{len(live_positions) + queued_today} open or queued (limit {g('swing_max_positions')})"
        per_day = int(g("swing_max_new_per_day"))
        if per_day > 0 and queued_today >= per_day:
            return "MAX_NEW_PER_DAY", f"{queued_today} entries queued from this close (limit {per_day})"
        blackout = int(g("swing_earnings_blackout_days"))
        if blackout > 0 and self.earnings_dates:
            try:
                for d in self.earnings_dates(symbol):
                    gap = (datetime.strptime(_day(d), "%Y-%m-%d").date() - day).days
                    if 0 <= gap <= blackout:
                        return "EARNINGS_BLACKOUT", f"results on {_day(d)}, {gap} days away (blackout {blackout})"
            except Exception:
                logger.warning("earnings calendar lookup failed for %s", symbol, exc_info=True)
        return None

    # ---------------------------------------------------------------- one trading day
    def process_day(self, day: date, bars: dict[str, pd.DataFrame], scan: bool = True) -> dict:
        """Run one finished trading day. ``bars`` holds each symbol's daily history; rows after ``day`` are ignored.

        Order: fill queued entries at the open, check stops, decide exits on the close, trail stops, then scan the close
        for new signals (queued for the next open)."""
        ds = _day(day)
        res: dict = {"day": ds, "filled": [], "closed": [], "queued": [], "cancelled": [], "skipped": 0}
        hist: dict[str, pd.DataFrame] = {}

        def history(sym: str) -> Optional[pd.DataFrame]:
            if sym not in hist:
                df = bars.get(sym)
                if df is None or df.empty:
                    hist[sym] = None
                else:
                    d = df[df["date"].astype(str).str[:10] <= ds]
                    hist[sym] = d.reset_index(drop=True) if len(d) and _day(d["date"].iloc[-1]) == ds else None
            return hist[sym]

        slip = self._slip()
        cfg = self.signal_cfg()
        max_hold = int(self.runtime.get("swing_max_hold_days"))
        close_mode = self.runtime.get("swing_exit_mode") == "close"
        loss_pct = float(self.runtime.get("swing_close_mode_max_loss_pct")) / 100.0
        for pos in self.store.positions():
            if pos["status"] not in ("PENDING", "OPEN"):
                continue
            df = history(pos["symbol"])
            if df is None:
                self._log("HELD", pos["symbol"], "NO_BAR_TODAY", {"day": ds}, pos["id"])
                continue
            bar = df.iloc[-1]
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            just_filled = False
            if pos["status"] == "PENDING":
                if pos["signal_day"] >= ds:
                    continue  # queued from this very close: fills on the next trading day
                entry = round(o * (1 + slip), 2)
                if o <= pos["stop"]:
                    self._cancel(pos, ds, "GAP_THROUGH_STOP", {"open": o, "stop": pos["stop"]})
                    res["cancelled"].append(pos["id"])
                    continue
                hard_stop = round(entry * (1 - loss_pct), 2)
                risk = entry - (max(pos["stop"], hard_stop) if close_mode else pos["stop"])
                qty = min(int(float(self.runtime.get("swing_risk_per_trade")) // risk) if risk > 0 else 0,
                          int(float(self.runtime.get("swing_max_capital_per_trade")) // entry))
                if qty < 1:
                    self._cancel(pos, ds, "SIZE_BELOW_ONE_SHARE", {"entry": entry, "stop": pos["stop"]})
                    res["cancelled"].append(pos["id"])
                    continue
                pos.update(status="OPEN", opened_day=ds, entry_price=entry, qty=qty, initial_stop=pos["stop"], hard_stop=hard_stop, hold_days=0,
                           mfe_pct=0.0, mae_pct=0.0, exit_pending=None, last_close=entry, unrealized_net=0.0)
                self._log("ENTERED", pos["symbol"], "SIGNAL_CONFIRMED",
                          {"entry": entry, "qty": qty, "stop": pos["stop"], "open": o, "signal_day": pos["signal_day"]}, pos["id"])
                res["filled"].append(pos["id"])
                just_filled = True
            # ---- exits that fire inside today's bar
            exit_px, reason = None, None
            level = pos["hard_stop"] if close_mode else pos["stop"]  # in close mode the Supertrend line only triggers a next-open exit
            if pos.get("exit_pending") and not just_filled:
                exit_px, reason = o, pos["exit_pending"]
            elif o <= level and not just_filled:
                exit_px, reason = o, "STOP_GAP"
            elif l <= level:
                exit_px, reason = level, "STOP"
            if exit_px is not None:
                self._close(pos, ds, round(exit_px * (1 - slip), 2), reason)
                res["closed"].append(pos["id"])
                continue
            # ---- still open at the close: mark, trail, decide tomorrow's exit
            pos["hold_days"] = int(pos.get("hold_days", 0)) + (0 if just_filled else 1)
            pos["last_close"] = c
            pos["mfe_pct"] = round(max(pos.get("mfe_pct", 0.0), (h / pos["entry_price"] - 1) * 100), 3)
            pos["mae_pct"] = round(min(pos.get("mae_pct", 0.0), (l / pos["entry_price"] - 1) * 100), 3)
            trend, line = sg.trend_state(df, cfg)
            if trend == 1 and not math.isnan(line) and line > pos["stop"]:
                pos["stop"] = round(line, 2)
            if trend == -1:
                pos["exit_pending"] = "TREND_FLIP"
            elif max_hold > 0 and pos["hold_days"] >= max_hold:
                pos["exit_pending"] = "TIME_STOP"
            pos["unrealized_net"] = round((c * (1 - slip) - pos["entry_price"]) * pos["qty"]
                                          - self._charges(pos["entry_price"], c, pos["qty"]), 2)
            self.store.save_position(pos)
        if scan:
            self._scan(day, bars, history, res)
        return res

    def _cancel(self, pos: dict, ds: str, reason: str, metrics: dict) -> None:
        pos.update(status="CANCELLED", closed_day=ds, exit_reason=reason, net_pnl=0.0)
        self.store.save_position(pos)
        self._log("SKIPPED", pos["symbol"], reason, metrics, pos["id"])

    def _close(self, pos: dict, ds: str, exit_px: float, reason: str) -> None:
        gross = round((exit_px - pos["entry_price"]) * pos["qty"], 2)
        charges = self._charges(pos["entry_price"], exit_px, pos["qty"])
        net = round(gross - charges, 2)
        risk_unit = pos["entry_price"] - (max(pos.get("initial_stop", pos["stop"]), pos.get("hard_stop", 0.0))
                                          if self.runtime.get("swing_exit_mode") == "close" else pos.get("initial_stop", pos["stop"]))
        pos.update(status="CLOSED", closed_day=ds, exit_price=exit_px, exit_reason=reason, gross_pnl=gross, charges=charges,
                   net_pnl=net, unrealized_net=0.0, exit_pending=None,
                   r_multiple=round((exit_px - pos["entry_price"]) / risk_unit, 3) if risk_unit > 0 else 0.0,
                   return_pct=round((exit_px / pos["entry_price"] - 1) * 100, 3))
        self.store.save_position(pos)
        self._log("EXITED", pos["symbol"], reason, {"gross_pnl": gross, "net_pnl": net, "charges": charges, "hold_days": pos.get("hold_days"),
                                                     "mfe_pct": pos.get("mfe_pct"), "mae_pct": pos.get("mae_pct")}, pos["id"])

    def _scan(self, day: date, bars: dict[str, pd.DataFrame], history: Callable, res: dict) -> None:
        cfg = self.signal_cfg()
        ds = _day(day)
        signals: list[sg.Setup15Signal] = []
        for sym in sorted(bars):
            df = history(sym)
            if df is None:
                continue
            sig = sg.evaluate_setup15(sym, df, cfg)
            if sig is not None:
                signals.append(sig)
        signals.sort(key=lambda s: (-s.rank_return, s.symbol))  # momentum tie-break when flips outnumber free slots
        live = [p for p in self.store.positions() if p["status"] in ("PENDING", "OPEN")]
        queued = 0
        for sig in signals:
            block = self.entry_block(sig.symbol, day, live, queued)
            if block:
                res["skipped"] += 1
                self._log("SKIPPED", sig.symbol, block[0], {**sig.as_dict(), "detail": block[1]})
                continue
            pos = {"id": f"SWG_{sig.symbol}_{uuid.uuid4().hex[:8]}", "symbol": sig.symbol, "setup": sg.SETUP_15, "status": "PENDING",
                   "signal_day": ds, "stop": round(sig.stop, 2), "signal_close": sig.close, "signal": sig.as_dict()}
            self.store.save_position(pos)
            queued += 1
            res["queued"].append(pos["id"])
            self._log("QUEUED", sig.symbol, "SIGNAL", sig.as_dict(), pos["id"])

    # ---------------------------------------------------------------- live cycle
    async def run_cycle(self, now: Optional[datetime] = None) -> dict:
        """Look for finished trading days we have not processed yet and run them."""
        async with self._lock:
            now = now or market_hours.now_ist()
            today = now.date()
            result: dict = {"at": now.isoformat(), "status": "ok", "days": []}
            try:
                if self.provider is None or not self.provider.has_credentials():
                    result["status"] = "no_credentials"
                    if any(p["status"] in ("OPEN", "PENDING") for p in self.store.positions()):
                        from app.services import notifier  # open positions are unmanaged until someone logs in again
                        notifier.notify("swing_unmanaged", "Swing positions are open but no broker session is connected, so they are not being managed. Log in to the dashboard.",
                                        dedupe_key="swing_unmanaged", min_interval=6 * 3600)
                elif not market_hours.is_trading_day(today):
                    result["status"] = "not_a_trading_day"
                elif now.hour * 60 + now.minute < _hhmm_minutes(self.runtime.get("swing_scan_time")):
                    result["status"] = "before_scan_time"
                elif self.store.get_meta("last_processed_day") == today.isoformat():
                    result["status"] = "up_to_date"
                else:
                    await self._catch_up(today, result)
            except Exception as exc:
                logger.warning("Swing cycle failed: %s", exc, exc_info=True)
                result["status"] = "error"
                result["error"] = str(exc)
            self.last_cycle = result
            return result

    async def _catch_up(self, today: date, result: dict) -> None:
        live = [p for p in self.store.positions() if p["status"] in ("PENDING", "OPEN")]
        enabled = bool(self.runtime.get("swing_enabled")) and bool(self.runtime.get("swing_setup15_enabled"))
        symbols = self.provider.symbols() if enabled else sorted({p["symbol"] for p in live})
        if not symbols:
            result["status"] = "nothing_to_do"
            return
        bars = await self.provider.bars(symbols, today)
        # a day counts as available once at least half of the requested symbols have its bar
        counts: dict[str, int] = {}
        for df in bars.values():
            for d in df["date"].astype(str).str[:10].tail(MAX_CATCH_UP_DAYS + 10):
                counts[d] = counts.get(d, 0) + 1
        available = sorted(d for d, n in counts.items() if n * 2 >= len(bars) and d <= today.isoformat())
        last = self.store.get_meta("last_processed_day")
        days = [d for d in available if last is None or d > last]
        if last is None:
            days = [d for d in days if d == today.isoformat()]  # first run starts today: no replay of the past
        if not days:
            result["status"] = "no_new_bar"
            return
        if len(days) > MAX_CATCH_UP_DAYS:
            logger.warning("Swing book is %d trading days behind; processing the last %d", len(days), MAX_CATCH_UP_DAYS)
            days = days[-MAX_CATCH_UP_DAYS:]
        for d in days:
            r = self.process_day(datetime.strptime(d, "%Y-%m-%d").date(), bars, scan=enabled and d == days[-1])
            result["days"].append(r)
            self.store.set_meta("last_processed_day", d)

    async def preview(self, today: Optional[date] = None) -> list[dict]:
        """Signals on the latest finished bar and whether the book would take them. Nothing is queued or logged."""
        if self.provider is None or not self.provider.has_credentials():
            return []
        today = today or market_hours.now_ist().date()
        bars = await self.provider.bars(self.provider.symbols(), today)
        cfg = self.signal_cfg()
        latest = max((_day(df["date"].iloc[-1]) for df in bars.values() if len(df)), default=None)
        if latest is None:
            return []
        day = datetime.strptime(latest, "%Y-%m-%d").date()
        live = [p for p in self.store.positions() if p["status"] in ("PENDING", "OPEN")]
        rows, queued = [], 0
        sigs = []
        for sym, df in sorted(bars.items()):
            d = df[df["date"].astype(str).str[:10] <= latest].reset_index(drop=True)
            if len(d) and _day(d["date"].iloc[-1]) == latest:
                s = sg.evaluate_setup15(sym, d, cfg)
                if s:
                    sigs.append(s)
        for s in sorted(sigs, key=lambda x: (-x.rank_return, x.symbol)):
            block = self.entry_block(s.symbol, day, live, queued)
            rows.append({**s.as_dict(), "ready": block is None, "code": block[0] if block else "READY", "detail": block[1] if block else ""})
            if block is None:
                queued += 1
        return rows

    async def square_off_all(self, reason: str = "KILL_SWITCH") -> int:
        """Close every open position at the last close (paper) and cancel queued entries."""
        async with self._lock:
            ds = market_hours.now_ist().date().isoformat()
            slip, n = self._slip(), 0
            for pos in self.store.positions():
                if pos["status"] == "OPEN":
                    self._close(pos, ds, round(pos.get("last_close", pos["entry_price"]) * (1 - slip), 2), reason)
                    n += 1
                elif pos["status"] == "PENDING":
                    self._cancel(pos, ds, reason, {})
            return n
