import asyncio
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from typing import Optional

from app.core.config import settings
from app.services.universe_manager import UniverseManager, Instrument
from app.services.dhan_client import DhanClient
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, Signal
from app.services.paper_trader import paper_trader, PaperPortfolio

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
    paper_portfolio: PaperPortfolio = Field(default_factory=PaperPortfolio)
    last_scan_time: str = ""
    scan_cycle_count: int = 0
    is_scanning: bool = False
    scan_progress: float = 0.0
    universe_count: int = 0
    active_mode: str = "demo"  # "live" or "demo"

class ScannerWorker:
    """Cyclic scanner worker cycling every ~8 seconds through the 4 indices and ~30 momentum stocks."""

    def __init__(self, universe_mgr: UniverseManager, dhan_client: Optional[DhanClient] = None):
        self.universe_mgr = universe_mgr
        self.dhan_client = dhan_client or DhanClient()
        self._state = ScannerState(universe_count=len(universe_mgr.get_all_instruments()))
        self._listeners: list[asyncio.Queue] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session_credentials: Optional[tuple[str, str]] = None

    def set_session_credentials(self, client_id: Optional[str], access_token: Optional[str]):
        if client_id and access_token:
            self._session_credentials = (client_id, access_token)
        else:
            self._session_credentials = None

    def get_state(self) -> ScannerState:
        return self._state

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=20)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._listeners:
            self._listeners.remove(q)

    async def broadcast(self, data: dict):
        dead_queues = []
        for q in self._listeners:
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(data)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            self.unsubscribe(dq)

    def generate_synthetic_candles(self, inst: Instrument, n: int = 40) -> pd.DataFrame:
        """
        Generate realistic simulated market candles for forward-testing
        when outside trading hours or before entering live Dhan credentials.
        """
        base_map = {
            "NIFTY 50": 25050.0,
            "NIFTY BANK": 51850.0,
            "FINNIFTY": 24120.0,
            "SENSEX": 82150.0,
            "RELIANCE": 2980.0,
            "HDFCBANK": 1680.0,
            "ICICIBANK": 1280.0,
            "TATAMOTORS": 940.0,
            "INFY": 1920.0,
        }
        base_p = base_map.get(inst.symbol, 1500.0)
        start_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
        minutes_step = 5 if inst.default_timeframe == "5m" else 15
        
        records = []
        curr_p = base_p
        
        # Seed by symbol name for reproducible realism
        seed_val = sum(ord(c) for c in inst.symbol)
        rng = np.random.default_rng(seed_val)
        
        for i in range(n):
            ts = start_time + timedelta(minutes=minutes_step * i)
            # Create natural momentum waves
            noise = rng.normal(0, base_p * 0.0015)
            open_p = curr_p
            close_p = open_p + noise
            
            # Inject a squeeze + breakout setup on NIFTY & RELIANCE for live demonstration
            if inst.symbol in ["NIFTY 50", "RELIANCE"] and i >= n - 2:
                close_p = open_p + abs(noise) * 2.5
            
            high_p = max(open_p, close_p) + abs(rng.normal(0, base_p * 0.0008))
            low_p = min(open_p, close_p) - abs(rng.normal(0, base_p * 0.0008))
            vol = int(rng.uniform(5000, 25000))
            
            records.append({
                "timestamp": ts,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": vol
            })
            curr_p = close_p
            
        return pd.DataFrame(records)

    async def run_single_scan_cycle(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> ScannerState:
        """Run a full cycle across all instruments."""
        self._state.is_scanning = True
        self._state.scan_progress = 0.0
        
        instruments = self.universe_mgr.get_all_instruments()
        total_count = len(instruments)
        new_signals: list[Signal] = []
        new_radar: dict[str, IndexRadarItem] = {}

        mode = "live" if (client_id and access_token) else "demo"
        self._state.active_mode = mode

        price_map: dict[str, float] = {}

        for idx, inst in enumerate(instruments):
            df = pd.DataFrame()
            if mode == "live" and client_id and access_token:
                try:
                    df = await self.dhan_client.fetch_intraday_candles(
                        client_id=client_id,
                        access_token=access_token,
                        security_id=inst.security_id,
                        exchange_segment=inst.exchange_segment,
                        instrument_type=inst.instrument_type,
                        interval=5 if inst.default_timeframe == "5m" else 15
                    )
                except Exception as e:
                    logger.warning(f"Error fetching candles for {inst.symbol}: {e}")

            # Fallback to demo generator if df is empty (outside market hours or demo mode)
            if df.empty or len(df) < 15:
                df = self.generate_synthetic_candles(inst)

            # Compute Indicators
            ind_df = calculate_indicators(df)
            if not ind_df.empty:
                price_map[inst.symbol] = float(ind_df.iloc[-1]["close"])
            
            # If instrument is an index, update radar status
            if inst.instrument_type == "INDEX" and not ind_df.empty:
                last_row = ind_df.iloc[-1]
                # Scope to today's trading session to prevent multi-day Dhan history from distorting daily % change
                today_mask = ind_df["timestamp"].dt.date == ind_df["timestamp"].dt.date.max()
                today_df = ind_df[today_mask]
                first_row = today_df.iloc[0] if not today_df.empty else ind_df.iloc[0]
                chg = ((last_row["close"] - first_row["open"]) / first_row["open"] * 100.0) if first_row["open"] else 0.0
                
                bw_min = last_row.get("bandwidth_20_min", last_row["bandwidth"])
                if pd.isna(bw_min) or bw_min <= 0:
                    bw_min = last_row["bandwidth"]
                is_sq = last_row["bandwidth"] <= bw_min * 1.2
                vwap_b = "ABOVE_VWAP" if last_row["close"] >= last_row["vwap"] else "BELOW_VWAP"
                
                trend = "RANGE"
                if last_row["percent_b"] > 0.9 and last_row["adx"] > 25:
                    trend = "BULLISH_WALK"
                elif last_row["percent_b"] < 0.1 and last_row["adx"] > 25:
                    trend = "BEARISH_WALK"
                elif is_sq:
                    trend = "SQUEEZE"

                new_radar[inst.symbol] = IndexRadarItem(
                    symbol=inst.symbol,
                    close=round(float(last_row["close"]), 2),
                    change_pct=round(float(chg), 2),
                    percent_b=round(float(last_row["percent_b"]), 2),
                    bandwidth=round(float(last_row["bandwidth"]), 2),
                    is_squeeze=bool(is_sq),
                    vwap_bias=vwap_b,
                    rsi=round(float(last_row["rsi"]), 2),
                    trend_state=trend
                )

            # Evaluate Setups
            detected = evaluate_signals(inst.symbol, ind_df, timeframe=inst.default_timeframe)
            new_signals.extend(detected)

            # Update progress
            self._state.scan_progress = round(((idx + 1) / total_count) * 100.0, 1)

        # Update paper trading engine with latest market prices and signals
        paper_trader.update_market_prices(price_map)
        paper_trader.on_signals_cycle(new_signals)

        self._state.signals = new_signals
        self._state.radar = new_radar
        self._state.paper_portfolio = paper_trader.get_portfolio()
        self._state.last_scan_time = datetime.now().strftime("%H:%M:%S")
        self._state.scan_cycle_count += 1
        self._state.is_scanning = False
        self._state.scan_progress = 100.0

        # Broadcast update to connected SSE subscribers
        await self.broadcast(self._state.model_dump())
        return self._state

    async def _loop(self):
        while self._running:
            try:
                cid, tok = self._session_credentials if self._session_credentials else (None, None)
                await self.run_single_scan_cycle(client_id=cid, access_token=tok)
            except Exception as e:
                logger.error(f"Error in scanner worker loop: {e}")
            await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("ScannerWorker background loop started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.dhan_client.close()
        logger.info("ScannerWorker background loop stopped")
