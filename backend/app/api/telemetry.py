"""Telemetry read APIs: decision trail, error events, excursions and the deep performance report."""
from typing import Optional

from fastapi import APIRouter, Query

from app.api.paper import _resolve_view
from app.services.paper_trader import paper_trader
from app.services.performance_report import build_report

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/insights")
async def insights(hours: float = Query(24, gt=0, le=24 * 365)) -> dict:
    return paper_trader.telemetry.insights(hours)


@router.get("/decisions")
async def decisions(hours: float = Query(24, gt=0, le=24 * 365), strategy: Optional[str] = None,
                    decision: Optional[str] = None, symbol: Optional[str] = None, book: Optional[str] = None,
                    limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    return paper_trader.telemetry.decisions(hours=hours, strategy=strategy, decision=decision, symbol=symbol,
                                            book=book, limit=limit)


@router.get("/errors")
async def errors(hours: float = Query(24, gt=0, le=24 * 365), code: Optional[str] = None,
                 limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    return paper_trader.telemetry.errors(hours=hours, code=code, limit=limit)


@router.get("/excursions")
async def excursions(hours: float = Query(24 * 30, gt=0, le=24 * 365), strategy: Optional[str] = None,
                     limit: int = Query(500, ge=1, le=5000)) -> list[dict]:
    return paper_trader.telemetry.excursions(hours=hours, strategy=strategy, limit=limit)


@router.get("/performance")
async def performance(mode: Optional[str] = None) -> dict:
    """Expectancy, profit factor, drawdown, MFE capture and more, per setup / symbol / hour / exit reason."""
    view = _resolve_view(mode)
    return build_report(paper_trader.get_portfolio(view).closed_trades, paper_trader.telemetry.excursions(hours=24 * 365),
                        book=view)


@router.post("/purge")
async def purge() -> dict:
    """Delete telemetry older than the retention setting."""
    return paper_trader.telemetry.purge()
