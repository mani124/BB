"""Paper-trading book for the stock earnings options strategy.

Pieces:
* ``EarningsStore``       calendar, IV history and positions in the trades database.
* ``DhanChainProvider``   spot, expiries and option chains from the Dhan client already used by the scanner.
* ``EarningsEngine``      scans the calendar, applies the RMS gates, opens and marks paper positions, exits them by rule.

Only paper orders exist here: positions are simulated at the bid / ask from the live chain. Every limit comes from the
runtime settings, and every decision is written to the telemetry decision trail (book "earnings").
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional, Protocol

from app.services import earnings_strategy as es
from app.services import market_hours
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry
from app.services import db

logger = logging.getLogger(__name__)
BOOK = "earnings"
SYNC_RETRY_BACKOFF_S = 30 * 60  # after a failed NSE sync, wait this long before asking again


def _hhmm_minutes(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _d(s: Any) -> date:
    return s if isinstance(s, date) and not isinstance(s, datetime) else datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


# ============================================================================================ store
class EarningsStore:
    def __init__(self, db_path: Optional[str]):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._mem_calendar: dict[tuple[str, str], dict] = {}
        self._mem_iv: dict[str, dict[str, float]] = {}
        self._mem_pos: dict[str, dict] = {}
        if db_path:
            with self._conn() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS earnings_calendar (
                    symbol TEXT NOT NULL, earnings_date TEXT NOT NULL, session TEXT DEFAULT '', sector TEXT DEFAULT '',
                    note TEXT DEFAULT '', PRIMARY KEY (symbol, earnings_date))""")
                for ddl in ("ALTER TABLE earnings_calendar ADD COLUMN source TEXT DEFAULT 'manual'",
                            "ALTER TABLE earnings_calendar ADD COLUMN session_source TEXT DEFAULT ''"):
                    try:
                        c.execute(ddl)
                    except sqlite3.OperationalError:
                        pass
                c.execute("CREATE TABLE IF NOT EXISTS earnings_meta (key TEXT PRIMARY KEY, value TEXT)")
                c.execute("""CREATE TABLE IF NOT EXISTS earnings_iv_history (
                    symbol TEXT NOT NULL, day TEXT NOT NULL, iv REAL NOT NULL, spot REAL, PRIMARY KEY (symbol, day))""")
                c.execute("""CREATE TABLE IF NOT EXISTS earnings_positions (
                    id TEXT PRIMARY KEY, symbol TEXT, mode TEXT, status TEXT, earnings_date TEXT, opened_at TEXT, body TEXT)""")

    def _conn(self) -> sqlite3.Connection:
        c = db.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # ---- calendar ----
    def upsert_calendar(self, symbol: str, earnings_date: str, session: str = "", sector: str = "", note: str = "",
                        source: str = "manual", session_source: Optional[str] = None) -> dict:
        row = {"symbol": symbol.strip().upper(), "earnings_date": _d(earnings_date).isoformat(),
               "session": (session or "").strip().upper(), "sector": sector.strip(), "note": note.strip(), "source": source}
        # A session typed in by hand is "manual" and always wins; the NSE sync passes "inferred".
        row["session_source"] = (session_source if session_source is not None else "manual") if row["session"] else ""
        if row["session"] not in ("", *es.SESSIONS):
            raise ValueError("session must be BMO, AMC or empty")
        if not row["symbol"]:
            raise ValueError("symbol is required")
        with self._lock:
            if not self.db_path:
                self._mem_calendar[(row["symbol"], row["earnings_date"])] = row
            else:
                with self._conn() as c:
                    c.execute("INSERT OR REPLACE INTO earnings_calendar (symbol, earnings_date, session, sector, note, source, session_source) VALUES (?,?,?,?,?,?,?)",
                              (row["symbol"], row["earnings_date"], row["session"], row["sector"], row["note"], row["source"], row["session_source"]))
        return row

    def sync_rows(self, rows: list[dict], today: date, horizon_days: int) -> dict:
        """Apply NSE rows: add new ones (source NSE), update the date of NSE rows that moved, never touch manual rows.
        Returns counts. NSE rows in the window that NSE no longer lists are removed (the meeting was cancelled or moved)."""
        added = removed = 0
        keep = {(r["symbol"], r["earnings_date"]) for r in rows}
        with self._lock:
            existing = self.calendar(today)
            manual = {(r["symbol"], r["earnings_date"]) for r in existing if r.get("source", "manual") != "NSE"}
            for r in rows:
                key = (r["symbol"], r["earnings_date"])
                if key in manual:
                    continue
                inferred = r.get("session", "")
                old = next((e for e in existing if (e["symbol"], e["earnings_date"]) == key), None)
                if old is not None:
                    # An NSE row keeps its session unless it was set by hand; a newly inferred session refreshes it.
                    if inferred and old.get("session_source") != "manual" and old.get("session") != inferred:
                        self.upsert_calendar(old["symbol"], old["earnings_date"], inferred, old.get("sector", ""),
                                             r.get("note", old.get("note", "")), source="NSE", session_source="inferred")
                    continue
                self.upsert_calendar(r["symbol"], r["earnings_date"], inferred, "", r.get("note", ""), source="NSE",
                                     session_source="inferred")
                added += 1
            limit = (today + timedelta(days=horizon_days)).isoformat()
            for e in existing:
                if e.get("source") == "NSE" and e["earnings_date"] <= limit and (e["symbol"], e["earnings_date"]) not in keep:
                    self.delete_calendar(e["symbol"], e["earnings_date"])
                    removed += 1
        return {"added": added, "removed": removed, "listed": len(rows)}

    def get_meta(self, key: str) -> Optional[str]:
        if not self.db_path:
            return getattr(self, "_mem_meta", {}).get(key)
        with self._conn() as c:
            r = c.execute("SELECT value FROM earnings_meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        if not self.db_path:
            self.__dict__.setdefault("_mem_meta", {})[key] = value
            return
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO earnings_meta (key, value) VALUES (?,?)", (key, value))

    def delete_calendar(self, symbol: str, earnings_date: str) -> bool:
        key = (symbol.strip().upper(), _d(earnings_date).isoformat())
        with self._lock:
            if not self.db_path:
                return self._mem_calendar.pop(key, None) is not None
            with self._conn() as c:
                return c.execute("DELETE FROM earnings_calendar WHERE symbol = ? AND earnings_date = ?", key).rowcount > 0

    def calendar(self, from_date: Optional[date] = None) -> list[dict]:
        with self._lock:
            if not self.db_path:
                rows = list(self._mem_calendar.values())
            else:
                with self._conn() as c:
                    rows = [dict(r) for r in c.execute("SELECT * FROM earnings_calendar ORDER BY earnings_date, symbol")]
        if from_date:
            rows = [r for r in rows if r["earnings_date"] >= from_date.isoformat()]
        for r in rows:
            r["session_source"] = r.get("session_source") or ("manual" if r.get("session") else "")
        return sorted(rows, key=lambda r: (r["earnings_date"], r["symbol"]))

    # ---- IV history ----
    def record_iv(self, symbol: str, day: date, iv: float, spot: float = 0.0) -> None:
        if iv <= 0:
            return
        with self._lock:
            if not self.db_path:
                self._mem_iv.setdefault(symbol, {})[day.isoformat()] = iv
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO earnings_iv_history (symbol, day, iv, spot) VALUES (?,?,?,?)",
                          (symbol, day.isoformat(), float(iv), float(spot or 0)))

    def has_iv(self, symbol: str, day: date) -> bool:
        with self._lock:
            if not self.db_path:
                return day.isoformat() in self._mem_iv.get(symbol, {})
            with self._conn() as c:
                return c.execute("SELECT 1 FROM earnings_iv_history WHERE symbol=? AND day=?", (symbol, day.isoformat())).fetchone() is not None

    def iv_history(self, symbol: str, before: date, lookback_days: int) -> list[float]:
        lo = (before - timedelta(days=lookback_days)).isoformat()
        with self._lock:
            if not self.db_path:
                return [v for d, v in sorted(self._mem_iv.get(symbol, {}).items()) if lo <= d < before.isoformat()]
            with self._conn() as c:
                return [r["iv"] for r in c.execute(
                    "SELECT iv FROM earnings_iv_history WHERE symbol=? AND day >= ? AND day < ? ORDER BY day",
                    (symbol, lo, before.isoformat()))]

    # ---- positions ----
    def save_position(self, pos: dict, *, entry_evidence: tuple[dict, dict[str, list[dict]]] | None = None) -> None:
        with self._lock:
            # A cycle holding a stale copy must never turn a closed position back into an open one.
            if pos.get("status") != "CLOSED" and self.position_status(pos["id"]) == "CLOSED":
                return
            if not self.db_path:
                self._mem_pos[pos["id"]] = json.loads(json.dumps(pos, default=str))
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO earnings_positions (id, symbol, mode, status, earnings_date, opened_at, body) VALUES (?,?,?,?,?,?,?)",
                          (pos["id"], pos["symbol"], pos["mode"], pos["status"], pos["earnings_date"], pos["opened_at"],
                           json.dumps(pos, default=str)))
                if entry_evidence is not None:
                    from app.services.dashboard_evidence import save_trade_evidence
                    decision, bars = entry_evidence
                    save_trade_evidence("earnings", pos["id"], decision, bars, connection=c)

    def position_status(self, pos_id: str) -> Optional[str]:
        with self._lock:
            if not self.db_path:
                p = self._mem_pos.get(pos_id)
                return p["status"] if p else None
            with self._conn() as c:
                r = c.execute("SELECT status FROM earnings_positions WHERE id = ?", (pos_id,)).fetchone()
                return r["status"] if r else None

    def positions(self) -> list[dict]:
        with self._lock:
            if not self.db_path:
                return [json.loads(json.dumps(p)) for p in self._mem_pos.values()]
            with self._conn() as c:
                return [json.loads(r["body"]) for r in c.execute("SELECT body FROM earnings_positions ORDER BY opened_at")]

    def clear_positions(self) -> None:
        with self._lock:
            self._mem_pos.clear()
            if self.db_path:
                with self._conn() as c:
                    c.execute("DELETE FROM earnings_positions")


# ============================================================================================ provider
class ChainProvider(Protocol):
    def has_credentials(self) -> bool: ...
    def instrument(self, symbol: str) -> Optional[dict]: ...
    async def spot(self, symbol: str) -> Optional[float]: ...
    async def expiries(self, symbol: str) -> list[date]: ...
    async def chain(self, symbol: str, expiry: date) -> dict: ...


class DhanChainProvider:
    """Chain data from Dhan. The stock universe (security ids, lot sizes) comes from app/data/fno_universe.json."""

    def __init__(self, dhan_client: Any, get_credentials: Callable[[], Optional[tuple[str, str]]], universe_path: Optional[str] = None):
        self.dhan = dhan_client
        self.get_credentials = get_credentials
        self.universe_path = universe_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fno_universe.json")
        self._universe: Optional[dict] = None
        self._expiry_cache: dict[str, tuple[float, list]] = {}  # symbol -> (monotonic ts, raw expiry list)

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

    def instrument(self, symbol: str) -> Optional[dict]:
        return self._load().get(symbol.upper())

    async def spot(self, symbol: str) -> Optional[float]:
        inst, creds = self.instrument(symbol), self.get_credentials()
        if not inst or not creds:
            return None
        res = await self.dhan.fetch_marketfeed_quotes(creds[0], creds[1], {inst["exchange_segment"]: [int(inst["security_id"])]})
        data = res.get("data", res) if isinstance(res.get("data"), dict) else res
        q = (data.get(inst["exchange_segment"]) or {}).get(str(inst["security_id"]))
        try:
            v = float(q.get("last_price", 0)) if q else 0.0
        except (TypeError, ValueError):
            v = 0.0
        return v if v > 0 else None

    async def expiries(self, symbol: str) -> list[date]:
        inst, creds = self.instrument(symbol), self.get_credentials()
        if not inst or not creds:
            return []
        now = time.monotonic()
        cache = self._expiry_cache
        hit = cache.get(symbol.upper())
        if hit and now - hit[0] < (600.0 if hit[1] else 20.0):
            raw = hit[1]
        else:
            raw = await self.dhan.fetch_expiry_list(creds[0], creds[1], int(inst["security_id"]), inst["exchange_segment"])
            cache[symbol.upper()] = (now, raw or [])
        out = []
        for e in raw or []:
            try:
                out.append(_d(e))
            except ValueError:
                continue
        return sorted(out)

    async def chain(self, symbol: str, expiry: date) -> dict:
        inst, creds = self.instrument(symbol), self.get_credentials()
        if not inst or not creds:
            return {}
        return await self.dhan.fetch_option_chain(creds[0], creds[1], int(inst["security_id"]), inst["exchange_segment"],
                                                  expiry.isoformat()) or {}


# ============================================================================================ engine
class EarningsEngine:
    def __init__(self, db_path: Optional[str], runtime: RuntimeSettings, telemetry: Telemetry,
                 provider: Optional[ChainProvider] = None, kill_switch: Optional[Callable[[], bool]] = None,
                 events_fetcher: Optional[Callable[[], Any]] = None, universe: Optional[Callable[[], set]] = None):
        self.events_fetcher = events_fetcher
        self._universe = universe
        self.store = EarningsStore(db_path)
        self.runtime = runtime
        self.telemetry = telemetry
        self.provider = provider
        self.kill_switch = kill_switch or (lambda: False)
        self._lock = asyncio.Lock()
        self.last_cycle: dict = {"status": "never_run"}
        self._last_sync_failure: Optional[float] = None

    # ---------------------------------------------------------------- calendar sync
    def _fno_symbols(self) -> set:
        if self._universe:
            return set(self._universe())
        u = getattr(self.provider, "_load", None)
        return set(u()) if u else set()

    async def sync_calendar(self, today: Optional[date] = None, force: bool = False) -> dict:
        """Fill the calendar from NSE (financial-result board meetings of F&O stocks). Once a day unless forced."""
        from app.services.earnings_calendar_sync import fetch_nse_events, parse_results_rows
        today = today or market_hours.now_ist().date()
        if not force and (not self.runtime.get("earnings_auto_sync") or self.store.get_meta("last_sync") == today.isoformat()):
            return {"status": "skipped"}
        if not force and self._last_sync_failure is not None and time.monotonic() - self._last_sync_failure < SYNC_RETRY_BACKOFF_S:
            return {"status": "skipped"}
        fetch = self.events_fetcher or fetch_nse_events
        try:
            events = await fetch()
            if not events:  # NSE answers [] when it throttles; treating that as truth would wipe the calendar
                raise ValueError("NSE returned no events; keeping the existing calendar")
        except Exception as exc:
            self._last_sync_failure = time.monotonic()
            logger.warning("Earnings calendar sync failed: %s", exc)
            return {"status": "error", "error": str(exc)}
        self._last_sync_failure = None
        horizon = int(self.runtime.get("earnings_sync_horizon_days"))
        rows = parse_results_rows(events, self._fno_symbols(), today, horizon)
        res = self.store.sync_rows(rows, today, horizon)
        self.store.set_meta("last_sync", today.isoformat())
        self.store.set_meta("last_sync_result", json.dumps(res))
        return {"status": "ok", **res}

    def calendar_view(self) -> list[dict]:
        """Calendar rows with the session the engine will use and where it comes from:
        manual (set by hand, wins), inferred (from NSE's event text), default (the setting) or skip (not traded)."""
        policy = self.runtime.get("earnings_default_session")
        out = []
        for r in self.store.calendar():
            eff = es.resolve_session(r["session"], policy)
            origin = r["session_source"] if r["session"] else ("default" if eff else "skip")
            out.append({**r, "effective_session": eff or "", "session_origin": origin})
        return out

    # ---------------------------------------------------------------- config
    def cfg(self) -> dict:
        g = self.runtime.get
        return {
            "far_days": g("earnings_mode_a_far_days"), "near_days": g("earnings_mode_a_near_days"),
            "exit_days_before": g("earnings_mode_a_exit_days_before"), "max_loss_pct": g("earnings_mode_a_max_loss_pct"),
            "max_ivp": g("earnings_mode_a_max_ivp"), "min_ivr": g("earnings_mode_b_min_ivr"),
            "short_steps": g("earnings_condor_short_steps"), "wing_steps": g("earnings_condor_wing_steps"),
            "min_credit": g("earnings_min_condor_credit"), "min_days_to_expiry": g("earnings_min_days_to_expiry"),
            "max_capital": g("earnings_max_capital_per_trade"), "max_spread_pct": g("earnings_max_spread_pct"),
            "iv_min_history": g("earnings_iv_min_history"), "iv_missing_policy": g("earnings_iv_missing_policy"),
        }

    def _log(self, decision: str, mode: str, symbol: str, reason: str, metrics: Optional[dict] = None, pos_id: Optional[str] = None):
        self.telemetry.decision(book=BOOK, strategy=mode, symbol=symbol, decision=decision, reason=reason,
                                metrics=metrics or {}, position_id=pos_id)

    # ---------------------------------------------------------------- reads
    def positions(self, status: Optional[str] = None) -> list[dict]:
        rows = self.store.positions()
        return [p for p in rows if status is None or p["status"] == status]

    def day_pnl(self, today: date) -> float:
        total = 0.0
        for p in self.store.positions():
            if p["status"] == "CLOSED" and str(p.get("closed_at", ""))[:10] == today.isoformat():
                total += p.get("net_pnl", 0.0)
            elif p["status"] == "OPEN":
                total += p.get("unrealized_net", 0.0)
        return round(total, 2)

    def consecutive_losses_today(self, today: date) -> int:
        closed = sorted((p for p in self.store.positions() if p["status"] == "CLOSED" and str(p.get("closed_at", ""))[:10] == today.isoformat()),
                        key=lambda p: p["closed_at"], reverse=True)
        run = 0
        for p in closed:
            if p.get("net_pnl", 0.0) < 0:
                run += 1
            else:
                break
        return run

    def summary(self) -> dict:
        closed = [p for p in self.store.positions() if p["status"] == "CLOSED"]
        opens = [p for p in self.store.positions() if p["status"] == "OPEN"]
        start = float(self.runtime.get("earnings_starting_capital"))
        pnls = [p.get("net_pnl", 0.0) for p in closed]
        wins = [x for x in pnls if x > 0]
        losses = [x for x in pnls if x < 0]
        by_mode: dict[str, dict] = {}
        for m in (es.MODE_A, es.MODE_B):
            ps = [p.get("net_pnl", 0.0) for p in closed if p["mode"] == m]
            by_mode[m] = {"trades": len(ps), "net_pnl": round(sum(ps), 2),
                          "win_rate": round(sum(1 for x in ps if x > 0) / len(ps) * 100, 1) if ps else 0.0}
        realized = sum(pnls)
        unreal = sum(p.get("unrealized_net", 0.0) for p in opens)
        return {
            "starting_capital": start, "realized_net_pnl": round(realized, 2), "unrealized_net_pnl": round(unreal, 2),
            "equity": round(start + realized + unreal, 2), "open_positions": len(opens), "closed_trades": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0, "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "total_charges": round(sum(p.get("charges", 0.0) for p in closed), 2), "by_mode": by_mode,
            "enabled": bool(self.runtime.get("earnings_enabled")), "last_cycle": self.last_cycle,
        }

    # ---------------------------------------------------------------- RMS gate
    def entry_block(self, cand: es.Candidate, today: date, open_positions: list[dict]) -> Optional[tuple[str, str]]:
        """(code, detail) if the RMS refuses this entry, else None."""
        g = self.runtime.get
        if self.kill_switch():
            return "KILL_SWITCH", "kill switch is engaged"
        limit = float(g("daily_loss_limit"))
        if limit > 0:
            pnl = self.day_pnl(today)
            if pnl <= -limit:
                return "LOSS_CAP", f"earnings book day P&L {pnl:,.0f} reached -{limit:,.0f}"
        streak = int(g("max_consecutive_losses"))
        if streak > 0 and self.consecutive_losses_today(today) >= streak:
            return "LOSS_STREAK_PAUSE", f"{streak} consecutive losses today"
        if len(open_positions) >= int(g("earnings_max_positions")):
            return "MAX_OPEN_POSITIONS", f"{len(open_positions)} open (limit {g('earnings_max_positions')})"
        if any(p["symbol"] == cand.symbol for p in open_positions):
            return "ALREADY_OPEN", f"{cand.symbol} already has an open earnings position"
        if g("earnings_one_per_sector") and cand.sector and any(p.get("sector") == cand.sector for p in open_positions):
            return "SECTOR_CONCENTRATION", f"sector {cand.sector} already has an open position"
        per_day = int(g("max_entries_per_day"))
        if per_day > 0:
            n = sum(1 for p in self.store.positions() if str(p.get("opened_at", ""))[:10] == today.isoformat())
            if n >= per_day:
                return "MAX_ENTRIES_PER_DAY", f"{n} entries today (limit {per_day})"
        notional_cap = float(g("max_open_notional"))
        if notional_cap > 0:
            used = sum(p.get("max_risk", 0.0) for p in open_positions)
            if used + cand.max_risk > notional_cap:
                return "MAX_OPEN_NOTIONAL", f"open risk {used + cand.max_risk:,.0f} would exceed {notional_cap:,.0f}"
        return None

    # ---------------------------------------------------------------- cycle
    async def run_cycle(self, now: Optional[datetime] = None) -> dict:
        """One pass: refresh IV history, mark and exit open positions, then look for entries."""
        async with self._lock:
            now = now or market_hours.now_ist()
            today = now.date()
            result: dict = {"at": now.isoformat(), "status": "ok", "opened": [], "closed": [], "skipped": 0}
            if self.provider is None or not self.provider.has_credentials():
                result["status"] = "no_credentials"
                if any(p["status"] == "OPEN" for p in self.store.positions()):
                    from app.services import notifier  # open positions are unmanaged until someone logs in again
                    notifier.notify("earnings_unmanaged", "Earnings positions are open but no broker session is connected, so they are not being managed. Log in to the dashboard.",
                                    dedupe_key="earnings_unmanaged", min_interval=3600)
            elif not market_hours.is_trading_day(today):
                result["status"] = "not_a_trading_day"
            else:
                try:
                    if market_hours.is_market_open(now) and now.hour * 60 + now.minute >= 9 * 60 + 30:
                        await self._record_iv(today, result)  # not on pre-open data, which carries yesterday's closing vols
                    await self._step_positions(now, result)
                    if self.runtime.get("earnings_enabled") and market_hours.is_market_open(now):
                        await self._scan_and_enter(now, result)
                except Exception as exc:
                    logger.warning("Earnings cycle failed: %s", exc, exc_info=True)
                    result["status"] = "error"
                    result["error"] = str(exc)
            self.last_cycle = result
        # Outside the lock and after the exits: a slow NSE download must delay neither the exits nor a kill-switch
        # square-off (which waits for this lock). Needs no broker session.
        try:
            sync = await self.sync_calendar(today)
            if sync["status"] != "skipped":
                result["calendar_sync"] = sync
        except Exception:
            logger.warning("calendar sync crashed", exc_info=True)
        return result

    async def _record_iv(self, today: date, result: dict) -> None:
        """Once a day, store ATM IV for stocks with earnings coming up, so IV percentile / rank have history."""
        track_until = today + timedelta(days=max(45, int(self.runtime.get("earnings_mode_a_far_days")) + 10))
        seen = set()
        for row in self.store.calendar(today):
            sym = row["symbol"]
            if sym in seen or _d(row["earnings_date"]) > track_until or self.store.has_iv(sym, today):
                continue
            seen.add(sym)
            spot = await self.provider.spot(sym)
            exps = await self.provider.expiries(sym) if spot else []
            exps = [e for e in exps if e >= today]
            if not spot or not exps:
                continue
            oc = await self.provider.chain(sym, exps[0])
            grid = es.strike_grid(oc)
            atm = es.nearest_strike(grid, spot)
            ce, pe = (es.contract(oc, atm, "CE"), es.contract(oc, atm, "PE")) if atm else (None, None)
            ivs = [c["iv"] for c in (ce, pe) if c and c["iv"] > 0]
            if ivs:
                self.store.record_iv(sym, today, sum(ivs) / len(ivs), spot)
                result["iv_recorded"] = result.get("iv_recorded", 0) + 1

    async def _evaluate(self, now: datetime, log: bool = True):
        """Yield (row, mode, outcome) for every calendar row / mode that is due today; outcome is a Candidate or a Skip."""
        today, g, cfg = now.date(), self.runtime.get, self.cfg()
        existing = {(p["symbol"], p["earnings_date"], p["mode"]) for p in self.store.positions()}

        def skip(mode: str, sym: str, code: str, metrics: Optional[dict] = None) -> es.Skip:
            if log:
                self._log("SKIPPED", mode, sym, code, metrics)
            return es.Skip(code, metrics=metrics or {})

        for row in self.store.calendar(today):
            sym, edate = row["symbol"], _d(row["earnings_date"])
            session = es.resolve_session(row["session"], g("earnings_default_session"))
            inst = self.provider.instrument(sym)
            for mode, on in ((es.MODE_A, g("earnings_mode_a_enabled")), (es.MODE_B, g("earnings_mode_b_enabled"))):
                if not on or (sym, row["earnings_date"], mode) in existing:
                    continue
                if session is None:
                    yield row, mode, skip(mode, sym, "SESSION_UNKNOWN", {"earnings_date": row["earnings_date"]})
                    continue
                # cheap window pre-check so chains are only pulled for names that can trade today
                if mode == es.MODE_A and not es.mode_a_in_window(today, edate, cfg["far_days"], cfg["near_days"]):
                    continue
                if mode == es.MODE_B and today != es.mode_b_entry_date(edate, session):
                    continue
                if not inst:
                    yield row, mode, skip(mode, sym, "NOT_IN_FNO_UNIVERSE")
                    continue
                spot = await self.provider.spot(sym)
                expiries = await self.provider.expiries(sym) if spot else []
                if not spot or not expiries:
                    yield row, mode, skip(mode, sym, "NO_MARKET_DATA")
                    continue
                needed = (es.mode_a_exit_date(edate, session, cfg["exit_days_before"]) if mode == es.MODE_A
                          else es.mode_b_exit_date(edate, session))
                exp = es.choose_expiry(expiries, needed, cfg["min_days_to_expiry"])
                oc = await self.provider.chain(sym, exp) if exp else {}
                lots = int(g("earnings_lots"))
                cap = int(g("max_lots_per_trade"))
                if cap > 0:
                    lots = min(lots, cap)
                history = self.store.iv_history(sym, today, int(g("earnings_iv_lookback_days")))
                fn = es.evaluate_mode_a if mode == es.MODE_A else es.evaluate_mode_b
                out = fn(symbol=sym, sector=row["sector"] or (inst.get("sector") or ""), earnings_date=edate, session=session,
                         today=today, spot=spot, expiries=expiries, oc_for=lambda _e, _oc=oc: _oc,
                         lot_size=int(inst["lot_size"]), lots=lots, iv_history=history, cfg=cfg)
                if isinstance(out, es.Skip) and log:
                    self._log("SKIPPED", mode, sym, out.code, {"detail": out.detail, **out.metrics})
                yield row, mode, out

    async def _scan_and_enter(self, now: datetime, result: dict) -> None:
        today = now.date()
        if now.hour * 60 + now.minute < _hhmm_minutes(self.runtime.get("earnings_entry_time")):
            result["entries"] = "before_entry_time"
            return
        async for row, mode, out in self._evaluate(now):
            if isinstance(out, es.Skip):
                result["skipped"] += 1
                continue
            block = self.entry_block(out, today, [p for p in self.store.positions() if p["status"] == "OPEN"])
            if block:
                self._log("SKIPPED", mode, out.symbol, block[0], {"detail": block[1], **out.metrics})
                result["skipped"] += 1
                continue
            result["opened"].append(self._open(out, now)["id"])

    async def preview(self, now: Optional[datetime] = None) -> list[dict]:
        """What the engine would do right now, without opening anything or writing decisions."""
        now = now or market_hours.now_ist()
        if self.provider is None or not self.provider.has_credentials():
            return []
        rows = []
        async for row, mode, out in self._evaluate(now, log=False):
            if isinstance(out, es.Skip):
                rows.append({"symbol": row["symbol"], "mode": mode, "ready": False, "code": out.code, "detail": out.detail, "metrics": out.metrics})
            else:
                block = self.entry_block(out, now.date(), [p for p in self.store.positions() if p["status"] == "OPEN"])
                rows.append({"symbol": out.symbol, "mode": mode, "ready": block is None, "code": block[0] if block else "READY",
                             "detail": block[1] if block else "", "earnings_date": out.earnings_date.isoformat(),
                             "expiry": out.expiry.isoformat(), "exit_date": out.exit_date.isoformat(), "net_unit": out.net_unit,
                             "max_risk": out.max_risk, "lots": out.lots, "legs": [l.as_dict() for l in out.legs], "metrics": out.metrics})
        return rows

    def _open(self, c: es.Candidate, now: datetime) -> dict:
        qty = c.lot_size * c.lots
        legs = [{**l.as_dict(), "current_bid": l.bid, "current_ask": l.ask, "current_ltp": l.entry_price} for l in c.legs]
        shorts = [l for l in c.legs if l.side == "SELL"]
        pos = {
            "id": f"ERN_{c.symbol}_{c.mode[-1]}_{uuid.uuid4().hex[:8]}", "mode": c.mode, "symbol": c.symbol, "sector": c.sector,
            "status": "OPEN", "opened_at": now.isoformat(timespec="seconds"), "earnings_date": c.earnings_date.isoformat(),
            "session": c.session, "expiry": c.expiry.isoformat(), "exit_date": c.exit_date.isoformat(), "lots": c.lots,
            "lot_size": c.lot_size, "qty": qty, "legs": legs, "net_unit": c.net_unit, "max_risk": c.max_risk,
            "premium_paid": round(c.net_unit * qty, 2) if c.mode == es.MODE_A else 0.0,
            "spot_entry": c.spot, "spot_current": c.spot,
            "short_pe": next((l.strike for l in shorts if l.opt == "PE"), None),
            "short_ce": next((l.strike for l in shorts if l.opt == "CE"), None),
            "unrealized_gross": 0.0, "unrealized_net": 0.0, "mfe": 0.0, "mae": 0.0, "iv_entry": c.iv_atm,
            "entry_metrics": c.metrics,
        }
        self._reprice(pos)
        self.store.save_position(pos, entry_evidence=(
            {"reason": "SIGNAL_CONFIRMED", "checks": c.metrics,
             "mode": c.mode, "legs": legs, "lots": c.lots,
             "max_risk": c.max_risk, "opened_at": pos["opened_at"],
             "earnings_date": pos["earnings_date"], "exit_date": pos["exit_date"]},
            {}))
        self._log("ENTERED", c.mode, c.symbol, "SIGNAL_CONFIRMED",
                  {**c.metrics, "lots": c.lots, "qty": qty, "max_risk": c.max_risk, "exit_date": pos["exit_date"]}, pos["id"])
        return pos

    # ---------------------------------------------------------------- valuation / exits
    def _charges(self, pos: dict) -> float:
        total = 0.0
        for lg in pos["legs"]:
            exit_px = lg.get("current_bid") if lg["side"] == "BUY" else lg.get("current_ask")
            exit_px = exit_px or lg.get("current_ltp") or lg["entry_price"]
            buy, sell = (lg["entry_price"], exit_px) if lg["side"] == "BUY" else (exit_px, lg["entry_price"])
            total += calculate_option_trade_charges(buy_price=float(buy), sell_price=float(sell), quantity=pos["qty"], orders_count=2).total_charges
        return round(total, 2)

    def _reprice(self, pos: dict) -> None:
        pos["unrealized_gross"] = es.gross_pnl(pos["legs"], pos["qty"])
        pos["unrealized_net"] = round(pos["unrealized_gross"] - self._charges(pos), 2)
        pos["mfe"] = max(pos.get("mfe", 0.0), pos["unrealized_gross"])
        pos["mae"] = min(pos.get("mae", 0.0), pos["unrealized_gross"])

    async def _step_positions(self, now: datetime, result: dict) -> None:
        today, g = now.date(), self.runtime.get
        cal = {(r["symbol"], r["earnings_date"]): r for r in self.store.calendar()}
        now_min = now.hour * 60 + now.minute
        for pos in [p for p in self.store.positions() if p["status"] == "OPEN"]:
            sym = pos["symbol"]
            row = cal.get((sym, pos["earnings_date"]))
            if row:  # a rescheduled board meeting changes the exit day
                session = es.resolve_session(row["session"], g("earnings_default_session")) or pos["session"]
                edate = _d(row["earnings_date"])
                new_exit = (es.mode_a_exit_date(edate, session, g("earnings_mode_a_exit_days_before")) if pos["mode"] == es.MODE_A
                            else es.mode_b_exit_date(edate, session))
                if new_exit.isoformat() != pos["exit_date"]:
                    self._log("HELD", pos["mode"], sym, "EXIT_DATE_RESCHEDULED", {"old": pos["exit_date"], "new": new_exit.isoformat()}, pos["id"])
                    pos["exit_date"] = new_exit.isoformat()
            spot = await self.provider.spot(sym)
            oc = await self.provider.chain(sym, _d(pos["expiry"]))
            if spot:
                pos["spot_current"] = spot
            if oc:
                for lg in pos["legs"]:
                    c = es.contract(oc, lg["strike"], lg["opt"])
                    if c:
                        lg["current_bid"], lg["current_ask"] = c["bid"], c["ask"]
                        lg["current_ltp"] = c["ltp"] or lg.get("current_ltp")
                self._reprice(pos)
            if self.store.position_status(pos["id"]) != "OPEN":
                continue  # closed (kill switch / manual square-off) while the quotes were being fetched
            have_quote = bool(oc) and bool(spot)
            exit_min = _hhmm_minutes(g("earnings_exit_time") if pos["mode"] == es.MODE_A else g("earnings_mode_b_exit_time"))
            reason = es.exit_reason(
                mode=pos["mode"], today=today, now_minutes=now_min, exit_date=_d(pos["exit_date"]), exit_minutes=exit_min,
                pnl=pos["unrealized_gross"], premium_paid=pos["premium_paid"], max_loss_pct=float(g("earnings_mode_a_max_loss_pct")),
                spot=pos["spot_current"], short_pe=pos["short_pe"], short_ce=pos["short_ce"], expiry=_d(pos["expiry"]),
                min_days_to_expiry=int(g("earnings_min_days_to_expiry")))
            if reason and not have_quote:
                # Never act on a price we could not refresh. A scheduled exit a full day overdue still closes, at the
                # last known prices, so a position cannot be left open indefinitely.
                overdue = reason == "SCHEDULED_EXIT" and today > _d(pos["exit_date"])
                if not overdue:
                    self._log("HELD", pos["mode"], sym, "EXIT_DUE_NO_QUOTE", {"reason": reason}, pos["id"])
                    reason = None
            if reason:
                self._close(pos, now, reason)
                result["closed"].append(pos["id"])
            else:
                self.store.save_position(pos)

    def _close(self, pos: dict, now: datetime, reason: str) -> None:
        self._reprice(pos)
        charges = self._charges(pos)
        pos.update(status="CLOSED", closed_at=now.isoformat(timespec="seconds"), exit_reason=reason, gross_pnl=pos["unrealized_gross"],
                   charges=charges, net_pnl=round(pos["unrealized_gross"] - charges, 2), unrealized_gross=0.0, unrealized_net=0.0)
        self.store.save_position(pos)
        self._log("EXITED", pos["mode"], pos["symbol"], reason,
                  {"gross_pnl": pos["gross_pnl"], "net_pnl": pos["net_pnl"], "charges": charges, "mfe": pos["mfe"], "mae": pos["mae"],
                   "spot_entry": pos["spot_entry"], "spot_exit": pos["spot_current"]}, pos["id"])

    async def square_off_all(self, reason: str = "KILL_SWITCH") -> int:
        """Close every open earnings position at the last known prices (paper)."""
        async with self._lock:  # waits for a running cycle so the two never act on the same position
            now = market_hours.now_ist()
            n = 0
            for pos in [p for p in self.store.positions() if p["status"] == "OPEN"]:
                self._close(pos, now, reason)
                n += 1
            return n
