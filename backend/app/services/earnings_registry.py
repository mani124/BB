"""Holds the process-wide earnings engine (built in app.main once the scanner worker exists) and its poll loop."""
import asyncio
import logging
from typing import Optional

from app.services.earnings_engine import EarningsEngine

logger = logging.getLogger(__name__)
_engine: Optional[EarningsEngine] = None


def set_engine(engine: Optional[EarningsEngine]) -> None:
    global _engine
    _engine = engine


def get_engine() -> EarningsEngine:
    if _engine is None:
        raise RuntimeError("Earnings engine is not initialised")
    return _engine


async def poll_loop(engine: EarningsEngine) -> None:
    """Run a cycle every `earnings_poll_seconds` (re-read each time, so a change applies without a restart)."""
    while True:
        try:
            await engine.run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("earnings poll cycle failed", exc_info=True)
        try:
            await asyncio.sleep(float(engine.runtime.get("earnings_poll_seconds")))
        except asyncio.CancelledError:
            raise
