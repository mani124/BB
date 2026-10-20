import asyncio
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal, is_setup5
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.services.notifier import notify
from app.core.config import settings
from app.services.paper_models import *  # noqa: F401,F403
from app.services.paper_models import _now_stamp, _parse_iso, _signed_slip, _view_mode  # noqa: F401
import logging

logger = logging.getLogger(__name__)



SPOT_GOVERNED = {"20", "21", "22", "23"}   # T315 and T315-F: exits follow the index, not the option premium


def _spot_governed(pos) -> bool:
    from app.services.setup_switches import setup_number
    return setup_number(pos.setup_type) in SPOT_GOVERNED


def _level_hit(pos, curr_spot, level: str, fresh_opt: Optional[float] = None) -> bool:
    """Whether spot or the option price currently sits beyond the stop ('sl'), Target 1 ('t1') or Target 2 ('t2').
    `fresh_opt` is this cycle's quote (LTP or bid) when one arrived; an unquoted (zero) price never counts as a breach."""
    ce = pos.option_type == "CE"
    opt = fresh_opt if fresh_opt is not None and fresh_opt > 0 else pos.current_option_price
    opt_ok = bool(opt and opt > 0) and not (_spot_governed(pos) and curr_spot is not None)
    if level == "sl":
        spot_hit = curr_spot is not None and (curr_spot <= pos.underlying_sl if ce else curr_spot >= pos.underlying_sl)
        return spot_hit or (opt_ok and opt <= pos.option_sl)
    target_spot = pos.underlying_target_1 if level == "t1" else pos.underlying_target_2
    target_opt = pos.option_target_1 if level == "t1" else pos.option_target_2
    spot_hit = curr_spot is not None and (curr_spot >= target_spot if ce else curr_spot <= target_spot)
    return spot_hit or (opt_ok and opt >= target_opt)


def _fresh_quote(bid, ltp) -> Optional[float]:
    for v in (ltp, bid):
        if v is not None and float(v) > 0:
            return float(v)
    return None


def _pending_is_stop(pos) -> bool:
    reason = pos.pending_spot_exit or ""
    return "Stop-Loss" in reason or "SL" in reason

class PaperExitsMixin:
    """Methods split out of PaperTradingEngine (no behaviour change)."""

    def _finalize_closed_position(
        self,
        pos: PaperPosition,
        theoretical_exit: float,
        status: Literal["OPEN", "TARGET_1", "TARGET_2", "STOPPED_OUT", "CLOSED"],
        reason: str,
        exit_time: str,
        real_bid_price: Optional[float] = None,
        real_opt_price: Optional[float] = None,
    ):
        # 1. Determine fill price P_fill_exit
        if real_bid_price is not None and float(real_bid_price) > 0:
            p_fill_exit = float(real_bid_price)
        elif real_opt_price is not None and float(real_opt_price) > 0:
            opt_val = float(real_opt_price)
            if opt_val < float(theoretical_exit):
                p_fill_exit = opt_val
            else:
                p_fill_exit = round(opt_val * 0.999, 2)
        elif pos.feed_mode == "live":
            p_fill_exit = float(pos.current_option_price)
            if "(Modeled" not in reason:
                reason = f"{reason} (Modeled: Last Price)"
        else:
            p_fill_exit = float(theoretical_exit)

        # 2. Exit slippage: signed. Positive = worse than the intended level; negative =
        # price improvement (e.g. a gap through a target). A fill far beyond the level is
        # labelled as a gap so it is not mistaken for a clean level hit.
        exit_slippage = _signed_slip(theoretical_exit, p_fill_exit)
        gap_pct = float(self.runtime.get("gap_exit_pct"))
        level = float(theoretical_exit)
        if gap_pct > 0 and level > 0 and "(Gap" not in reason and status in ("STOPPED_OUT", "TARGET_2"):
            move_pct = abs(p_fill_exit - level) / level * 100.0
            if move_pct >= gap_pct:
                reason = f"{reason} (Gap Exit: filled {p_fill_exit:.2f} vs level {level:.2f})"

        # 3. Update position state and P&L
        pos.status = status
        pos.exit_time = exit_time
        pos.exit_datetime = _now_stamp()[1]
        pos.exit_reason = reason
        pos.theoretical_exit = round(float(theoretical_exit), 2)
        pos.exit_slippage = exit_slippage
        pos.current_option_price = round(p_fill_exit, 2)
        pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
        runner_pnl = round(pos.pnl_points * pos.quantity, 2)
        pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)

        # 4. Total slippage cost
        init_qty = pos.initial_quantity if (pos.initial_quantity and pos.initial_quantity > 0) else pos.quantity
        runner_qty = pos.quantity
        entry_slip_cost = round(pos.entry_slippage * init_qty, 2)
        runner_slip_cost = round(pos.exit_slippage * runner_qty, 2)
        booked_slip_cost = round(getattr(pos, "booked_slippage_cost", 0.0), 2)
        pos.total_slippage_cost = round(entry_slip_cost + booked_slip_cost + runner_slip_cost, 2)

        # 5. Charges calculation
        orders_count = 3 if pos.booked_lots > 0 else 2
        sell_price = max(0.0, round(pos.option_entry + (pos.pnl_rupees / init_qty), 2)) if init_qty > 0 else pos.current_option_price
        breakdown = calculate_option_trade_charges(
            buy_price=pos.option_entry,
            sell_price=sell_price,
            quantity=init_qty,
            orders_count=orders_count,
        )

        pos.gross_pnl = round(pos.pnl_rupees, 2)
        pos.total_charges = breakdown.total_charges
        pos.net_pnl = round(pos.gross_pnl - pos.total_charges, 2)
        pos.charges_breakdown = breakdown.model_dump()

        try:
            self.telemetry.decision(
                book=pos.feed_mode, strategy=pos.setup_type, symbol=pos.symbol, side=pos.option_type, decision="EXITED",
                reason=status if status != "CLOSED" else "MANUAL_OR_RULE_EXIT", position_id=pos.id,
                metrics={"exit_reason": pos.exit_reason, "net_pnl": pos.net_pnl, "gross_pnl": pos.gross_pnl,
                         "charges": pos.total_charges, "entry": pos.option_entry, "exit": pos.current_option_price,
                         "theoretical_exit": pos.theoretical_exit, "exit_slippage": pos.exit_slippage,
                         "total_slippage_cost": pos.total_slippage_cost, "lots_booked_early": pos.booked_lots})
            self.telemetry.close_trade(pos, pos.gross_pnl)
        except Exception:
            logger.debug("telemetry exit hook failed", exc_info=True)

        if status in ("STOPPED_OUT", "TARGET_1", "TARGET_2"):
            label = "Stop hit" if status == "STOPPED_OUT" else "Target hit"
            notify(
                "position_closed",
                f"{label}: {pos.symbol} {pos.option_type} ({pos.setup_type}) closed at {pos.current_option_price:.2f}, "
                f"net P&L {pos.net_pnl:+,.0f}. {pos.exit_reason or ''}".strip(),
                dedupe_key=f"closed:{pos.id}",
                min_interval=3600,
            )

    def _emit_position_update(self, pos: PaperPosition) -> None:
        """Tell live order routing (if wired in) that a position changed size or closed."""
        cb = self.on_position_update
        if cb is None:
            return
        try:
            cb(pos)
        except Exception:
            logger.error("Live routing update hook failed for %s", pos.id, exc_info=True)

    @staticmethod
    def _mark_open_estimates(pos: PaperPosition) -> None:
        """Unrealised P&L of the open lots and the net result if the trade closed now, using the
        same charge model as _finalize_closed_position."""
        runner = round(pos.pnl_points * pos.quantity, 2)
        pos.unrealized_pnl_rupees = runner
        init_qty = pos.initial_quantity if (pos.initial_quantity and pos.initial_quantity > 0) else pos.quantity
        gross = round(pos.booked_pnl_rupees + runner, 2)
        if init_qty <= 0:
            pos.est_exit_charges, pos.est_net_pnl = 0.0, gross
            return
        sell_price = max(0.0, round(pos.option_entry + gross / init_qty, 2))
        breakdown = calculate_option_trade_charges(
            buy_price=pos.option_entry,
            sell_price=sell_price,
            quantity=init_qty,
            orders_count=3 if pos.booked_lots > 0 else 2,
        )
        pos.est_exit_charges = breakdown.total_charges
        pos.est_net_pnl = round(gross - breakdown.total_charges, 2)

    def update_market_prices(
        self,
        price_map: dict[str, float],
        option_price_map: Optional[dict[str, float]] = None,
        feed_mode: Optional[str] = None,
        option_bid_map: Optional[dict[str, float]] = None,
    ):
        """Update active positions with current underlying prices and live option prices from Dhan."""
        delta = 0.55
        now_str = _now_stamp()[0]
        if feed_mode is not None:
            spots = self.__dict__.setdefault("_last_spot", {})
            for sym, px in price_map.items():
                if px:
                    spots[(feed_mode, sym)] = (float(px), time.monotonic())
        still_active = []
        changed_active: list[PaperPosition] = []
        closed_before = len(self._portfolio.closed_trades)

        for pos in self._portfolio.active_positions:
            orig_state = (
                pos.current_underlying, pos.current_option_price, pos.pnl_points,
                pos.pnl_rupees, pos.status, pos.lots, pos.quantity, pos.underlying_sl,
                pos.option_sl, getattr(pos, "pending_spot_exit", None),
                getattr(pos, "pending_spot_tp1", False)
            )

            if feed_mode is not None and getattr(pos, "feed_mode", "demo") != feed_mode:
                still_active.append(pos)
                continue

            curr_spot = price_map.get(pos.symbol)
            if curr_spot is not None:
                pos.current_underlying = round(curr_spot, 2)

            is_opt_chart_setup = (
                is_setup5(pos.setup_type)
            )

            # Check if live option quote is directly provided from Dhan (NSE_FNO)
            real_opt_price = None
            if option_price_map:
                if pos.option_security_id:
                    real_opt_price = option_price_map.get(str(pos.option_security_id)) or option_price_map.get(pos.option_security_id)
                if real_opt_price is None:
                    real_opt_price = option_price_map.get(pos.id) or option_price_map.get(pos.strike_symbol)

            real_bid_price = None
            if option_bid_map:
                real_bid_price = option_bid_map.get(pos.id)
                if real_bid_price is None and pos.option_security_id:
                    real_bid_price = option_bid_map.get(str(pos.option_security_id)) or option_bid_map.get(pos.option_security_id)
                if real_bid_price is None and pos.strike_symbol:
                    real_bid_price = option_bid_map.get(pos.strike_symbol)

            if real_opt_price is not None and float(real_opt_price) > 0:
                pos.current_option_price = round(float(real_opt_price), 2)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif pos.feed_mode == "live" or pos.option_security_id:
                # Live contract: keep last known real price, do not synthesize fake delta
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif is_opt_chart_setup:
                # Setup 5: Option chart scalp - maintain current option price if no new tick
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif curr_spot is not None and pos.feed_mode == "demo":
                # Fallback to delta estimation only for demo/offline signals lacking option_security_id
                if pos.option_type == "CE":
                    spot_move = curr_spot - pos.underlying_entry
                    est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                else:
                    spot_move = pos.underlying_entry - curr_spot
                    est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                pos.current_option_price = round(est_opt, 1)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 1)
            else:
                still_active.append(pos)
                continue

            has_fresh_quote = (
                (real_bid_price is not None and float(real_bid_price) > 0)
                or (real_opt_price is not None and float(real_opt_price) > 0)
            )

            # Index-governed setups (20-23) are analysed and exited on the index chart only: once spot is known, the
            # option premium (spread, time decay) never triggers their stop or targets. Premium levels are only a
            # fallback when no spot price arrived.
            opt_levels = not (_spot_governed(pos) and curr_spot is not None)

            # A stop queued while no live quote existed: with a fresh quote, act on it only if the stop is still
            # breached. If price has recovered above it, drop the stale flag and evaluate normally. Targets stay
            # pending: they filled at the touch and are booked at the real quote (labelled a late fill if lower).
            if has_fresh_quote and getattr(pos, "pending_spot_exit", None) and _pending_is_stop(pos) \
                    and not _level_hit(pos, curr_spot, "sl", _fresh_quote(real_bid_price, real_opt_price)):
                logger.info("Pending stop for %s dropped: price recovered above the stop before a fresh quote arrived", pos.id)
                pos.pending_spot_exit = None
                # a bid-only update leaves the old (breached) last price in place; take the fresh quote so it cannot re-trigger
                fresh = _fresh_quote(real_bid_price, real_opt_price)
                if fresh is not None:
                    pos.current_option_price = round(fresh, 2)
                    pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)

            # Check if pending spot exit can now execute with fresh quote
            if getattr(pos, "pending_spot_exit", None) and has_fresh_quote:
                pending_reason = pos.pending_spot_exit
                theo_exit = pos.option_sl if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else pos.option_target_2
                status_to_set = "STOPPED_OUT" if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else "TARGET_2"
                if status_to_set == "TARGET_2":
                    # The exit still happens (spot touched Target 2), but a quote that has since fallen back below the
                    # target is not a Target 2 trade: record it as a plain close so stats and labels stay honest.
                    px = real_bid_price if (real_bid_price and float(real_bid_price) > 0) else real_opt_price
                    if px and float(px) < float(theo_exit):
                        status_to_set = "CLOSED"
                        pending_reason = f"{pending_reason} (Late Fill: quote {float(px):.2f} below target {float(theo_exit):.2f})"
                self._finalize_closed_position(
                    pos=pos,
                    theoretical_exit=theo_exit,
                    status=status_to_set,
                    reason=pending_reason,
                    exit_time=now_str,
                    real_bid_price=real_bid_price,
                    real_opt_price=real_opt_price,
                )
                self._portfolio.closed_trades.append(pos)
                self._enqueue_write("upsert", pos)
                continue

            # --- SETUP 5: EXITS BASED EXCLUSIVELY ON OPTION CHARTS ---
            if is_opt_chart_setup:
                if pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                elif pos.current_option_price >= pos.option_target_2:
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                elif pos.current_option_price >= pos.option_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else pos.current_option_price
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    else:
                        # Single lot cannot be split: no partial at Target 1, the whole lot
                        # runs with its stop moved to entry (breakeven) below.
                        logger.info("T1 %s: %d lot cannot book 50%%; no partial, stop to breakeven", pos.symbol, pos.lots)
                    pos.option_sl = pos.option_entry
                    self._enqueue_write("upsert", pos)

                # Keep the headline P&L live. This branch used to skip the update below, so a
                # Setup 5 position showed +33 pts but P&L of 0.
                pos.pnl_rupees = round(pos.booked_pnl_rupees + round(pos.pnl_points * pos.quantity, 2), 2)
                if orig_state[3] != pos.pnl_rupees or orig_state[1] != pos.current_option_price:
                    changed_active.append(pos)
                still_active.append(pos)
                continue

            # --- SETUPS 1-4 & 6-8: EXITS BASED ON UNDERLYING SPOT OR OPTION LEVELS ---
            if pos.option_type == "CE":
                # Check SL
                if (curr_spot is not None and curr_spot <= pos.underlying_sl) or (opt_levels and pos.current_option_price <= pos.option_sl):
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = reason
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot >= pos.underlying_target_2) or (opt_levels and pos.current_option_price >= pos.option_target_2):
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 1
                hit_ce_tp1 = (
                    ((curr_spot is not None and curr_spot >= pos.underlying_target_1) or (opt_levels and pos.current_option_price >= pos.option_target_1))
                    and pos.status == "OPEN"
                ) or getattr(pos, "pending_spot_tp1", False)

                if hit_ce_tp1:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_tp1 = True
                        still_active.append(pos)
                        continue
                    pos.pending_spot_tp1 = False
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else (real_opt_price if (real_opt_price and real_opt_price > 0) else pos.current_option_price)
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    else:
                        # Single lot cannot be split: no partial at Target 1, the whole lot
                        # runs with its stop moved to entry (breakeven) below.
                        logger.info("T1 %s: %d lot cannot book 50%%; no partial, stop to breakeven", pos.symbol, pos.lots)
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            else:  # PE
                # Check SL
                if (curr_spot is not None and curr_spot >= pos.underlying_sl) or (opt_levels and pos.current_option_price <= pos.option_sl):
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = reason
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot <= pos.underlying_target_2) or (opt_levels and pos.current_option_price >= pos.option_target_2):
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 1
                hit_pe_tp1 = (
                    ((curr_spot is not None and curr_spot <= pos.underlying_target_1) or (opt_levels and pos.current_option_price >= pos.option_target_1))
                    and pos.status == "OPEN"
                ) or getattr(pos, "pending_spot_tp1", False)

                if hit_pe_tp1:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_tp1 = True
                        still_active.append(pos)
                        continue
                    pos.pending_spot_tp1 = False
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else (real_opt_price if (real_opt_price and real_opt_price > 0) else pos.current_option_price)
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    else:
                        # Single lot cannot be split: no partial at Target 1, the whole lot
                        # runs with its stop moved to entry (breakeven) below.
                        logger.info("T1 %s: %d lot cannot book 50%%; no partial, stop to breakeven", pos.symbol, pos.lots)
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            runner_pnl = round(pos.pnl_points * pos.quantity, 2)
            pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
            self.telemetry.track(pos)
            new_state = (
                pos.current_underlying, pos.current_option_price, pos.pnl_points,
                pos.pnl_rupees, pos.status, pos.lots, pos.quantity, pos.underlying_sl,
                pos.option_sl, getattr(pos, "pending_spot_exit", None),
                getattr(pos, "pending_spot_tp1", False)
            )
            if orig_state != new_state:
                changed_active.append(pos)
            still_active.append(pos)

        self._portfolio.active_positions = still_active
        self._recalculate_metrics()
        if changed_active:
            self._enqueue_write("batch_upsert", list(changed_active))
        if self.on_position_update is not None:
            for p in self._portfolio.closed_trades[closed_before:]:
                self._emit_position_update(p)
            for p in still_active:
                self._emit_position_update(p)

    def close_position(
        self,
        position_id: str,
        reason: str = "MANUAL_EXIT",
        exit_price: Optional[float] = None,
        real_bid_price: Optional[float] = None,
        real_opt_price: Optional[float] = None,
    ) -> Optional[PaperPosition]:
        for i, pos in enumerate(self._portfolio.active_positions):
            if pos.id == position_id:
                # F8: In live mode, derive theoretical exit strictly from server-owned observations
                if pos.feed_mode == "live":
                    if real_opt_price is not None and float(real_opt_price) > 0:
                        theo_exit = float(real_opt_price)
                    elif real_bid_price is not None and float(real_bid_price) > 0:
                        theo_exit = float(real_bid_price)
                    else:
                        theo_exit = pos.current_option_price
                else:
                    if exit_price is not None and exit_price > 0:
                        theo_exit = exit_price
                    elif real_opt_price is not None and float(real_opt_price) > 0:
                        theo_exit = float(real_opt_price)
                    else:
                        theo_exit = pos.current_option_price
                self._finalize_closed_position(
                    pos=pos,
                    theoretical_exit=theo_exit,
                    status="CLOSED",
                    reason=reason,
                    exit_time=_now_stamp()[0],
                    real_bid_price=real_bid_price,
                    real_opt_price=real_opt_price,
                )
                closed = self._portfolio.active_positions.pop(i)
                self._portfolio.closed_trades.append(closed)
                self._recalculate_metrics()
                self._enqueue_write("upsert", closed)
                self._emit_position_update(closed)
                return closed
        return None

    def _recalculate_metrics(self):
        counted = [p for p in self._portfolio.closed_trades if not p.quarantine_reason]
        closed_pnl = sum(p.pnl_rupees for p in counted)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in self._portfolio.active_positions)
        realized = closed_pnl + active_booked_pnl
        unrealized = sum(round(p.pnl_points * p.quantity, 2) for p in self._portfolio.active_positions)
        for p in self._portfolio.active_positions:
            self._mark_open_estimates(p)
        unrealized_charges = sum(p.est_exit_charges for p in self._portfolio.active_positions)

        # Same rule as the per-book views and the daily table: net of charges, breakeven is neither.
        from app.services.paper_trader import _outcome_pnl
        wins = sum(1 for p in counted if _outcome_pnl(p) > 0)
        losses = sum(1 for p in counted if _outcome_pnl(p) < 0)
        total_closed = len(counted)

        self._portfolio.total_realized_pnl = round(realized, 2)
        self._portfolio.total_unrealized_pnl = round(unrealized, 2)
        self._portfolio.total_unrealized_charges = round(unrealized_charges, 2)
        self._portfolio.total_unrealized_net = round(unrealized - unrealized_charges, 2)
        self._portfolio.total_pnl = round(realized + unrealized, 2)
        self._portfolio.winning_trades_count = wins
        self._portfolio.losing_trades_count = losses
        self._portfolio.total_trades_count = total_closed
        self._portfolio.closed_trades_count = len(self._portfolio.closed_trades)
        self._portfolio.win_rate_pct = round((wins / total_closed * 100.0) if total_closed > 0 else 0.0, 1)

        total_gross = sum(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees for p in counted)
        total_charges = sum(getattr(p, "total_charges", 0.0) for p in counted)
        total_net = sum(getattr(p, "net_pnl", 0.0) for p in counted)
        total_slip_cost = sum(getattr(p, "total_slippage_cost", 0.0) for p in counted)
        avg_slip_pts = (
            sum((getattr(p, "entry_slippage", 0.0) + getattr(p, "exit_slippage", 0.0)) for p in counted) / total_closed
            if total_closed > 0 else 0.0
        )

        self._portfolio.total_gross_pnl = round(total_gross, 2)
        self._portfolio.total_charges = round(total_charges, 2)
        self._portfolio.total_net_pnl = round(total_net, 2)
        self._portfolio.total_slippage_cost = round(total_slip_cost, 2)
        self._portfolio.avg_slippage_points = round(avg_slip_pts, 2)
