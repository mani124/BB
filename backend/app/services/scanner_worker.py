import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

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

SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "active_session.json"

class ScannerWorker:
    """Cyclic scanner worker cycling every ~8 seconds through the 4 indices and ~35 momentum stocks."""

    def __init__(self, universe_mgr: UniverseManager, dhan_client: Optional[DhanClient] = None):
        self.universe_mgr = universe_mgr
        self.dhan_client = dhan_client or DhanClient()
        self._state = ScannerState(universe_count=len(universe_mgr.get_universe()))
        self._listeners: list[asyncio.Queue] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session_credentials: Optional[tuple[str, str]] = None
        self._historical_disabled: bool = False
        self._load_saved_session()

    def _load_saved_session(self):
        try:
            if SESSION_FILE.exists():
                with open(SESSION_FILE, "r") as f:
                    data = json.load(f)
                    cid = data.get("client_id")
                    tok = data.get("access_token")
                    if cid and tok:
                        self._session_credentials = (cid, tok)
                        self._state.active_mode = "live"
                        logger.info("Restored active Dhan session into live scanner mode")
        except Exception as e:
            logger.warning(f"Could not load saved session: {e}")

    def set_session_credentials(self, client_id: Optional[str], access_token: Optional[str]):
        self._historical_disabled = False
        if client_id and access_token:
            self._session_credentials = (client_id, access_token)
            self._state.active_mode = "live"
            try:
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(SESSION_FILE, "w") as f:
                    json.dump({"client_id": client_id, "access_token": access_token}, f)
                os.chmod(SESSION_FILE, 0o600)
            except Exception as e:
                logger.warning(f"Could not persist active session: {e}")
        else:
            self._session_credentials = None
            self._state.active_mode = "demo"
            try:
                if SESSION_FILE.exists():
                    SESSION_FILE.unlink()
            except Exception as e:
                logger.warning(f"Could not clear session file: {e}")

    def get_state(self) -> ScannerState:
        return self._state

    def get_latest_state(self) -> ScannerState:
        """Alias for get_state returning the most recent scanner state snapshot."""
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

    def generate_synthetic_candles(self, inst: Instrument, n: int = 40, base_price: Optional[float] = None) -> pd.DataFrame:
        """
        Generate realistic simulated market candles for forward-testing
        when outside trading hours or in demo mode.
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
        base_p = float(base_price) if (base_price and base_price > 0) else base_map.get(inst.symbol, 1500.0)
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
            noise = float(rng.normal(0, base_p * 0.0015))
            open_p = curr_p
            close_p = open_p + noise

            # Inject a squeeze + breakout setup on NIFTY & RELIANCE for live demonstration
            if inst.symbol in ["NIFTY 50", "RELIANCE"] and i >= n - 2:
                close_p = open_p + abs(noise) * 2.5

            high_p = max(open_p, close_p) + abs(float(rng.normal(0, base_p * 0.0008)))
            low_p = min(open_p, close_p) - abs(float(rng.normal(0, base_p * 0.0008)))
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
        """Run a full cycle across all instruments in the universe."""
        self._state.is_scanning = True
        self._state.scan_progress = 0.0

        # Fallback to session credentials if not explicitly passed
        cid = client_id or (self._session_credentials[0] if self._session_credentials else None)
        tok = access_token or (self._session_credentials[1] if self._session_credentials else None)

        mode = "live" if (cid and tok) else "demo"
        self._state.active_mode = mode

        instruments = self.universe_mgr.get_universe()
        total_count = len(instruments)
        self._state.universe_count = total_count

        new_signals: list[Signal] = []
        new_radar: dict[str, IndexRadarItem] = {}
        price_map: dict[str, float] = {}

        # Batch-fetch real-time market quotes (LTP, OHLC, volume, net change) via marketfeed
        live_quotes: dict = {}
        if mode == "live" and cid and tok:
            try:
                req_securities: dict[str, list[int]] = {}
                for inst in instruments:
                    try:
                        sec_id_int = int(inst.security_id)
                        req_securities.setdefault(inst.exchange_segment, []).append(sec_id_int)
                    except ValueError:
                        pass
                fetch_fn = getattr(self.dhan_client, "fetch_marketfeed_quotes", None)
                if fetch_fn and asyncio.iscoroutinefunction(fetch_fn):
                    live_quotes = await fetch_fn(cid, tok, req_securities)
                    if live_quotes:
                        logger.info(f"Live marketfeed quotes fetched for {sum(len(v) for v in live_quotes.values())} securities")
            except Exception as e:
                logger.warning(f"Error fetching live marketfeed quotes: {e}")

        for idx, inst in enumerate(instruments):
            inst_quote = None
            if live_quotes:
                quotes_dict = live_quotes.get("data", live_quotes) if isinstance(live_quotes.get("data"), dict) else live_quotes
                seg_quotes = quotes_dict.get(inst.exchange_segment, {})
                inst_quote = seg_quotes.get(str(inst.security_id)) or seg_quotes.get(int(inst.security_id))

            df = pd.DataFrame()
            if mode == "live" and cid and tok and not inst_quote and not self._historical_disabled:
                try:
                    df = await self.dhan_client.fetch_intraday_candles(
                        client_id=cid,
                        access_token=tok,
                        security_id=inst.security_id,
                        exchange_segment=inst.exchange_segment,
                        instrument_type=inst.instrument_type,
                        interval=5 if inst.default_timeframe == "5m" else 15
                    )
                    if df.empty:
                        self._historical_disabled = True
                except Exception as e:
                    self._historical_disabled = True
                    logger.warning(f"Error fetching candles for {inst.symbol}: {e}")

            # Calibrate candles with real-time live market quote if available
            live_ltp = float(inst_quote.get("last_price", 0.0)) if inst_quote else None
            if df.empty or len(df) < 15:
                df = self.generate_synthetic_candles(inst, base_price=live_ltp)
                if inst_quote and live_ltp and live_ltp > 0:
                    ohlc = inst_quote.get("ohlc", {})
                    # Pin latest bar to real market tick
                    df.iloc[-1, df.columns.get_loc("close")] = live_ltp
                    df.iloc[-1, df.columns.get_loc("high")] = max(float(ohlc.get("high", live_ltp)), live_ltp)
                    df.iloc[-1, df.columns.get_loc("low")] = min(float(ohlc.get("low", live_ltp)), live_ltp)
                    df.iloc[-1, df.columns.get_loc("volume")] = int(inst_quote.get("volume", 10000))
            elif inst_quote and live_ltp and live_ltp > 0:
                df.iloc[-1, df.columns.get_loc("close")] = live_ltp

            # Compute Indicators
            ind_df = calculate_indicators(df)
            if not ind_df.empty:
                current_price = live_ltp if (live_ltp and live_ltp > 0) else float(ind_df.iloc[-1]["close"])
                price_map[inst.symbol] = current_price

            # If instrument is an index, update radar status
            if inst.instrument_type == "INDEX" and not ind_df.empty:
                last_row = ind_df.iloc[-1]
                if inst_quote and live_ltp and live_ltp > 0:
                    ohlc = inst_quote.get("ohlc", {})
                    prev_close = float(ohlc.get("close", 0.0))
                    net_change = float(inst_quote.get("net_change", 0.0))
                    if prev_close > 0:
                        change_pct = round((net_change / prev_close) * 100, 2)
                    elif float(ohlc.get("open", 0.0)) > 0:
                        change_pct = round(((live_ltp - float(ohlc["open"])) / float(ohlc["open"])) * 100, 2)
                    else:
                        change_pct = 0.0
                    radar_close = live_ltp
                else:
                    today_mask = ind_df["timestamp"].dt.date == ind_df["timestamp"].dt.date.max()
                    today_df = ind_df[today_mask]
                    first_row = today_df.iloc[0] if not today_df.empty else ind_df.iloc[0]
                    first_open = float(first_row["open"]) if float(first_row["open"]) > 0 else float(last_row["close"])
                    radar_close = float(last_row["close"])
                    change_pct = round(((radar_close - first_open) / first_open) * 100, 2) if first_open > 0 else 0.0

                bw_val = float(last_row["bandwidth"])
                bw_min = float(last_row.get("bandwidth_20_min", bw_val))
                if pd.isna(bw_min) or bw_min <= 0:
                    bw_min = bw_val

                is_sq = (bw_val <= bw_min * 1.25) or (bw_val <= 5.0)
                vwap_b = "ABOVE_VWAP" if radar_close >= float(last_row["vwap"]) else "BELOW_VWAP"

                percent_b_val = float(last_row["percent_b"])
                adx_val = float(last_row["adx"])

                trend = "RANGE"
                if percent_b_val > 0.9 and adx_val > 25.0:
                    trend = "BULLISH_WALK"
                elif percent_b_val < 0.1 and adx_val > 25.0:
                    trend = "BEARISH_WALK"
                elif is_sq:
                    trend = "SQUEEZE"

                new_radar[inst.symbol] = IndexRadarItem(
                    symbol=inst.symbol,
                    close=round(radar_close, 2),
                    change_pct=round(change_pct, 2),
                    percent_b=round(percent_b_val, 2),
                    bandwidth=round(bw_val, 2),
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
                await self.run_single_scan_cycle()
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
