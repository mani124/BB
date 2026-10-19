"""Holds the process-wide Commodities & Currency engine (built in app.main) and its poll loop."""
import asyncio
import logging
from typing import Optional

from app.services.cx_engine import CxEngine

logger = logging.getLogger(__name__)
_engine: Optional[CxEngine] = None


def set_engine(engine: Optional[CxEngine]) -> None:
    global _engine
    _engine = engine


def get_engine() -> CxEngine:
    if _engine is None:
        raise RuntimeError("Commodities & Currency engine is not initialised")
    return _engine


async def poll_loop(engine: CxEngine) -> None:
    """Run a cycle every `cx_poll_seconds` (re-read each time, so a change applies without a restart)."""
    while True:
        try:
            await engine.run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("cx poll cycle failed", exc_info=True)
        try:
            await asyncio.sleep(float(engine.runtime.get("cx_poll_seconds")))
        except asyncio.CancelledError:
            raise
