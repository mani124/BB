"""Holds the process-wide swing engine (built in app.main) and its poll loop."""
import asyncio
import logging
from typing import Optional

from app.services.swing_engine import SwingEngine

logger = logging.getLogger(__name__)
_engine: Optional[SwingEngine] = None


def set_engine(engine: Optional[SwingEngine]) -> None:
    global _engine
    _engine = engine


def get_engine() -> SwingEngine:
    if _engine is None:
        raise RuntimeError("Swing engine is not initialised")
    return _engine


async def poll_loop(engine: SwingEngine) -> None:
    """Check for a finished trading day every `swing_poll_seconds` (re-read each time, so a change applies without a restart)."""
    while True:
        try:
            await engine.run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("swing poll cycle failed", exc_info=True)
        try:
            await asyncio.sleep(float(engine.runtime.get("swing_poll_seconds")))
        except asyncio.CancelledError:
            raise
