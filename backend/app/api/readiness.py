"""Readiness API: the same checks the morning alert uses, for the dashboard."""
from fastapi import APIRouter

from app.services import readiness

router = APIRouter(prefix="/readiness", tags=["readiness"])


@router.get("")
async def get_readiness() -> dict:
    from app.main import gather_readiness
    return readiness.summarize(gather_readiness())
