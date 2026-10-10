import asyncio
import uuid
import logging
from datetime import datetime
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal
from app.services.strike_selector import get_lot_size

logger = logging.getLogger(__name__)

class PaperPosition(BaseModel):
    id: str
    signal_id: str
    symbol: str
    option_type: Literal["CE", "PE"]
    strike_symbol: str
    timeframe: str
    setup_type: str
    entry_time: str
    underlying_entry: float
    underlying_sl: float
    underlying_target_1: float
    underlying_target_2: float
    option_entry: float
    option_sl: float
    option_target_1: float
    option_target_2: float
    lot_size: int
    lots: int
    quantity: int
    current_underlying: float
    current_option_price: float
    pnl_points: float
    pnl_rupees: float
    status: Literal["OPEN", "TARGET_1", "TARGET_2", "STOPPED_OUT", "CLOSED"]
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    initial_lots: Optional[int] = None
    initial_quantity: Optional[int] = None
    booked_lots: int = 0
    booked_pnl_rupees: float = 0.0
    booked_slippage_cost: float = 0.0
    pending_spot_exit: Optional[str] = None
    option_security_id: Optional[str] = None
    feed_mode: str = "demo"  # "demo" or "live"
    theoretical_entry: float = 0.0
    entry_slippage: float = 0.0
    theoretical_exit: Optional[float] = None
    exit_slippage: float = 0.0
    total_slippage_cost: float = 0.0
    gross_pnl: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0
    charges_breakdown: Optional[dict] = None

class PaperPortfolio(BaseModel):
    active_positions: list[PaperPosition] = []
    closed_trades: list[PaperPosition] = []
    auto_trade_enabled: bool = True
    default_lots: int = 2
    max_risk_per_trade: float = 4000.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    win_rate_pct: float = 0.0
    total_trades_count: int = 0
    winning_trades_count: int = 0
    losing_trades_count: int = 0
    total_gross_pnl: float = 0.0
    total_slippage_cost: float = 0.0
    avg_slippage_points: float = 0.0
    total_charges: float = 0.0
    total_net_pnl: float = 0.0

class PaperTradingEngine:
    """Manages paper trading execution, position monitoring, and analytics."""

    def __init__(self, db_path: Optional[str] = None):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids: set[str] = set()
        self.storage = None
        self.on_position_opened: Optional[Callable[[PaperPosition], Any]] = None
        if db_path is not None:
            from app.services.paper_storage import PaperStorage
            self.storage = PaperStorage(db_path)
            self._load_from_storage()

    def _load_from_storage(self):
        if not self.storage:
            return
        active, closed = self.storage.load_all_positions()
        self._portfolio.active_positions = active
        self._portfolio.closed_trades = closed
        self._processed_signal_ids = self.storage.load_processed_signals()

        saved_auto = self.storage.load_setting("auto_trade_enabled")
        if saved_auto is not None:
            self._portfolio.auto_trade_enabled = (saved_auto.lower() == "true")

        saved_lots = self.storage.load_setting("default_lots")
        if saved_lots is not None:
            try:
                self._portfolio.default_lots = int(saved_lots)
            except ValueError:
                pass

        saved_risk = self.storage.load_setting("max_risk_per_trade")
        if saved_risk is not None:
            try:
                self._portfolio.max_risk_per_trade = float(saved_risk)
            except ValueError:
                pass

        self._recalculate_metrics()

    def get_portfolio(self, mode: Optional[str] = None) -> PaperPortfolio:
        self._recalculate_metrics()
        if not mode:
            return self._portfolio

        active = [p for p in self._portfolio.active_positions if getattr(p, "feed_mode", "demo") == mode]
        closed = [p for p in self._portfolio.closed_trades if getattr(p, "feed_mode", "demo") == mode]
        closed_pnl = sum(p.pnl_rupees for p in closed)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in active)
        realized = round(closed_pnl + active_booked_pnl, 2)
        unrealized = round(sum(round(p.pnl_points * p.quantity, 2) for p in active), 2)
        total = round(realized + unrealized, 2)
        total_trades = len(closed)
        winning = sum(1 for p in closed if p.pnl_rupees > 0)
        losing = sum(1 for p in closed if p.pnl_rupees <= 0)
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
            closed_trades=closed,
            auto_trade_enabled=self._portfolio.auto_trade_enabled,
            default_lots=self._portfolio.default_lots,
            max_risk_per_trade=self._portfolio.max_risk_per_trade,
            total_realized_pnl=realized,
            total_unrealized_pnl=unrealized,
            total_pnl=total,
            win_rate_pct=win_rate,
            total_trades_count=total_trades,
            winning_trades_count=winning,
            losing_trades_count=losing,
            total_gross_pnl=round(total_gross, 2),
            total_slippage_cost=round(total_slip_cost, 2),
            avg_slippage_points=round(avg_slip_pts, 2),
            total_charges=round(total_charges, 2),
            total_net_pnl=round(total_net, 2)
        )

    def set_auto_trade(self, enabled: bool):
        self._portfolio.auto_trade_enabled = enabled
        if self.storage:
            self.storage.save_setting("auto_trade_enabled", str(enabled))

    def set_default_lots(self, lots: int):
        self._portfolio.default_lots = max(1, lots)
        if self.storage:
            self.storage.save_setting("default_lots", str(self._portfolio.default_lots))

    def set_max_risk_per_trade(self, amount: float):
        self._portfolio.max_risk_per_trade = max(500.0, float(amount))
        if self.storage:
            self.storage.save_setting("max_risk_per_trade", str(self._portfolio.max_risk_per_trade))

    def reset(self):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids.clear()
        if self.storage:
            self.storage.clear_all()

    def reset_portfolio(self):
        self.reset()

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

        # Check re-entry gate: prevent consecutive stop-out churn in the same chop box
        last_closed = next(
            (p for p in reversed(self._portfolio.closed_trades) if p.symbol == signal.symbol and p.option_type == signal.option_type),
            None
        )
        if last_closed and last_closed.status == "STOPPED_OUT":
            is_s5 = (
                signal.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
                or "Setup 5" in str(signal.setup_type)
            )
            if is_s5:
                failed_peak = last_closed.option_entry
                opt_entry = signal.strike_recommendation.estimated_option_entry
                if opt_entry <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} Setup 5: option entry {opt_entry} <= previous failed option price {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None
            elif signal.option_type == "CE":
                failed_peak = last_closed.underlying_entry
                if signal.entry_price <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} CE: entry {signal.entry_price} <= previous failed high {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None
            elif signal.option_type == "PE":
                failed_trough = last_closed.underlying_entry
                if signal.entry_price >= failed_trough:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} PE: entry {signal.entry_price} >= previous failed low {failed_trough} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None

        rec = signal.strike_recommendation
        lot_size = rec.lot_size

        risk_per_unit = max(0.1, abs(rec.estimated_option_entry - rec.option_sl_price))
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
                return None
            lots_to_trade = min(target_lots, allowed_lots)

        self._processed_signal_ids.add(signal.id)
        qty = lot_size * lots_to_trade

        pos_id = f"POS_{signal.symbol}_{signal.option_type}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        rec = signal.strike_recommendation

        p_signal = float(rec.estimated_option_entry)
        is_s5 = (
            signal.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
            or "Setup 5" in str(signal.setup_type)
        )
        if getattr(rec, "real_ask_price", 0.0) is not None and float(rec.real_ask_price or 0.0) > 0:
            p_fill_entry = float(rec.real_ask_price)
        elif not is_s5 and getattr(rec, "real_ltp", 0.0) is not None and float(rec.real_ltp or 0.0) > 0:
            p_fill_entry = round(float(rec.real_ltp) * 1.001, 2)
        else:
            p_fill_entry = float(p_signal)

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
            entry_time=datetime.now().strftime("%H:%M:%S"),
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
        )

        self._portfolio.active_positions.append(pos)
        self._recalculate_metrics()
        if self.storage:
            self.storage.upsert_position(pos)
            self.storage.add_processed_signal(signal.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
                # Open position for new signals
                self.open_position_from_signal(sig, feed_mode=feed_mode)

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
        else:
            p_fill_exit = float(theoretical_exit)

        # 2. Exit slippage
        exit_slippage = max(0.0, round(float(theoretical_exit) - p_fill_exit, 2))

        # 3. Update position state and P&L
        pos.status = status
        pos.exit_time = exit_time
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

    def update_market_prices(
        self,
        price_map: dict[str, float],
        option_price_map: Optional[dict[str, float]] = None,
        feed_mode: Optional[str] = None,
        option_bid_map: Optional[dict[str, float]] = None,
    ):
        """Update active positions with current underlying prices and live option prices from Dhan."""
        delta = 0.55
        now_str = datetime.now().strftime("%H:%M:%S")
        still_active = []

        for pos in self._portfolio.active_positions:
            if feed_mode is not None and getattr(pos, "feed_mode", "demo") != feed_mode:
                still_active.append(pos)
                continue

            curr_spot = price_map.get(pos.symbol)
            if curr_spot is not None:
                pos.current_underlying = round(curr_spot, 2)

            is_opt_chart_setup = (
                pos.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
                or "Setup 5" in str(pos.setup_type)
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

            # Check if pending spot exit can now execute with fresh quote
            if getattr(pos, "pending_spot_exit", None) and has_fresh_quote:
                pending_reason = pos.pending_spot_exit
                theo_exit = pos.option_sl if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else pos.option_target_2
                status_to_set = "STOPPED_OUT" if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else "TARGET_2"
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
                if self.storage:
                    self.storage.upsert_position(pos)
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
                    if self.storage:
                        self.storage.upsert_position(pos)
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
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                elif pos.current_option_price >= pos.option_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else pos.current_option_price
                        tp1_slippage = max(0.0, round(pos.option_target_1 - tp1_fill, 2))
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.option_sl = pos.option_entry
                    if self.storage:
                        self.storage.upsert_position(pos)

                still_active.append(pos)
                continue

            # --- SETUPS 1-4 & 6-8: EXITS BASED ON UNDERLYING SPOT OR OPTION LEVELS ---
            if pos.option_type == "CE":
                # Check SL
                if (curr_spot is not None and curr_spot <= pos.underlying_sl) or pos.current_option_price <= pos.option_sl:
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
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot >= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
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
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 1
                elif ((curr_spot is not None and curr_spot >= pos.underlying_target_1) or pos.current_option_price >= pos.option_target_1) and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else pos.current_option_price
                        tp1_slippage = max(0.0, round(pos.option_target_1 - tp1_fill, 2))
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            else:  # PE
                # Check SL
                if (curr_spot is not None and curr_spot >= pos.underlying_sl) or pos.current_option_price <= pos.option_sl:
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
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot <= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
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
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 1
                elif ((curr_spot is not None and curr_spot <= pos.underlying_target_1) or pos.current_option_price >= pos.option_target_1) and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else pos.current_option_price
                        tp1_slippage = max(0.0, round(pos.option_target_1 - tp1_fill, 2))
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            runner_pnl = round(pos.pnl_points * pos.quantity, 2)
            pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
            still_active.append(pos)

        self._portfolio.active_positions = still_active
        self._recalculate_metrics()
        if self.storage:
            for p in still_active:
                self.storage.upsert_position(p)

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
                theo_exit = exit_price if (exit_price is not None and exit_price > 0) else pos.current_option_price
                self._finalize_closed_position(
                    pos=pos,
                    theoretical_exit=theo_exit,
                    status="CLOSED",
                    reason=reason,
                    exit_time=datetime.now().strftime("%H:%M:%S"),
                    real_bid_price=real_bid_price,
                    real_opt_price=real_opt_price,
                )
                closed = self._portfolio.active_positions.pop(i)
                self._portfolio.closed_trades.append(closed)
                self._recalculate_metrics()
                if self.storage:
                    self.storage.upsert_position(closed)
                return closed
        return None

    def _recalculate_metrics(self):
        closed_pnl = sum(p.pnl_rupees for p in self._portfolio.closed_trades)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in self._portfolio.active_positions)
        realized = closed_pnl + active_booked_pnl
        unrealized = sum(round(p.pnl_points * p.quantity, 2) for p in self._portfolio.active_positions)
        
        wins = sum(1 for p in self._portfolio.closed_trades if p.pnl_rupees > 0)
        losses = sum(1 for p in self._portfolio.closed_trades if p.pnl_rupees < 0)
        total_closed = len(self._portfolio.closed_trades)

        self._portfolio.total_realized_pnl = round(realized, 2)
        self._portfolio.total_unrealized_pnl = round(unrealized, 2)
        self._portfolio.total_pnl = round(realized + unrealized, 2)
        self._portfolio.winning_trades_count = wins
        self._portfolio.losing_trades_count = losses
        self._portfolio.total_trades_count = total_closed
        self._portfolio.win_rate_pct = round((wins / total_closed * 100.0) if total_closed > 0 else 0.0, 1)

        total_gross = sum(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees for p in self._portfolio.closed_trades)
        total_charges = sum(getattr(p, "total_charges", 0.0) for p in self._portfolio.closed_trades)
        total_net = sum(getattr(p, "net_pnl", 0.0) for p in self._portfolio.closed_trades)
        total_slip_cost = sum(getattr(p, "total_slippage_cost", 0.0) for p in self._portfolio.closed_trades)
        avg_slip_pts = (
            sum((getattr(p, "entry_slippage", 0.0) + getattr(p, "exit_slippage", 0.0)) for p in self._portfolio.closed_trades) / total_closed
            if total_closed > 0 else 0.0
        )

        self._portfolio.total_gross_pnl = round(total_gross, 2)
        self._portfolio.total_charges = round(total_charges, 2)
        self._portfolio.total_net_pnl = round(total_net, 2)
        self._portfolio.total_slippage_cost = round(total_slip_cost, 2)
        self._portfolio.avg_slippage_points = round(avg_slip_pts, 2)

from app.core.config import settings
paper_trader = PaperTradingEngine(db_path=settings.DB_PATH)
