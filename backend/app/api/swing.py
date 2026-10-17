"""Swing equity paper book (Setup 15): summary, positions, signal preview and a manual run (paper only)."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.swing_registry import get_engine

router = APIRouter(prefix="/swing", tags=["swing"])


@router.get("/summary")
async def summary() -> dict:
    return get_engine().summary()


@router.get("/positions")
async def positions(status: Optional[str] = Query(None, pattern="^(PENDING|OPEN|CLOSED|CANCELLED)$")) -> list[dict]:
    return get_engine().positions(status)


@router.get("/candidates")
async def candidates() -> list[dict]:
    """Setup 15 signals on the latest finished daily bar and whether the book would take them (needs a Dhan session). Nothing is queued."""
    return await get_engine().preview()


@router.post("/run")
async def run_now() -> dict:
    """Run the daily cycle now. It still only acts once the scan time has passed on a trading day."""
    return await get_engine().run_cycle()
