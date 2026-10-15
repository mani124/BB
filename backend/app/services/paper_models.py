import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal, is_setup5
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.core.config import settings

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
    pending_spot_tp1: bool = False
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
    # Full ISO datetimes (IST, with date). entry_time/exit_time stay HH:MM:SS for display.
    entry_datetime: Optional[str] = None
    exit_datetime: Optional[str] = None
    # Non-destructive quarantine: rows with a reason stay visible but are excluded from totals.
    quarantine_reason: Optional[str] = None
    # True when the entry price was modelled (no real ask/last from the exchange feed).
    entry_estimated: bool = False
    # Liquidity at the moment of entry (None when the feed did not supply it). Logged so a
    # spread or volume filter can be tested on real trades.
    entry_bid: Optional[float] = None
    entry_spread_pct: Optional[float] = None
    option_volume: Optional[float] = None
    option_oi: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_qty: Optional[float] = None

class DailyPnl(BaseModel):
    date: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0
    quarantined_excluded: int = 0

STALE_CARRYOVER = "STALE_CARRYOVER"
EOD_SQUARE_OFF = "EOD_SQUARE_OFF"

def _now_stamp() -> tuple[str, str]:
    """(HH:MM:SS display, ISO datetime with date) for the current IST instant."""
    n = market_hours.now_ist().replace(microsecond=0)
    return n.strftime("%H:%M:%S"), n.isoformat()

def _signed_slip(level: float, fill: float) -> float:
    """Slippage in points for a sell: positive = filled worse than the intended level,
    negative = price improvement (e.g. a gap through a target)."""
    return round(float(level) - float(fill), 2)

def _view_mode(mode: Optional[str]) -> Optional[str]:
    """Portfolio views are either demo or live. Every non-demo scan state (live, stale,
    error, closed) shows the live book, so positions never vanish when the market closes."""
    if not mode:
        return None
    return "demo" if mode == "demo" else "live"

def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=market_hours.IST)

class PaperPortfolio(BaseModel):
    active_positions: list[PaperPosition] = []
    closed_trades: list[PaperPosition] = []
    auto_trade_enabled: bool = True
    setup_modes: dict[str, str] = {}
    default_lots: int = 2
    max_risk_per_trade: float = 8000.0
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
    # Number of closed trades in this view. The SSE state stream sends closed_trades empty
    # (see get_portfolio_summary) and the UI fetches the list when this count changes.
    closed_trades_count: int = 0

