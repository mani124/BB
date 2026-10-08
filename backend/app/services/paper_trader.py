from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel
from app.services.strategy_engine import Signal
from app.services.strike_selector import get_lot_size

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

class PaperPortfolio(BaseModel):
    active_positions: list[PaperPosition] = []
    closed_trades: list[PaperPosition] = []
    auto_trade_enabled: bool = True
    default_lots: int = 1
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    win_rate_pct: float = 0.0
    total_trades_count: int = 0
    winning_trades_count: int = 0
    losing_trades_count: int = 0

class PaperTradingEngine:
    """Manages paper trading execution, position monitoring, and analytics."""

    def __init__(self):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids: set[str] = set()

    def get_portfolio(self) -> PaperPortfolio:
        self._recalculate_metrics()
        return self._portfolio

    def set_auto_trade(self, enabled: bool):
        self._portfolio.auto_trade_enabled = enabled

    def set_default_lots(self, lots: int):
        self._portfolio.default_lots = max(1, lots)

    def reset(self):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids.clear()

    def open_position_from_signal(self, signal: Signal, lots: Optional[int] = None) -> Optional[PaperPosition]:
        # Avoid duplicate trades on same signal ID
        if signal.id in self._processed_signal_ids:
            return None

        self._processed_signal_ids.add(signal.id)
        lots_to_trade = lots if lots is not None else self._portfolio.default_lots
        lot_size = signal.strike_recommendation.lot_size
        qty = lot_size * lots_to_trade

        pos_id = f"POS_{signal.symbol}_{signal.option_type}_{int(datetime.now().timestamp())}"
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
            current_underlying=signal.entry_price,
            current_option_price=rec.estimated_option_entry,
            pnl_points=0.0,
            pnl_rupees=0.0,
            status="OPEN"
        )

        self._portfolio.active_positions.append(pos)
        self._recalculate_metrics()
        return pos

    def on_signals_cycle(self, signals: list[Signal]):
        """Automatically open paper positions if auto-trade is enabled."""
        if not self._portfolio.auto_trade_enabled:
            return

        for sig in signals:
            if sig.id not in self._processed_signal_ids:
                # Open position for new signals
                self.open_position_from_signal(sig)

    def update_market_prices(self, price_map: dict[str, float]):
        """Update active positions with current underlying prices and check SL/targets."""
        delta = 0.55
        now_str = datetime.now().strftime("%H:%M:%S")
        still_active = []

        for pos in self._portfolio.active_positions:
            curr_spot = price_map.get(pos.symbol)
            if curr_spot is None:
                still_active.append(pos)
                continue

            pos.current_underlying = round(curr_spot, 2)
            
            # Estimate option price based on underlying delta
            if pos.option_type == "CE":
                spot_move = curr_spot - pos.underlying_entry
                est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                pos.current_option_price = round(est_opt, 1)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 1)

                # Check SL
                if curr_spot <= pos.underlying_sl or pos.current_option_price <= pos.option_sl:
                    pos.status = "STOPPED_OUT"
                    pos.exit_time = now_str
                    pos.exit_reason = "Stop-Loss Hit"
                    pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
                    self._portfolio.closed_trades.append(pos)
                    continue

                # Check Target 2
                elif curr_spot >= pos.underlying_target_2 or pos.current_option_price >= pos.option_target_2:
                    pos.status = "TARGET_2"
                    pos.exit_time = now_str
                    pos.exit_reason = "Target 2 (1:2.5) Hit"
                    pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
                    self._portfolio.closed_trades.append(pos)
                    continue

                # Check Target 1
                elif curr_spot >= pos.underlying_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    # Move SL to breakeven
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            else:  # PE
                spot_move = pos.underlying_entry - curr_spot
                est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                pos.current_option_price = round(est_opt, 1)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 1)

                # Check SL
                if curr_spot >= pos.underlying_sl or pos.current_option_price <= pos.option_sl:
                    pos.status = "STOPPED_OUT"
                    pos.exit_time = now_str
                    pos.exit_reason = "Stop-Loss Hit"
                    pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
                    self._portfolio.closed_trades.append(pos)
                    continue

                # Check Target 2
                elif curr_spot <= pos.underlying_target_2 or pos.current_option_price >= pos.option_target_2:
                    pos.status = "TARGET_2"
                    pos.exit_time = now_str
                    pos.exit_reason = "Target 2 (1:2.5) Hit"
                    pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
                    self._portfolio.closed_trades.append(pos)
                    continue

                # Check Target 1
                elif curr_spot <= pos.underlying_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
            still_active.append(pos)

        self._portfolio.active_positions = still_active
        self._recalculate_metrics()

    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> Optional[PaperPosition]:
        for i, pos in enumerate(self._portfolio.active_positions):
            if pos.id == position_id:
                pos.status = "CLOSED"
                pos.exit_time = datetime.now().strftime("%H:%M:%S")
                pos.exit_reason = reason
                pos.pnl_rupees = round(pos.pnl_points * pos.quantity, 2)
                closed = self._portfolio.active_positions.pop(i)
                self._portfolio.closed_trades.append(closed)
                self._recalculate_metrics()
                return closed
        return None

    def _recalculate_metrics(self):
        realized = sum(p.pnl_rupees for p in self._portfolio.closed_trades)
        unrealized = sum(p.pnl_rupees for p in self._portfolio.active_positions)
        
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

paper_trader = PaperTradingEngine()
