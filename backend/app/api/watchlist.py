"""After-close watchlist for Setup 16: the current list and a manual rebuild."""
from fastapi import APIRouter

from app.services.watchlist_registry import get_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
async def current() -> dict:
    return get_service().current()


@router.post("/run")
async def run_now() -> dict:
    """Run the after-close cycle now. It still only builds once the build time has passed on a trading day."""
    return await get_service().run_cycle()
