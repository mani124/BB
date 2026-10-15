from typing import Optional

from fastapi import APIRouter

from app.api.paper import _resolve_view
from app.services.cost_analysis import CostReport, build_cost_report
from app.services.paper_trader import paper_trader

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/costs")
async def get_costs(mode: Optional[str] = None) -> CostReport:
    """Gross P&L, slippage, charges and net per trade, per day and grouped by setup, symbol
    and premium bucket. Slippage is already inside gross (see services/cost_analysis.py)."""
    view = _resolve_view(mode)
    closed = paper_trader.get_portfolio(view).closed_trades
    return build_cost_report(closed)
