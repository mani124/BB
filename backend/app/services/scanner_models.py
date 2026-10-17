import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from app.services import market_hours
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from app.core.config import settings

@dataclass
class OptionQuote:
    ltp: float
    bid: Optional[float]
    timestamp: float
    source: str  # "ws" or "chain"
from app.services.universe_manager import UniverseManager, Instrument
from app.services.dhan_client import DhanClient
from app.services.dhan_websocket import DhanWebSocketManager
from app.services.dhan_packet_codec import segment_to_int
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, Signal, SetupType
from app.services.strike_selector import resolve_live_strike_from_chain, get_lot_size
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.paper_trader import paper_trader, PaperPortfolio, PaperPosition
from app.services.momentum_ranker import MomentumRanker, MomentumRankings

logger = logging.getLogger(__name__)

class IndexRadarItem(BaseModel):
    symbol: str
    close: float
    change_pct: float
    percent_b: float
    bandwidth: float
    is_squeeze: bool
    vwap_bias: str  # "ABOVE_VWAP" or "BELOW_VWAP"
    rsi: float
    trend_state: str  # "BULLISH_WALK", "BEARISH_WALK", "SQUEEZE", "RANGE"

class ScannerState(BaseModel):
    signals: list[Signal] = []
    radar: dict[str, IndexRadarItem] = {}
    top_bullish: list[str] = Field(default_factory=list)
    top_bearish: list[str] = Field(default_factory=list)
    market_bias: str = "NEUTRAL"
    paper_portfolio: PaperPortfolio = Field(default_factory=PaperPortfolio)
    last_scan_time: str = ""
    scan_cycle_count: int = 0
    last_scan_seconds: float = 0.0  # wall time of the latest full scan cycle
    is_scanning: bool = False
    scan_progress: float = 0.0
    universe_count: int = 0
    active_mode: str = "demo"  # "live", "stale", "error", "closed" (outside exchange session), or "demo"
    feed_status: str = "DEMO"  # "WS_LIVE", "LIVE", "STALE", "ERROR", "CLOSED", "DEMO"
    ws_connected: bool = False
    last_quote_time: str = ""

SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "active_session.json"

