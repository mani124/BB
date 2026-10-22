"""Read-only analytics for the dashboard's Performance, Execution and Risk workspaces."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.paper import _resolve_view
from app.services import analytics
from app.services.paper_trader import paper_trader

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _selected(from_: Optional[str], to: Optional[str], book: str, setup: Optional[str], side: Optional[str]):
    try:
        rng = analytics.parse_range(from_, to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date range: {e}")
    view = None if book == "all" else _resolve_view(None)
    return analytics.filter_trades(list(paper_trader._portfolio.closed_trades), rng=rng, book=view, setup=setup, side=side)


@router.get("/equity")
async def equity(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                 book: str = Query("paper", pattern="^(paper|all)$"), setup: Optional[str] = None,
                 side: Optional[str] = Query(None, pattern="^(CE|PE)$")) -> dict:
    trades, excluded = _selected(from_, to, book, setup, side)
    return analytics.equity_report(trades, excluded)


@router.get("/attribution")
async def attribution(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                      book: str = Query("paper", pattern="^(paper|all)$"), setup: Optional[str] = None,
                      side: Optional[str] = Query(None, pattern="^(CE|PE)$"),
                      group: str = Query("setup", pattern="^(setup|symbol|side|hour|weekday|exit_reason)$")) -> dict:
    trades, excluded = _selected(from_, to, book, setup, side)
    return analytics.attribution_report(trades, paper_trader.telemetry.excursions(hours=24 * 365, limit=5000), group, excluded)


@router.get("/distribution")
async def distribution(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                       book: str = Query("paper", pattern="^(paper|all)$"), setup: Optional[str] = None,
                       side: Optional[str] = Query(None, pattern="^(CE|PE)$"), bins: int = Query(20, ge=5, le=60)) -> dict:
    trades, excluded = _selected(from_, to, book, setup, side)
    return analytics.distribution_report(trades, paper_trader.telemetry.excursions(hours=24 * 365, limit=5000), bins, excluded)


@router.get("/execution")
async def execution(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                    book: str = Query("paper", pattern="^(paper|all)$"), setup: Optional[str] = None,
                    side: Optional[str] = Query(None, pattern="^(CE|PE)$")) -> dict:
    trades, excluded = _selected(from_, to, book, setup, side)
    return analytics.execution_report(trades, excluded)


@router.get("/risk")
async def risk(book: str = Query("paper", pattern="^(paper|all)$")) -> dict:
    view = None if book == "all" else _resolve_view(None)
    positions = [p for p in paper_trader._portfolio.active_positions if view is None or getattr(p, "feed_mode", "demo") == view]
    return analytics.risk_snapshot(positions, paper_trader.runtime)
