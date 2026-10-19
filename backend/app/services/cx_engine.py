"""Paper-trading book for MCX commodity and NSE currency options (Setups 17-19). Paper only: it never routes real orders.

Pieces:
* ``CxStore``        positions and run state in the trades database (tables ``cx_positions`` and ``cx_meta``).
* ``DhanCxProvider`` live contracts, 5-minute candles of the underlying future and the option chain from the Dhan client.
* ``CxEngine``       every ``cx_poll_seconds``: manage open positions, then look for entries on the last completed bar.

Each commodity / currency underlying is a futures contract; the book buys the at-the-money call or put (the option on that
future) when a setup fires, marks it on the chain's bid, and exits on a premium stop, a premium target, a time stop, the
underlying trading back through the setup's invalidation level, the exchange square-off time, or the kill switch.

Two pools (``commodity`` for MCX, ``currency`` for NSE currency) each have their own daily loss cap and their own session
hours (``exchange_sessions``), so a bad MCX evening cannot stop the currency pool or any NSE book.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import pandas as pd

from app.services import cx_instruments as ci
from app.services import cx_signals as sg
from app.services import db, market_hours
from app.services import exchange_sessions as xs
from app.services.charges_calculator import calculate_currency_option_charges, calculate_mcx_option_charges
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry

logger = logging.getLogger(__name__)
BOOK = "cx"
CANDLE_MINUTES = 5
HISTORY_DAYS = 5
MAX_BAR_AGE_MINUTES = 20  # the last completed bar must be this recent while the session is open
LEG_KEY = {"CE": "ce", "PE": "pe"}


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ============================================================================================ store
class CxStore:
    def __init__(self, db_path: Optional[str]):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._mem_pos: dict[str, dict] = {}
        self._mem_meta: dict[str, str] = {}
        if db_path:
            with self._conn() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS cx_positions (
                    id TEXT PRIMARY KEY, symbol TEXT, pool TEXT, setup TEXT, status TEXT, opened_at TEXT, body TEXT)""")
                c.execute("CREATE TABLE IF NOT EXISTS cx_meta (key TEXT PRIMARY KEY, value TEXT)")

    def _conn(self) -> sqlite3.Connection:
        c = db.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def save_position(self, pos: dict) -> None:
        with self._lock:
            if not self.db_path:
                self._mem_pos[pos["id"]] = json.loads(json.dumps(pos))
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO cx_positions (id, symbol, pool, setup, status, opened_at, body) VALUES (?,?,?,?,?,?,?)",
                          (pos["id"], pos["symbol"], pos["pool"], pos.get("setup", ""), pos["status"], pos.get("opened_at", ""), json.dumps(pos)))

    def positions(self) -> list[dict]:
        with self._lock:
            if not self.db_path:
                rows = [json.loads(json.dumps(p)) for p in self._mem_pos.values()]
            else:
                with self._conn() as c:
                    rows = [json.loads(r["body"]) for r in c.execute("SELECT body FROM cx_positions")]
        return sorted(rows, key=lambda p: (p.get("opened_at", ""), p["id"]))

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            if not self.db_path:
                return self._mem_meta.get(key)
            with self._conn() as c:
                r = c.execute("SELECT value FROM cx_meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            if not self.db_path:
                self._mem_meta[key] = value
                return
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO cx_meta (key, value) VALUES (?,?)", (key, value))


# ============================================================================================ data
class DhanCxProvider:
    """Contracts, candles and option chains for the commodity / currency underlyings via the shared Dhan client."""

    def __init__(self, dhan_client: Any, get_credentials: Callable[[], Optional[tuple[str, str]]], resolver: ci.ContractResolver):
        self.dhan = dhan_client
        self.get_credentials = get_credentials
        self.resolver = resolver

    def has_credentials(self) -> bool:
        return bool(self.get_credentials())

    async def contracts(self, symbols: list[str], today: date) -> dict[str, list[dict]]:
        return await self.resolver.resolve(symbols, today)

    async def candles(self, symbol: str, contract: dict, now: datetime) -> pd.DataFrame:
        creds = self.get_credentials()
        if not creds:
            return pd.DataFrame()
        u = ci.UNDERLYINGS[symbol]
        naive = now.replace(tzinfo=None)
        df = await self.dhan.fetch_intraday_candles(
            creds[0], creds[1], contract["security_id"], u.segment, u.fut_type, CANDLE_MINUTES,
            (naive - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d 09:00:00"), naive.strftime("%Y-%m-%d %H:%M:%S"))
        return df if df is not None else pd.DataFrame()

    async def chain(self, symbol: str, contract: dict, now: datetime) -> tuple[Optional[str], dict]:
        """(expiry, option chain) for the first option expiry after today; (None, {}) when unavailable."""
        creds = self.get_credentials()
        if not creds:
            return None, {}
        u = ci.UNDERLYINGS[symbol]
        expiries = await self.dhan.fetch_expiry_list(creds[0], creds[1], int(contract["security_id"]), u.segment)
        today = now.date().isoformat()
        future = sorted(str(e)[:10] for e in expiries if str(e)[:10] > today)
        if not future:
            return None, {}
        oc = await self.dhan.fetch_option_chain(creds[0], creds[1], int(contract["security_id"]), u.segment, future[0])
        return future[0], oc or {}


def completed_bars(df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Drop the bar that is still forming (its 5 minutes are not over yet)."""
    if df is None or df.empty:
        return pd.DataFrame()
    ts = pd.to_datetime(df["timestamp"])
    cut = pd.Timestamp(now.replace(tzinfo=None)) - pd.Timedelta(minutes=CANDLE_MINUTES)
    return df[ts <= cut].reset_index(drop=True)


def _two_sided(leg: dict) -> bool:
    return _f(leg.get("top_bid_price")) > 0 and _f(leg.get("top_ask_price")) > 0


def atm_strike(oc: dict, fallback_price: float) -> Optional[float]:
    """The at-the-money strike. Put-call parity first (the strike where call and put last prices are closest, which is the
    chain's own forward and does not depend on which futures month the candles came from); the candle price otherwise."""
    best, best_gap = None, None
    strikes = []
    for k, row in oc.items():
        strike = _f(k, float("nan"))
        if strike != strike or not isinstance(row, dict):
            continue
        strikes.append(strike)
        ce, pe = row.get("ce"), row.get("pe")
        if isinstance(ce, dict) and isinstance(pe, dict) and _f(ce.get("last_price")) > 0 and _f(pe.get("last_price")) > 0:
            gap = abs(_f(ce.get("last_price")) - _f(pe.get("last_price")))
            if best is None or gap < best_gap:
                best, best_gap = strike, gap
    if best is not None:
        return best
    return min(strikes, key=lambda x: abs(x - fallback_price)) if strikes else None


def pick_leg(oc: dict, side: str, price: float) -> Optional[dict]:
    """The ``side`` leg to buy: the ATM strike, or the nearest of the next two strikes either side that has a two-sided
    quote (a third of chain legs have no bid or ask). When none of them is quoted the ATM leg is returned so the caller
    can log why it skipped. The leg carries its ``strike``."""
    center = atm_strike(oc, price)
    if center is None:
        return None
    legs = []
    for k, row in oc.items():
        leg = row.get(LEG_KEY[side]) if isinstance(row, dict) else None
        strike = _f(k, float("nan"))
        if isinstance(leg, dict) and strike == strike:
            legs.append({**leg, "strike": strike})
    legs.sort(key=lambda l: abs(l["strike"] - center))
    near = legs[:5]
    if not near:
        return None
    for leg in near:
        if _two_sided(leg):
            return leg
    return near[0]


def leg_for(oc: dict, strike: float, side: str) -> Optional[dict]:
    for k, row in oc.items():
        if isinstance(row, dict) and abs(_f(k, -1.0) - strike) < 1e-6:
            leg = row.get(LEG_KEY[side])
            return leg if isinstance(leg, dict) else None
    return None


# ============================================================================================ engine
class CxEngine:
    def __init__(self, db_path: Optional[str], runtime: RuntimeSettings, telemetry: Telemetry,
                 provider: Optional[DhanCxProvider] = None, kill_switch: Optional[Callable[[], bool]] = None,
                 notify: Optional[Callable[..., Any]] = None):
        self.store = CxStore(db_path)
        self.runtime = runtime
        self.telemetry = telemetry
        self.provider = provider
        self.kill_switch = kill_switch or (lambda: False)
        self.notify = notify
        self._lock = asyncio.Lock()
        self.last_cycle: dict = {"status": "never_run"}
        self.symbol_status: dict[str, dict] = {}
        self._loss_cap_notified: dict[str, str] = {}

    # ---------------------------------------------------------------- config
    def session_cfg(self) -> xs.SessionConfig:
        return xs.config_from(self.runtime)

    def signal_cfg(self) -> sg.CxSignalConfig:
        g = self.runtime.get
        return sg.CxSignalConfig(
            donchian_len=int(g("cx_donchian_len")), adx_min=float(g("cx_adx_min")), orb_minutes=int(g("cx_orb_minutes")),
            adx_max_fade=float(g("cx_adx_max_fade")), rsi_low=float(g("cx_rsi_low")), rsi_high=float(g("cx_rsi_high")),
            s17=bool(g("cx_setup17_enabled")), s18=bool(g("cx_setup18_enabled")), s19=bool(g("cx_setup19_enabled")))

    def symbols(self) -> list[str]:
        raw = str(self.runtime.get("cx_symbols") or "")
        return [s for s in (x.strip().upper() for x in raw.split(",")) if s in ci.UNDERLYINGS and s not in ci.PARKED]

    def pool_enabled(self, pool: str) -> bool:
        if pool in ci.PARKED_POOLS:
            return False
        return bool(self.runtime.get("cx_commodity_enabled" if pool == "commodity" else "cx_currency_enabled"))

    def loss_cap(self, pool: str) -> float:
        return float(self.runtime.get("cx_loss_cap_commodity" if pool == "commodity" else "cx_loss_cap_currency"))

    def _slip(self) -> float:
        return float(self.runtime.get("cx_slippage_pct")) / 100.0

    def _log(self, decision: str, symbol: str, reason: str, metrics: Optional[dict] = None, pos_id: Optional[str] = None,
             strategy: str = "", side: str = "") -> None:
        self.telemetry.decision(book=BOOK, strategy=strategy or "CX", symbol=symbol, decision=decision, reason=reason,
                                side=side, metrics=metrics or {}, position_id=pos_id)

    def _charges(self, u: ci.CxUnderlying, entry: float, exit_px: float, units: float) -> float:
        fn = calculate_mcx_option_charges if u.pool == "commodity" else calculate_currency_option_charges
        return fn(entry, exit_px, units, brokerage_per_order=float(self.runtime.get("cx_brokerage_per_order"))).total_charges

    # ---------------------------------------------------------------- P&L and risk
    def _open(self) -> list[dict]:
        return [p for p in self.store.positions() if p["status"] == "OPEN"]

    def pool_day_pnl(self, pool: str, day: Optional[str] = None) -> float:
        """Net P&L of the pool today: closed trades plus open positions marked on the bid, net of estimated exit charges."""
        day = day or market_hours.now_ist().date().isoformat()
        total = 0.0
        for p in self.store.positions():
            if p["pool"] != pool:
                continue
            if p["status"] == "CLOSED" and str(p.get("closed_at", ""))[:10] == day:
                total += p.get("net_pnl", 0.0)
            elif p["status"] == "OPEN" and str(p.get("opened_at", ""))[:10] == day:
                total += p.get("unrealized_net", 0.0)
        return round(total, 2)

    def loss_cap_tripped(self, pool: str) -> bool:
        cap = self.loss_cap(pool)
        if cap <= 0:
            return False
        pnl = self.pool_day_pnl(pool)
        if pnl > -cap:
            return False
        day = market_hours.now_ist().date().isoformat()
        if self._loss_cap_notified.get(pool) != day:
            self._loss_cap_notified[pool] = day
            if self.notify:
                try:
                    self.notify("cx_loss_cap", f"Commodities & Currency {pool} pool reached its daily loss cap ({pnl:,.0f} of -{cap:,.0f}). New entries stopped for today.",
                                dedupe_key=f"cx_loss_cap_{pool}_{day}", min_interval=3600)
                except Exception:
                    logger.warning("cx loss cap notification failed", exc_info=True)
        return True

    def summary(self) -> dict:
        allp = self.store.positions()
        closed = [p for p in allp if p["status"] == "CLOSED"]
        opens = [p for p in allp if p["status"] == "OPEN"]
        start = float(self.runtime.get("cx_starting_capital"))

        def block(ps_closed: list[dict], ps_open: list[dict]) -> dict:
            pnls = [p.get("net_pnl", 0.0) for p in ps_closed]
            wins, losses = [x for x in pnls if x > 0], [x for x in pnls if x < 0]
            return {"realized_net_pnl": round(sum(pnls), 2), "unrealized_net_pnl": round(sum(p.get("unrealized_net", 0.0) for p in ps_open), 2),
                    "open_positions": len(ps_open), "closed_trades": len(ps_closed),
                    "win_rate": round(len(wins) / len(ps_closed) * 100, 1) if ps_closed else 0.0,
                    "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
                    "total_charges": round(sum(p.get("charges", 0.0) for p in ps_closed), 2)}

        total = block(closed, opens)
        pools = {}
        for pool in ci.POOLS:
            pools[pool] = {**block([p for p in closed if p["pool"] == pool], [p for p in opens if p["pool"] == pool]),
                           "enabled": self.pool_enabled(pool), "parked": pool in ci.PARKED_POOLS, "day_pnl": self.pool_day_pnl(pool), "loss_cap": self.loss_cap(pool),
                           "loss_cap_tripped": self.loss_cap_tripped(pool)}
        cfg = self.session_cfg()
        now = market_hours.now_ist()
        return {"starting_capital": start, "equity": round(start + total["realized_net_pnl"] + total["unrealized_net_pnl"], 2),
                **total, "pools": pools, "enabled": bool(self.runtime.get("cx_enabled")),
                "sessions": {x: {"open": xs.is_session_open(x, now, cfg), "entry_allowed": xs.is_entry_allowed(x, now, cfg),
                                 "square_off_due": xs.is_square_off_due(x, now, cfg)} for x in xs.EXCHANGES},
                "last_cycle": self.last_cycle, "symbols": self.symbol_status}

    def positions(self, status: Optional[str] = None) -> list[dict]:
        return [p for p in self.store.positions() if status is None or p["status"] == status]

    def overview(self) -> dict:
        """Everything the Commodities & Currency tab shows, in one call (no broker traffic)."""
        today = market_hours.now_ist().date().isoformat()
        allp = self.store.positions()
        closed = [p for p in allp if p["status"] == "CLOSED"]
        done_today = [p for p in closed if str(p.get("closed_at", ""))[:10] == today]
        return {"summary": self.summary(), "open_positions": [p for p in allp if p["status"] == "OPEN"],
                "closed_today": done_today, "recent_closed": sorted(closed, key=lambda p: p.get("closed_at", ""), reverse=True)[:30],
                "decisions": self.telemetry.decisions(hours=24, book=BOOK, limit=100),
                "settings": {"lots": int(self.runtime.get("cx_lots")), "sl_pct": float(self.runtime.get("cx_sl_pct")),
                             "target_pct": float(self.runtime.get("cx_target_pct")), "symbols": self.symbols()},
                "as_of": market_hours.now_ist().strftime("%H:%M:%S")}

    # ---------------------------------------------------------------- entry gate
    def entry_block(self, u: ci.CxUnderlying, now: datetime, side_open: list[dict]) -> Optional[tuple[str, str]]:
        g = self.runtime.get
        if not g("cx_enabled"):
            return "CX_DISABLED", "Commodities & Currency book is switched off"
        if u.symbol in ci.PARKED or u.pool in ci.PARKED_POOLS:
            return "PARKED", f"{u.symbol} is parked until its Dhan data check passes"
        if not self.pool_enabled(u.pool):
            return "POOL_OFF", f"{u.pool} pool is switched off"
        if self.kill_switch():
            return "KILL_SWITCH", "kill switch is engaged"
        if not xs.is_entry_allowed(u.exchange, now, self.session_cfg()):
            return "OUTSIDE_ENTRY_WINDOW", f"{u.exchange} is closed or past its last-entry time"
        if self.loss_cap_tripped(u.pool):
            return "LOSS_CAP", f"{u.pool} pool daily loss cap reached"
        if any(p["symbol"] == u.symbol for p in side_open):
            return "ALREADY_HELD", f"{u.symbol} already has an open position"
        if len(side_open) >= int(g("cx_max_open_positions")):
            return "MAX_OPEN_POSITIONS", f"{len(side_open)} open (limit {g('cx_max_open_positions')})"
        day = now.date().isoformat()
        todays = [p for p in self.store.positions() if p["symbol"] == u.symbol and str(p.get("opened_at", ""))[:10] == day]
        cap = int(g("cx_max_entries_per_symbol"))
        if cap > 0 and len(todays) >= cap:
            return "MAX_ENTRIES_PER_SYMBOL", f"{len(todays)} entries today (limit {cap})"
        cooldown = int(g("cx_cooldown_minutes"))
        if cooldown > 0:
            for p in todays:
                if p["status"] == "CLOSED" and p.get("closed_at"):
                    if now - datetime.fromisoformat(p["closed_at"]) < timedelta(minutes=cooldown):
                        return "COOLDOWN", f"last {u.symbol} trade closed less than {cooldown} min ago"
        return None

    # ---------------------------------------------------------------- positions
    def _close(self, pos: dict, now: datetime, bid: float, reason: str) -> None:
        u = ci.UNDERLYINGS[pos["symbol"]]
        exit_px = round(max(0.0, bid * (1 - self._slip())), 4)
        gross = round((exit_px - pos["entry_price"]) * pos["units"], 2)
        charges = self._charges(u, pos["entry_price"], exit_px, pos["units"])
        pos.update(status="CLOSED", closed_at=now.isoformat(), exit_price=exit_px, exit_reason=reason, gross_pnl=gross,
                   charges=charges, net_pnl=round(gross - charges, 2), unrealized_net=0.0,
                   return_pct=round((exit_px / pos["entry_price"] - 1) * 100, 2))
        self.store.save_position(pos)
        self._log("EXITED", pos["symbol"], reason, {"gross_pnl": gross, "net_pnl": pos["net_pnl"], "charges": charges,
                                                     "entry": pos["entry_price"], "exit": exit_px}, pos["id"], pos["setup"], pos["side"])

    def _mark(self, pos: dict, bid: float) -> None:
        u = ci.UNDERLYINGS[pos["symbol"]]
        px = bid * (1 - self._slip())
        pos["last_bid"] = bid
        pos["max_bid"] = max(pos.get("max_bid", 0.0), bid)
        pos["unrealized_net"] = round((px - pos["entry_price"]) * pos["units"] - self._charges(u, pos["entry_price"], px, pos["units"]), 2)

    async def _manage(self, pos: dict, now: datetime, bars: pd.DataFrame, oc: dict) -> bool:
        """Mark and possibly exit one open position. Returns True when it was closed."""
        u = ci.UNDERLYINGS[pos["symbol"]]
        cfg = self.session_cfg()
        leg = leg_for(oc, pos["strike"], pos["side"]) if oc else None
        bid = _f(leg.get("top_bid_price")) if leg else 0.0
        if bid > 0:
            self._mark(pos, bid)
        use = bid if bid > 0 else pos.get("last_bid", 0.0)
        if self.kill_switch():
            self._close(pos, now, use, "KILL_SWITCH")
            return True
        if xs.is_square_off_due(u.exchange, now, cfg):
            self._close(pos, now, use, "SQUARE_OFF" if bid > 0 else "SQUARE_OFF_NO_QUOTE")
            return True
        if bid <= 0:
            self._log("HELD", pos["symbol"], "NO_OPTION_QUOTE", {"strike": pos["strike"]}, pos["id"], pos["setup"], pos["side"])
            self.store.save_position(pos)
            return False
        entry = pos["entry_price"]
        reason = None
        if bid <= entry * (1 - float(self.runtime.get("cx_sl_pct")) / 100.0):
            reason = "STOP_LOSS"
        elif bid >= entry * (1 + float(self.runtime.get("cx_target_pct")) / 100.0):
            reason = "TARGET"
        hold = int(self.runtime.get("cx_max_hold_minutes"))
        if reason is None and hold > 0 and now - datetime.fromisoformat(pos["opened_at"]) >= timedelta(minutes=hold):
            reason = "TIME_STOP"
        if reason is None and bars is not None and len(bars):
            last_close = _f(bars["close"].iloc[-1])
            lvl = pos["invalidate_level"]
            if (pos["side"] == "CE" and last_close <= lvl) or (pos["side"] == "PE" and last_close >= lvl):
                reason = "INVALIDATED"
        if reason:
            self._close(pos, now, bid, reason)
            return True
        self.store.save_position(pos)
        return False

    def _enter(self, u: ci.CxUnderlying, contract: dict, expiry: str, sig: sg.CxSignal, leg: dict, now: datetime,
               bars: Optional[pd.DataFrame] = None) -> Optional[dict]:
        g = self.runtime.get
        bid, ask = _f(leg.get("top_bid_price")), _f(leg.get("top_ask_price"))
        metrics = {**sig.as_dict(), "strike": leg["strike"], "bid": bid, "ask": ask, "expiry": expiry, "oi": leg.get("oi")}
        if bid <= 0 or ask <= 0 or ask < bid:
            self._log("SKIPPED", u.symbol, "NO_TWO_SIDED_QUOTE", metrics, strategy=sig.setup, side=sig.side)
            return None
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid * 100
        if spread > float(g("cx_max_spread_pct")):
            self._log("SKIPPED", u.symbol, "SPREAD_TOO_WIDE", {**metrics, "spread_pct": round(spread, 1)}, strategy=sig.setup, side=sig.side)
            return None
        min_prem = float(g("cx_min_premium_commodity" if u.pool == "commodity" else "cx_min_premium_currency"))
        if ask < min_prem:
            self._log("SKIPPED", u.symbol, "PREMIUM_TOO_LOW", metrics, strategy=sig.setup, side=sig.side)
            return None
        if not contract.get("lot_size_known"):
            self._log("SKIPPED", u.symbol, "LOT_SIZE_UNKNOWN", metrics, strategy=sig.setup, side=sig.side)
            return None
        oi = _f(leg.get("oi"), -1.0) if leg.get("oi") is not None else -1.0
        min_oi = float(g("cx_min_oi"))
        if min_oi > 0 and 0 <= oi < min_oi:  # an option with no OI reported is unknown, not illiquid: only a known low OI blocks
            self._log("SKIPPED", u.symbol, "OPEN_INTEREST_TOO_LOW", {**metrics, "oi": oi}, strategy=sig.setup, side=sig.side)
            return None
        lots = int(g("cx_lots"))
        lot_size = int(contract["lot_size"])
        entry = round(ask * (1 + self._slip()), 4)
        pos = {"id": f"CX_{u.symbol}_{uuid.uuid4().hex[:8]}", "symbol": u.symbol, "pool": u.pool, "setup": sig.setup, "side": sig.side,
               "status": "OPEN", "opened_at": now.isoformat(), "strike": leg["strike"], "expiry": expiry,
               "option_security_id": str(leg.get("security_id", "")), "future_security_id": contract["security_id"],
               "lots": lots, "lot_size": lot_size, "units": u.pnl_multiplier() * lots, "entry_price": entry,
               "entry_bid": bid, "entry_ask": ask, "underlying_entry": sig.price, "invalidate_level": sig.invalidate_level,
               "last_bid": bid, "max_bid": bid, "unrealized_net": 0.0, "signal": sig.as_dict()}
        self.store.save_position(pos)
        try:
            from app.services.dashboard_evidence import save_trade_evidence
            actual_bars = bars[["timestamp", "open", "high", "low", "close"]].to_dict("records") if bars is not None and len(bars) else []
            save_trade_evidence("cx", pos["id"],
                                {"reason": "SIGNAL", "rationale": sig.as_dict(), "checks": sig.metrics,
                                 "entry": entry, "invalidate_level": sig.invalidate_level,
                                 "lots": lots, "opened_at": pos["opened_at"]},
                                {"underlying": actual_bars}, db_path=self.store.db_path)
        except Exception:
            logger.warning("Could not save dashboard evidence for %s", pos["id"], exc_info=True)
        self._log("ENTERED", u.symbol, "SIGNAL", {**metrics, "entry": entry, "lots": lots}, pos["id"], sig.setup, sig.side)
        return pos

    # ---------------------------------------------------------------- live cycle
    async def run_cycle(self, now: Optional[datetime] = None) -> dict:
        async with self._lock:
            now = now or market_hours.now_ist()
            result: dict = {"at": now.isoformat(), "status": "ok", "entered": [], "closed": []}
            try:
                if self.provider is None or not self.provider.has_credentials():
                    result["status"] = "no_credentials"
                    if self._open():
                        from app.services import notifier
                        notifier.notify("cx_unmanaged", "Commodities & Currency positions are open but no broker session is connected, so they are not being managed. Log in to the dashboard.",
                                        dedupe_key="cx_unmanaged", min_interval=3600)
                else:
                    await self._cycle(now, result)
            except Exception as exc:
                logger.warning("Commodities & Currency cycle failed: %s", exc, exc_info=True)
                result["status"] = "error"
                result["error"] = str(exc)
            self.last_cycle = result
            return result

    async def _cycle(self, now: datetime, result: dict) -> None:
        cfg = self.session_cfg()
        enabled = bool(self.runtime.get("cx_enabled"))
        open_by_symbol: dict[str, list[dict]] = {}
        for p in self._open():
            open_by_symbol.setdefault(p["symbol"], []).append(p)
        symbols = sorted(set(self.symbols() if enabled else []) | set(open_by_symbol))
        if not symbols:
            result["status"] = "nothing_to_do"
            return
        contracts = await self.provider.contracts(symbols, now.date())
        sig_cfg = self.signal_cfg()
        for sym in symbols:
            u = ci.UNDERLYINGS.get(sym)
            cs = contracts.get(sym) or []
            st = self.symbol_status.setdefault(sym, {})
            st.update(pool=u.pool if u else "", session_open=bool(u and xs.is_session_open(u.exchange, now, cfg)), checked_at=now.isoformat())
            if u is None or not cs:
                st["state"] = "NO_CONTRACT"
                continue
            mine = open_by_symbol.get(sym, [])
            session_open = st["session_open"]
            if not session_open and not mine:
                st["state"] = "SESSION_CLOSED"
                continue
            # choose the future an open position belongs to, else the nearest one with an option chain
            expiry, oc, contract = None, {}, cs[0]
            if mine:
                contract = next((c for c in cs if c["security_id"] == mine[0]["future_security_id"]), cs[0])
            bars_df = await self.provider.candles(sym, contract, now)
            bars = completed_bars(bars_df, now)
            if mine or enabled:
                expiry, oc = await self.provider.chain(sym, contract, now)
                if expiry and not mine:
                    # the chain is written on the first future expiring on/after the option expiry, which is not always the nearest one
                    under = ci.underlying_for_option_expiry(cs, expiry)
                    if under is not None and under["security_id"] != contract["security_id"]:
                        contract = under
                        bars = completed_bars(await self.provider.candles(sym, contract, now), now)
            for pos in mine:
                if await self._manage(pos, now, bars, oc):
                    result["closed"].append(pos["id"])
            st["bars"] = len(bars)
            st["last_bar"] = str(bars["timestamp"].iloc[-1]) if len(bars) else None
            st["contract"] = contract.get("display") or contract["security_id"]
            st["expiry"] = expiry
            if not enabled:
                st["state"] = "BOOK_OFF"
                continue
            if not len(bars):
                st["state"] = "NO_CANDLES"
                continue
            age = now.replace(tzinfo=None) - pd.Timestamp(bars["timestamp"].iloc[-1]).to_pydatetime()
            if session_open and age > timedelta(minutes=MAX_BAR_AGE_MINUTES):
                st["state"] = "STALE_DATA"
                self._log("SKIPPED", sym, "STALE_DATA", {"last_bar": st["last_bar"], "age_min": round(age.total_seconds() / 60, 1)})
                continue
            if not oc:
                st["state"] = "NO_OPTION_CHAIN"
                continue
            st["state"] = "WATCHING"
            windows = xs.trading_windows(u.exchange, now.date(), cfg)
            win_start = windows[0][0] if windows else None
            for sig in sg.evaluate(sym, bars, sig_cfg, win_start):
                key = f"last_bar:{sym}:{sig.setup}"
                if self.store.get_meta(key) == sig.bar_time:
                    continue
                self.store.set_meta(key, sig.bar_time)
                st["last_signal"] = sig.as_dict()
                live = self._open()
                block = self.entry_block(u, now, live)
                if block:
                    self._log("SKIPPED", sym, block[0], {**sig.as_dict(), "detail": block[1]}, strategy=sig.setup, side=sig.side)
                    continue
                leg = pick_leg(oc, sig.side, sig.price)
                if leg is None:
                    self._log("SKIPPED", sym, "NO_STRIKE", sig.as_dict(), strategy=sig.setup, side=sig.side)
                    continue
                pos = self._enter(u, contract, expiry, sig, leg, now, bars)
                if pos:
                    result["entered"].append(pos["id"])

    async def candidates(self) -> list[dict]:
        """Signals on the last completed bar of each underlying, whether or not the book would take them. Nothing is opened."""
        if self.provider is None or not self.provider.has_credentials():
            return []
        now = market_hours.now_ist()
        cfg, sig_cfg = self.session_cfg(), self.signal_cfg()
        rows = []
        contracts = await self.provider.contracts(self.symbols(), now.date())
        for sym in self.symbols():
            u, cs = ci.UNDERLYINGS[sym], contracts.get(sym) or []
            if not cs:
                continue
            bars = completed_bars(await self.provider.candles(sym, cs[0], now), now)
            windows = xs.trading_windows(u.exchange, now.date(), cfg)
            for sig in sg.evaluate(sym, bars, sig_cfg, windows[0][0] if windows else None) if len(bars) else []:
                block = self.entry_block(u, now, self._open())
                rows.append({**sig.as_dict(), "ready": block is None, "code": block[0] if block else "READY", "detail": block[1] if block else ""})
        return rows

    async def square_off_all(self, reason: str = "KILL_SWITCH") -> int:
        """Close every open position on its last known bid (paper)."""
        async with self._lock:
            now = market_hours.now_ist()
            n = 0
            for pos in self._open():
                self._close(pos, now, pos.get("last_bid", pos["entry_price"]), reason)
                n += 1
            return n
