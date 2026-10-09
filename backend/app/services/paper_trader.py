import uuid
import logging
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel
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
    option_security_id: Optional[str] = None
    feed_mode: str = "demo"  # "demo" or "live"

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

class PaperTradingEngine:
    """Manages paper trading execution, position monitoring, and analytics."""

    def __init__(self, db_path: Optional[str] = None):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids: set[str] = set()
        self.storage = None
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
        realized = round(sum(p.pnl_rupees for p in closed), 2)
        unrealized = round(sum(p.pnl_rupees for p in active), 2)
        total = round(realized + unrealized, 2)
        total_trades = len(closed)
        winning = sum(1 for p in closed if p.pnl_rupees > 0)
        losing = sum(1 for p in closed if p.pnl_rupees <= 0)
        win_rate = round((winning / total_trades) * 100, 1) if total_trades > 0 else 0.0

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
            losing_trades_count=losing
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

    def open_position_from_signal(
        self,
        signal: Signal,
        lots: Optional[int] = None,
        feed_mode: str = "demo"
    ) -> Optional[PaperPosition]:
        # Avoid duplicate trades on same signal ID
        if signal.id in self._processed_signal_ids:
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
            option_entry=rec.estimated_option_entry,
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
            current_option_price=rec.estimated_option_entry,
            pnl_points=0.0,
            pnl_rupees=0.0,
            status="OPEN",
            option_security_id=getattr(rec, "option_security_id", None),
            feed_mode=feed_mode
        )

        self._portfolio.active_positions.append(pos)
        self._recalculate_metrics()
        if self.storage:
            self.storage.upsert_position(pos)
            self.storage.add_processed_signal(signal.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return pos

    def on_signals_cycle(self, signals: list[Signal], feed_mode: str = "demo"):
        """Automatically open paper positions if auto-trade is enabled."""
        if not self._portfolio.auto_trade_enabled:
            return

        for sig in signals:
            if sig.id not in self._processed_signal_ids:
                # Open position for new signals
                self.open_position_from_signal(sig, feed_mode=feed_mode)

    def update_market_prices(
        self,
        price_map: dict[str, float],
        option_price_map: Optional[dict[str, float]] = None
    ):
        """Update active positions with current underlying prices and live option prices from Dhan."""
        delta = 0.55
        now_str = datetime.now().strftime("%H:%M:%S")
        still_active = []

        for pos in self._portfolio.active_positions:
            curr_spot = price_map.get(pos.symbol)
            if curr_spot is not None:
                pos.current_underlying = round(curr_spot, 2)

            is_opt_chart_setup = (
                pos.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
                or "Setup 5" in str(pos.setup_type)
            )

            # Check if live option quote is directly provided from Dhan (NSE_FNO)
            real_opt_price = None
            if option_price_map and pos.option_security_id:
                real_opt_price = option_price_map.get(str(pos.option_security_id)) or option_price_map.get(pos.option_security_id)

            if real_opt_price is not None and float(real_opt_price) > 0:
                pos.current_option_price = round(float(real_opt_price), 2)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif pos.option_security_id:
                # Live contract with security_id: keep last known real price, do not synthesize fake delta
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif is_opt_chart_setup:
                # Setup 5: Option chart scalp - maintain current option price if no new tick
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif curr_spot is not None:
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

            # --- SETUP 5: EXITS BASED EXCLUSIVELY ON OPTION CHARTS ---
            if is_opt_chart_setup:
                if pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    pos.status = "STOPPED_OUT"
                    pos.exit_time = now_str
                    pos.exit_reason = reason
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
                    self._portfolio.closed_trades.append(pos)
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                elif pos.current_option_price >= pos.option_target_2:
                    pos.status = "TARGET_2"
                    pos.exit_time = now_str
                    pos.exit_reason = "Target 2 (1:2.5) Hit"
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
                    self._portfolio.closed_trades.append(pos)
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                elif pos.current_option_price >= pos.option_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        book_pnl = round(pos.pnl_points * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.option_sl = pos.option_entry
                    if self.storage:
                        self.storage.upsert_position(pos)

                still_active.append(pos)
                continue

            # --- SETUPS 1-4: EXITS BASED ON UNDERLYING SPOT OR OPTION LEVELS ---
            if pos.option_type == "CE":
                # Check SL
                if (curr_spot is not None and curr_spot <= pos.underlying_sl) or pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    pos.status = "STOPPED_OUT"
                    pos.exit_time = now_str
                    pos.exit_reason = reason
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
                    self._portfolio.closed_trades.append(pos)
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot >= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
                    pos.status = "TARGET_2"
                    pos.exit_time = now_str
                    pos.exit_reason = "Target 2 (1:2.5) Hit"
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
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
                        book_pnl = round(pos.pnl_points * book_qty, 2)
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
                    pos.status = "STOPPED_OUT"
                    pos.exit_time = now_str
                    pos.exit_reason = reason
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
                    self._portfolio.closed_trades.append(pos)
                    if self.storage:
                        self.storage.upsert_position(pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot <= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
                    pos.status = "TARGET_2"
                    pos.exit_time = now_str
                    pos.exit_reason = "Target 2 (1:2.5) Hit"
                    runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                    pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
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
                        book_pnl = round(pos.pnl_points * book_qty, 2)
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

    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> Optional[PaperPosition]:
        for i, pos in enumerate(self._portfolio.active_positions):
            if pos.id == position_id:
                pos.status = "CLOSED"
                pos.exit_time = datetime.now().strftime("%H:%M:%S")
                pos.exit_reason = reason
                runner_pnl = round(pos.pnl_points * pos.quantity, 2)
                pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
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

from app.core.config import settings
paper_trader = PaperTradingEngine(db_path=settings.DB_PATH)
