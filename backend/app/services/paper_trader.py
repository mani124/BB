import asyncio
import json
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal, is_setup5, is_setup11
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.core.config import settings
from app.services.paper_models import *  # noqa: F401,F403
from app.services.paper_models import _now_stamp, _parse_iso, _signed_slip, _view_mode  # noqa: F401
from app.services.paper_persistence import PaperPersistenceMixin
from app.services.paper_guards import PaperGuardsMixin
from app.services import liquidity_filter
from app.services.paper_exits import PaperExitsMixin
from app.services.paper_risk import PaperRiskMixin
from app.services import setup_switches
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry
logger = logging.getLogger(__name__)


def _outcome_pnl(p) -> float:
    """Win/loss basis: net of charges when the trade carries them (matches the dashboard rows), else gross."""
    if getattr(p, "net_pnl", 0.0) or getattr(p, "total_charges", 0.0):
        return p.net_pnl
    return p.pnl_rupees


class PaperTradingEngine(PaperPersistenceMixin, PaperGuardsMixin, PaperExitsMixin, PaperRiskMixin):
    """Manages paper trading execution, position monitoring, and analytics."""

    def __init__(self, db_path: Optional[str] = None):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids: set[str] = set()
        self.storage = None
        self.on_position_opened: Optional[Callable[[PaperPosition], Any]] = None
        # Live order routing (order_router.py). Both stay None, and cost nothing, unless the router is wired in.
        self.on_live_entry: Optional[Callable[[PaperPosition, Any], Any]] = None
        self.on_position_update: Optional[Callable[[PaperPosition], Any]] = None
        self._write_queue: Optional[asyncio.Queue] = None
        self._writer_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._portfolio_generation: int = 0
        self._pending_errors: list[Exception] = []
        # Every limit and threshold is a runtime setting (see runtime_settings.py): editable from the dashboard,
        # persisted in the database, falling back to the environment defaults.
        self.runtime = RuntimeSettings(db_path)
        self.telemetry = Telemetry(
            db_path, self.runtime,
            log_dir=os.path.join(os.path.dirname(os.path.abspath(db_path)), "logs") if db_path else None)
        self.runtime.on_change("default_lots", self._apply_default_lots)
        self.runtime.on_change("max_risk_per_trade", self._apply_max_risk)
        self._init_risk()
        if db_path is not None:
            from app.services.paper_storage import PaperStorage
            self.storage = PaperStorage(db_path)
            try:
                self.storage.prune_trade_candles()
            except Exception:
                pass
            self._load_from_storage()

    def get_portfolio(self, mode: Optional[str] = None) -> PaperPortfolio:
        self._recalculate_metrics()
        mode = _view_mode(mode)
        if not mode:
            self._portfolio.risk = self.risk_status(None).model_dump()
            return self._portfolio

        active = [p for p in self._portfolio.active_positions if getattr(p, "feed_mode", "demo") == mode]
        all_closed = [p for p in self._portfolio.closed_trades if getattr(p, "feed_mode", "demo") == mode]
        closed = [p for p in all_closed if not p.quarantine_reason]
        closed_pnl = sum(p.pnl_rupees for p in closed)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in active)
        realized = round(closed_pnl + active_booked_pnl, 2)
        unrealized = round(sum(round(p.pnl_points * p.quantity, 2) for p in active), 2)
        total = round(realized + unrealized, 2)
        unrealized_charges = round(sum(p.est_exit_charges for p in active), 2)
        total_trades = len(closed)
        winning = sum(1 for p in closed if _outcome_pnl(p) > 0)
        losing = sum(1 for p in closed if _outcome_pnl(p) < 0)
        win_rate = round((winning / total_trades) * 100, 1) if total_trades > 0 else 0.0

        total_gross = sum(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees for p in closed)
        total_charges = sum(getattr(p, "total_charges", 0.0) for p in closed)
        total_net = sum(getattr(p, "net_pnl", 0.0) for p in closed)
        total_slip_cost = sum(getattr(p, "total_slippage_cost", 0.0) for p in closed)
        avg_slip_pts = (
            sum((getattr(p, "entry_slippage", 0.0) + getattr(p, "exit_slippage", 0.0)) for p in closed) / total_trades
            if total_trades > 0 else 0.0
        )

        return PaperPortfolio(
            active_positions=active,
            closed_trades=all_closed,
            auto_trade_enabled=self._portfolio.auto_trade_enabled,
            setup_modes=setup_switches.normalize_modes(self._portfolio.setup_modes),
            default_lots=self._portfolio.default_lots,
            max_risk_per_trade=self._portfolio.max_risk_per_trade,
            total_realized_pnl=realized,
            total_unrealized_pnl=unrealized,
            total_unrealized_charges=unrealized_charges,
            total_unrealized_net=round(unrealized - unrealized_charges, 2),
            total_pnl=total,
            win_rate_pct=win_rate,
            total_trades_count=total_trades,
            winning_trades_count=winning,
            losing_trades_count=losing,
            total_gross_pnl=round(total_gross, 2),
            total_slippage_cost=round(total_slip_cost, 2),
            avg_slippage_points=round(avg_slip_pts, 2),
            total_charges=round(total_charges, 2),
            total_net_pnl=round(total_net, 2),
            closed_trades_count=len(all_closed),
            risk=self.risk_status(mode).model_dump(),
        )

    def get_portfolio_summary(self, mode: Optional[str] = None) -> PaperPortfolio:
        """Totals and open positions without the closed-trade list. Used for the state that is
        broadcast every scan, whose size must not grow with the journal."""
        full = self.get_portfolio(mode)
        return full.model_copy(update={"closed_trades": [], "closed_trades_count": len(full.closed_trades)})

    def get_daily_pnl(self, mode: Optional[str] = None) -> list[DailyPnl]:
        """P1-7: realized P&L per IST exit date (newest first). Quarantined rows are
        excluded from the figures and only counted in ``quarantined_excluded``."""
        mode = _view_mode(mode)
        days: dict[str, DailyPnl] = {}
        for p in self._portfolio.closed_trades:
            if mode is not None and getattr(p, "feed_mode", "demo") != mode:
                continue
            stamp = _parse_iso(p.exit_datetime) or _parse_iso(p.entry_datetime)
            key = stamp.date().isoformat() if stamp else "unknown"
            day = days.setdefault(key, DailyPnl(date=key))
            if p.quarantine_reason:
                day.quarantined_excluded += 1
                continue
            day.trades += 1
            if _outcome_pnl(p) > 0:
                day.wins += 1
            elif _outcome_pnl(p) < 0:
                day.losses += 1
            day.gross_pnl = round(day.gross_pnl + (p.gross_pnl or p.pnl_rupees), 2)
            day.total_charges = round(day.total_charges + p.total_charges, 2)
            day.net_pnl = round(day.net_pnl + p.net_pnl, 2)
        # Profit already booked at Target 1 on still-open runners is realized today.
        today = market_hours.now_ist().date().isoformat()
        for p in self._portfolio.active_positions:
            if (mode is not None and getattr(p, "feed_mode", "demo") != mode) or p.quarantine_reason:
                continue
            if p.booked_pnl_rupees:
                day = days.setdefault(today, DailyPnl(date=today))
                day.gross_pnl = round(day.gross_pnl + p.booked_pnl_rupees, 2)
                day.net_pnl = round(day.net_pnl + p.booked_pnl_rupees, 2)
        return sorted(days.values(), key=lambda d: d.date, reverse=True)

    def set_auto_trade(self, enabled: bool):
        self._portfolio.auto_trade_enabled = enabled
        self._enqueue_write("save_setting", ("auto_trade_enabled", str(enabled)))

    def set_setup_modes(self, modes: dict) -> None:
        """Merge `modes` (setup number -> off/index/stocks/all) into the saved switches."""
        merged = setup_switches.normalize_modes({**self._portfolio.setup_modes, **(modes or {})})
        self._portfolio.setup_modes = merged
        self._enqueue_write("save_setting", ("setup_modes", json.dumps(merged)))

    def set_default_lots(self, lots: int):
        self.runtime.set("default_lots", max(2, int(lots)))  # 2 lots minimum so Target 1 can book 50%

    def set_max_risk_per_trade(self, amount: float):
        self.runtime.set("max_risk_per_trade", max(500.0, float(amount)))

    def _apply_default_lots(self, value) -> None:
        self._portfolio.default_lots = int(value)
        self._enqueue_write("save_setting", ("default_lots", str(self._portfolio.default_lots)))

    def _apply_max_risk(self, value) -> None:
        self._portfolio.max_risk_per_trade = float(value)
        self._enqueue_write("save_setting", ("max_risk_per_trade", str(self._portfolio.max_risk_per_trade)))

    def _sync_portfolio_from_runtime(self) -> None:
        """Portfolio fields that mirror runtime settings take the stored/overridden value (used after load and reset)."""
        for key, attr in (("default_lots", "default_lots"), ("max_risk_per_trade", "max_risk_per_trade")):
            if self.runtime.is_overridden(key):
                setattr(self._portfolio, attr, self.runtime.get(key))

    async def reset(self) -> None:
        self._portfolio_generation += 1
        saved_modes = self._portfolio.setup_modes
        self._portfolio = PaperPortfolio(setup_modes=saved_modes)
        self._sync_portfolio_from_runtime()
        self._processed_signal_ids.clear()
        self._loss_cap_trips = {}  # a reset empties the day's P&L, so a stored trip no longer applies
        self._enqueue_write("save_setting", ("loss_cap_trips", "{}"))  # ...and must not come back on restart
        if self._write_queue is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = self._loop or asyncio.get_event_loop()
            fut = loop.create_future()
            self._enqueue_write("clear_all", None, generation=self._portfolio_generation, future=fut)
            await fut
        elif self.storage:
            self.storage.clear_all()

    def reset_sync(self) -> None:
        if self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.reset(), self._loop)
            fut.result(timeout=10.0)
        else:
            self._portfolio_generation += 1
            saved_modes = self._portfolio.setup_modes
            self._portfolio = PaperPortfolio(setup_modes=saved_modes)
            self._sync_portfolio_from_runtime()
            self._processed_signal_ids.clear()
            self._loss_cap_trips = {}
            if self.storage:
                self.storage.clear_all()
                self.storage.save_setting("loss_cap_trips", "{}")

    def reset_portfolio(self) -> None:
        self.reset_sync()


    # ---- telemetry helpers ----
    _SKIP_CODES = (
        ("kill switch", "KILL_SWITCH"), ("daily loss cap", "LOSS_CAP"), ("consecutive losses", "LOSS_STREAK_PAUSE"),
        ("max open positions", "MAX_OPEN_POSITIONS"), ("open premium notional", "MAX_OPEN_NOTIONAL"),
        ("max entries per day", "MAX_ENTRIES_PER_DAY"), ("entries today", "MAX_ENTRIES_PER_SYMBOL_DAY"),
        ("cooldown", "REENTRY_COOLDOWN"), ("already has an open position", "ALREADY_OPEN"),
        ("quote is", "QUOTE_STALE"), ("spread", "SPREAD_TOO_WIDE"), ("crossed market", "CROSSED_MARKET"),
        ("lot size unknown", "LOT_SIZE_UNKNOWN"), ("assumed delta", "DELTA_ASSUMED"),
    )

    @classmethod
    def _skip_code(cls, reason: str) -> str:
        low = reason.lower()
        for needle, code in cls._SKIP_CODES:
            if needle in low:
                return code
        return "OTHER"

    def _signal_metrics(self, signal: Signal) -> dict:
        rec = getattr(signal, "strike_recommendation", None)
        m = {"timeframe": signal.timeframe, "underlying_entry": signal.entry_price}
        if rec is not None:
            for attr in ("estimated_option_entry", "real_bid_price", "real_ask_price", "real_ltp", "lot_size", "quote_age_s"):
                v = getattr(rec, attr, None)
                if v is not None:
                    m[attr] = v
        return m

    def _log_skip(self, signal: Signal, feed_mode: str, code: str, reason: str = "", **extra) -> None:
        """Record why a signal was declined. Also marks nothing: callers keep their own processed-signal handling."""
        self.telemetry.decision(
            book=feed_mode, strategy=getattr(signal.setup_type, "value", str(signal.setup_type)), symbol=signal.symbol,
            side=signal.option_type, decision="SKIPPED", reason=code, signal_id=signal.id,
            metrics={**self._signal_metrics(signal), "detail": reason, **extra})

    def open_position_from_signal(
        self,
        signal: Signal,
        lots: Optional[int] = None,
        feed_mode: str = "demo"
    ) -> Optional[PaperPosition]:
        # Avoid duplicate trades on same signal ID
        if signal.id in self._processed_signal_ids:
            return None

        if feed_mode not in ("live", "demo"):
            logger.info("Skipping trade opening for feed_mode '%s' (not live or demo)", feed_mode)
            return None

        # P0-1: no new live entries outside the exchange session or after the entry cutoff.
        # (demo mode runs on synthetic offline data and is not tied to exchange hours)
        if feed_mode == "live" and not market_hours.is_entry_allowed():
            logger.info("Entry skipped for %s: outside entry window (session closed or past cutoff)", signal.symbol)
            self._log_skip(signal, feed_mode, "OUTSIDE_ENTRY_WINDOW")
            return None

        # Kill switch and daily loss cap stop every new entry, auto or manual.
        risk_block = self.risk_block_reason(feed_mode, pool="s11" if is_setup11(signal.setup_type) else "main")
        if risk_block:
            logger.info("Entry blocked for %s %s: %s", signal.symbol, signal.option_type, risk_block)
            self._processed_signal_ids.add(signal.id)
            self._log_skip(signal, feed_mode, self._skip_code(risk_block), risk_block)
            return None

        # P0-2: exposure guards (one position per contract, per stock+side, plus cooldown)
        block = self._exposure_block_reason(signal, lots, feed_mode)
        if block:
            logger.info("Entry blocked for %s %s: %s", signal.symbol, signal.option_type, block)
            self._processed_signal_ids.add(signal.id)
            self._log_skip(signal, feed_mode, self._skip_code(block), block)
            return None

        # Check re-entry gate: prevent consecutive stop-out churn in the same chop box
        last_closed = next(
            (p for p in reversed(self._portfolio.closed_trades) if p.symbol == signal.symbol and p.option_type == signal.option_type and not p.quarantine_reason
             and is_setup11(p.setup_type) == is_setup11(signal.setup_type)),
            None
        )
        if last_closed and last_closed.status == "STOPPED_OUT":
            is_s5 = (
                is_setup5(signal.setup_type)
            )
            if is_s5:
                failed_peak = last_closed.option_entry
                opt_entry = signal.strike_recommendation.estimated_option_entry
                if opt_entry <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} Setup 5: option entry {opt_entry} <= previous failed option price {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    self._log_skip(signal, feed_mode, "REENTRY_CHOP_GATE", "price not beyond the previous stopped-out entry")
                    return None
            elif signal.option_type == "CE":
                failed_peak = last_closed.underlying_entry
                if signal.entry_price <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} CE: entry {signal.entry_price} <= previous failed high {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    self._log_skip(signal, feed_mode, "REENTRY_CHOP_GATE", "price not beyond the previous stopped-out entry")
                    return None
            elif signal.option_type == "PE":
                failed_trough = last_closed.underlying_entry
                if signal.entry_price >= failed_trough:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} PE: entry {signal.entry_price} >= previous failed low {failed_trough} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    self._log_skip(signal, feed_mode, "REENTRY_CHOP_GATE", "price not beyond the previous stopped-out entry")
                    return None

        rec = signal.strike_recommendation
        if feed_mode == "live":
            sec_id = getattr(rec, "option_security_id", None)
            is_live = getattr(rec, "is_live_quote", False)
            real_ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
            real_ltp = float(getattr(rec, "real_ltp", 0.0) or 0.0)
            if not sec_id or not str(sec_id).strip() or not (is_live or real_ask > 0 or real_ltp > 0):
                logger.info(
                    f"Live position entry skipped for {signal.symbol}: contract unresolved or missing usable live option quote"
                )
                self._processed_signal_ids.add(signal.id)
                self._log_skip(signal, feed_mode, "NO_LIVE_QUOTE", "contract unresolved or no usable live option quote")
                return None

            # P1-3: reject stale or untradeable quotes (frozen last trade, wide/one-sided market).
            quote_block = self._quote_block_reason(
                rec, max_age=float(self.runtime.get("max_quote_age_seconds")),
                max_spread=float(self.runtime.get("max_entry_spread_pct")))
            if quote_block:
                logger.warning("DATA_QUALITY entry_blocked symbol=%s side=%s reason=%s", signal.symbol, signal.option_type, quote_block)
                self._processed_signal_ids.add(signal.id)
                self._log_skip(signal, feed_mode, self._skip_code(quote_block), quote_block)
                return None

        liq_block = liquidity_filter.check_recommendation(rec, signal.symbol, signal.option_type)
        if liq_block:
            self._processed_signal_ids.add(signal.id)
            self._log_skip(signal, feed_mode, "LIQUIDITY_FILTER", str(liq_block))
            return None

        lot_size = rec.lot_size

        p_signal = float(rec.estimated_option_entry)
        is_s5 = (
            is_setup5(signal.setup_type)
        )
        entry_estimated = False
        if getattr(rec, "real_ask_price", 0.0) is not None and float(rec.real_ask_price or 0.0) > 0:
            p_fill_entry = float(rec.real_ask_price)
        elif not is_s5 and getattr(rec, "real_ltp", 0.0) is not None and float(rec.real_ltp or 0.0) > 0:
            p_fill_entry = round(float(rec.real_ltp) * 1.001, 2)
        else:
            p_fill_entry = float(p_signal)
            entry_estimated = True
            logger.warning("DATA_QUALITY entry_estimated symbol=%s side=%s price=%s feed=%s (no live ask/ltp; fill modeled from signal)",
                           signal.symbol, signal.option_type, p_signal, feed_mode)

        # Size risk from the price we will actually fill at, not the signal candle close.
        risk_per_unit = max(0.1, abs(max(p_fill_entry, float(rec.estimated_option_entry)) - rec.option_sl_price))
        risk_per_lot = risk_per_unit * lot_size

        target_lots = lots if lots is not None else self._portfolio.default_lots
        lots_to_trade = target_lots

        if self._portfolio.max_risk_per_trade > 0 and risk_per_lot > 0:
            allowed_lots = int(self._portfolio.max_risk_per_trade // risk_per_lot)
            if allowed_lots < 1:
                logger.info(
                    f"Trade skipped for {signal.symbol}: risk per lot {risk_per_lot:.1f} exceeds max risk cap {self._portfolio.max_risk_per_trade:.1f}"
                )
                self._processed_signal_ids.add(signal.id)
                self._log_skip(signal, feed_mode, "RISK_PER_TRADE_TOO_HIGH",
                               risk_per_lot=round(risk_per_lot, 2), max_risk_per_trade=self._portfolio.max_risk_per_trade)
                return None
            lots_to_trade = min(target_lots, allowed_lots)
            if lots_to_trade < target_lots:
                logger.warning("Risk cap reduced %s from %d to %d lot(s)%s", signal.symbol, target_lots, lots_to_trade,
                               "; Target 1 will not book a partial" if lots_to_trade < 2 else "")

        lot_cap = int(self.runtime.get("max_lots_per_trade"))
        if lot_cap > 0 and lots_to_trade > lot_cap:
            logger.warning("Lot cap reduced %s from %d to %d lot(s)", signal.symbol, lots_to_trade, lot_cap)
            lots_to_trade = lot_cap

        self._processed_signal_ids.add(signal.id)
        qty = lot_size * lots_to_trade

        pos_id = f"POS_{signal.symbol}_{signal.option_type}_{int(market_hours.now_ist().timestamp())}_{uuid.uuid4().hex[:6]}"
        rec = signal.strike_recommendation

        entry_bid = getattr(rec, "real_bid_price", None)
        entry_bid = float(entry_bid) if entry_bid and float(entry_bid) > 0 else None
        entry_spread_pct = (
            round((p_fill_entry - entry_bid) / p_fill_entry * 100.0, 2)
            if entry_bid is not None and p_fill_entry > 0 and entry_bid <= p_fill_entry else None
        )
        entry_slippage = max(0.0, round(p_fill_entry - p_signal, 2))
        init_slip_cost = round(entry_slippage * qty, 2)

        pos = PaperPosition(
            id=pos_id,
            signal_id=signal.id,
            symbol=signal.symbol,
            option_type=signal.option_type,
            strike_symbol=rec.strike_symbol,
            timeframe=signal.timeframe,
            setup_type=signal.setup_type.value if hasattr(signal.setup_type, "value") else str(signal.setup_type),
            entry_time=_now_stamp()[0],
            entry_datetime=_now_stamp()[1],
            underlying_entry=signal.entry_price,
            underlying_sl=signal.stop_loss,
            underlying_target_1=signal.target_1,
            underlying_target_2=signal.target_2,
            option_entry=round(p_fill_entry, 2),
            option_sl=rec.option_sl_price,
            option_target_1=rec.option_target_1_price,
            option_target_2=rec.option_target_2_price,
            lot_size=lot_size,
            lots=lots_to_trade,
            quantity=qty,
            initial_lots=lots_to_trade,
            initial_quantity=qty,
            booked_lots=0,
            booked_pnl_rupees=0.0,
            current_underlying=signal.entry_price,
            current_option_price=round(p_fill_entry, 2),
            pnl_points=0.0,
            pnl_rupees=0.0,
            status="OPEN",
            option_security_id=getattr(rec, "option_security_id", None),
            feed_mode=feed_mode,
            theoretical_entry=round(p_signal, 2),
            entry_slippage=entry_slippage,
            theoretical_exit=None,
            exit_slippage=0.0,
            total_slippage_cost=init_slip_cost,
            gross_pnl=0.0,
            total_charges=0.0,
            net_pnl=0.0,
            charges_breakdown=None,
            entry_estimated=entry_estimated,
            entry_bid=entry_bid,
            entry_spread_pct=entry_spread_pct,
            option_volume=getattr(rec, "real_volume", None),
            option_oi=getattr(rec, "real_oi", None),
            bid_qty=getattr(rec, "real_bid_qty", None),
            ask_qty=getattr(rec, "real_ask_qty", None),
        )

        self._portfolio.active_positions.append(pos)
        self._recalculate_metrics()
        if not self._persist_entry(pos, signal.id):
            # The entry never reached storage: do not report a trade that would vanish on restart.
            self._portfolio.active_positions.remove(pos)
            self._processed_signal_ids.discard(signal.id)  # allow a retry once storage recovers
            self._recalculate_metrics()
            self._log_skip(signal, feed_mode, "STORAGE_WRITE_FAILED")
            return None
        self.telemetry.decision(
            book=feed_mode, strategy=pos.setup_type, symbol=pos.symbol, side=pos.option_type, decision="ENTERED",
            reason="SIGNAL_CONFIRMED", signal_id=signal.id, position_id=pos.id,
            metrics={**self._signal_metrics(signal), "lots": lots_to_trade, "fill": pos.option_entry,
                     "signal_price": pos.theoretical_entry, "entry_slippage": pos.entry_slippage,
                     "spread_pct": pos.entry_spread_pct, "risk_per_lot": round(risk_per_lot, 2),
                     "estimated_fill": entry_estimated})
        if self.on_position_opened:
            try:
                res = self.on_position_opened(pos)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.warning(f"Error executing on_position_opened callback: {e}")
        if self.on_live_entry:
            try:
                self.on_live_entry(pos, rec)
            except Exception:
                logger.error("Live routing entry hook failed for %s", pos.id, exc_info=True)
        return pos

    def on_signals_cycle(self, signals: list[Signal], feed_mode: str = "demo"):
        """Automatically open paper positions if auto-trade is enabled."""
        if not self._portfolio.auto_trade_enabled:
            return
        if feed_mode not in ("live", "demo"):
            return

        for sig in signals:
            if not getattr(sig, "is_confirmed", True):
                continue
            if sig.id not in self._processed_signal_ids:
                # Per-setup switch (off / indices only / stocks only / all) applies to auto-entry;
                # a trade the user places by hand is never blocked by it.
                modes = self._portfolio.setup_modes or setup_switches.DEFAULT_MODES
                switched_off = setup_switches.block_reason(modes, sig.setup_type, sig.symbol)
                if switched_off:
                    logger.info("Auto-entry skipped for %s: %s", sig.symbol, switched_off)
                    self._log_skip(sig, feed_mode, "SETUP_SWITCHED_OFF", switched_off)
                    self._processed_signal_ids.add(sig.id)
                    continue
                # Open position for new signals
                self.open_position_from_signal(sig, feed_mode=feed_mode)

from app.core.config import settings
paper_trader = PaperTradingEngine(db_path=settings.DB_PATH)
