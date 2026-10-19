"""Holds the process-wide watchlist service (built in app.main)."""
from typing import Optional

from app.services.watchlist import WatchlistService

_service: Optional[WatchlistService] = None


def set_service(service: Optional[WatchlistService]) -> None:
    global _service
    _service = service


def get_service() -> WatchlistService:
    if _service is None:
        raise RuntimeError("Watchlist service is not initialised")
    return _service
