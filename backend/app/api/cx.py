"""Commodities & Currency paper book (Setups 17-19): summary, positions, signal preview and a manual cycle (paper only)."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.cx_registry import get_engine

router = APIRouter(prefix="/cx", tags=["commodities-currency"])


@router.get("/summary")
async def summary() -> dict:
    return get_engine().summary()


@router.get("/positions")
async def positions(status: Optional[str] = Query(None, pattern="^(OPEN|CLOSED)$")) -> list[dict]:
    return get_engine().positions(status)


@router.get("/candidates")
async def candidates() -> list[dict]:
    """Signals on the last completed 5m bar of each underlying and whether the book would take them (needs a Dhan session). Nothing is opened."""
    return await get_engine().candidates()


@router.post("/run")
async def run_now() -> dict:
    """Run one cycle now (manage positions, look for entries)."""
    return await get_engine().run_cycle()
