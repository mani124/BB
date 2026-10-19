"""Read-only, source-aware dashboard endpoints."""
import asyncio

from fastapi import APIRouter, Query

from app.services.dashboard_read import list_dashboard_trades, build_dashboard_watch
from app.services.market_hours import now_ist

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/watch")
async def watch() -> dict:
    from app.main import worker
    from app.api.setup16 import build_overview
    from app.services.cx_registry import get_engine as get_cx_engine
    from app.services.earnings_registry import get_engine as get_earnings_engine

    try:
        scanner = worker.get_state().model_dump()
    except Exception as exc:
        scanner = {"_error": str(exc), "signals": []}
    try:
        setup16 = build_overview(worker)
    except Exception as exc:
        setup16 = {"_error": str(exc), "contracts": []}
    try:
        cx_engine = get_cx_engine()
        cx = {"summary": cx_engine.summary(), "candidates": await asyncio.wait_for(cx_engine.candidates(), timeout=10)}
    except Exception as exc:
        cx = {"_error": str(exc)}
    try:
        earnings_engine = get_earnings_engine()
        earnings = {"summary": earnings_engine.summary(), "candidates": await asyncio.wait_for(earnings_engine.preview(), timeout=10)}
    except Exception as exc:
        earnings = {"_error": str(exc)}
    return build_dashboard_watch(scanner, setup16, cx, earnings, observed_at=now_ist().isoformat())


@router.get("/trades")
async def trades(
    status: str | None = None,
    book: str | None = None,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> list[dict]:
    return list_dashboard_trades(status=status, book=book, day=day)
