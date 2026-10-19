"""Read-only, source-aware dashboard endpoints."""
from fastapi import APIRouter, Query

from app.services.dashboard_read import list_dashboard_trades

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/trades")
async def trades(
    status: str | None = None,
    book: str | None = None,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> list[dict]:
    return list_dashboard_trades(status=status, book=book, day=day)
