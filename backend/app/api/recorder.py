"""Read access to the recorded market bars (see services/market_recorder.py)."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services.market_recorder import recorder

router = APIRouter(prefix="/recorder", tags=["recorder"])


@router.get("/status")
async def recorder_status() -> dict:
    return recorder.status()


@router.get("/bars")
async def recorder_bars(kind: str = Query("spot", pattern="^(spot|option)$"), key: str = Query(..., min_length=1),
                        tf: int = Query(5, ge=1, le=60), day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                        limit: int = Query(5000, ge=1, le=20000)) -> list[dict]:
    return recorder.bars(kind, key, tf, day, limit)
