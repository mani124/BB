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
    is_scanning: bool = False
    scan_progress: float = 0.0
    universe_count: int = 0
    active_mode: str = "demo"  # "live", "stale", "error", "closed" (outside exchange session), or "demo"
    feed_status: str = "DEMO"  # "WS_LIVE", "LIVE", "STALE", "ERROR", "CLOSED", "DEMO"
    ws_connected: bool = False
    last_quote_time: str = ""

SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "active_session.json"

class ScannerWorker:
    """Cyclic scanner worker cycling every ~8 seconds through the 4 indices and ~35 momentum stocks."""

    def __init__(
        self,
        universe_mgr: UniverseManager,
        dhan_client: Optional[DhanClient] = None,
        ws_manager: Optional[DhanWebSocketManager] = None,
    ):
        self.universe_mgr = universe_mgr
        self.dhan_client = dhan_client or DhanClient()
        self.ws_manager = ws_manager or DhanWebSocketManager(
            on_tick_callback=self._handle_incoming_ws_tick
        )
        if self.ws_manager.on_tick_callback is None:
            self.ws_manager.on_tick_callback = self._handle_incoming_ws_tick

        self.momentum_ranker = MomentumRanker(top_n=10)
        self._state = ScannerState(universe_count=len(universe_mgr.get_universe()))
        self._listeners: list[asyncio.Queue] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session_credentials: Optional[tuple[str, str]] = None
        self._historical_disabled: bool = False
        self._session_generation: int = 0
        self._expiry_cache: dict[str, str] = {}
        self._option_chain_cache: dict[str, tuple[float, dict]] = {}
        self._option_chart_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._candle_history: dict[str, list[dict]] = {}
        self._current_forming_candle: dict[str, dict] = {}
        self._option_candle_history: dict[str, list[dict]] = {}
        self._option_forming_candle: dict[str, dict] = {}
        self._failed_candle_sec_ids: dict[str, float] = {}
        self._historical_seed_attempts: dict[str, float] = {}
        self._historical_seed_fail_count: dict[str, int] = {}
        self._last_session_date = market_hours.now_ist().date()
        self._option_last_cum_volume: dict[str, int] = {}
        self._last_successful_quote_time: Optional[float] = None
        self._scan_lock = asyncio.Lock()
        self._ws_connect_task: Optional[asyncio.Task] = None
        self._bar_completed_symbols: set[str] = set()
        self._instrument_last_quote_time: dict[str, float] = {}
        self._option_last_quote_time: dict[str, float] = {}
        self._latest_option_quotes: dict[str, OptionQuote] = {}
        self._last_cumulative_volume: dict[str, int] = {}
        self._sec_id_to_instrument: dict[str, Instrument] = {}
        self._seg_sec_id_to_instrument: dict[tuple[int, str], Instrument] = {}
        for inst in universe_mgr.get_universe():
            self._sec_id_to_instrument[str(inst.security_id)] = inst
            seg_i = segment_to_int(inst.exchange_segment)
            self._seg_sec_id_to_instrument[(seg_i, str(inst.security_id))] = inst

        # Wire dynamic paper trading position subscription callback
        paper_trader.on_position_opened = self._on_paper_position_opened
        self._load_saved_session()

    def record_option_quote(
        self,
        sec_id: str,
        ltp: float,
        bid: Optional[float] = None,
        source: str = "ws",
        timestamp: Optional[float] = None
    ) -> None:
        """Store an atomic OptionQuote record with observed price, bid, timestamp, and source."""
        sec_id_str = str(sec_id)
        ts = timestamp if timestamp is not None else time.monotonic()
        bid_f = None
        if bid is not None:
            try:
                b = float(bid)
                if b > 0:
                    bid_f = b
            except (ValueError, TypeError):
                pass

        # F4: Prevent older quote (e.g. from cached chain) from overwriting newer quote
        existing = self._latest_option_quotes.get(sec_id_str)
        if existing and existing.timestamp > ts:
            return

        self._latest_option_quotes[sec_id_str] = OptionQuote(
            ltp=float(ltp),
            bid=bid_f,
            timestamp=ts,
            source=source
        )
        self._option_last_quote_time[sec_id_str] = ts

    def get_option_quote(self, sec_id: str, max_age_s: float = 15.0) -> Optional[OptionQuote]:
        """Retrieve the latest OptionQuote if within max_age_s freshness window."""
        sec_id_str = str(sec_id)
        quote = self._latest_option_quotes.get(sec_id_str)
        if quote:
            age = (time.time() - quote.timestamp) if quote.timestamp > 1_000_000_000 else (time.monotonic() - quote.timestamp)
            if age <= max_age_s:
                return quote
            return None

        # Fallback for forming candle if last quote time is fresh
        quote_time = self._option_last_quote_time.get(sec_id_str, 0.0)
        candle = self._option_forming_candle.get(sec_id_str)
        if candle and candle.get("close", 0) > 0:
            age = (time.time() - quote_time) if quote_time > 1_000_000_000 else (time.monotonic() - quote_time)
            if age <= max_age_s:
                return OptionQuote(
                    ltp=float(candle["close"]),
                    bid=None,
                    timestamp=quote_time,
                    source="candle"
                )
        return None

    def _on_paper_position_opened(self, pos: PaperPosition) -> None:
        """Whenever a live paper trading position is opened, dynamically subscribe its option contract."""
        if pos.feed_mode == "live" and pos.option_security_id:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.subscribe_option_instrument(pos.option_security_id))
            except RuntimeError:
                pass

    async def subscribe_option_instrument(self, option_security_id: str | int) -> None:
        """Dynamically subscribe a single option instrument to live WebSocket feed."""
        try:
            sec_id_int = int(option_security_id)
            if self.ws_manager:
                await self.ws_manager.subscribe([(2, sec_id_int)])
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid option security ID %s: %s", option_security_id, exc)

    async def _subscribe_universe_instruments(self) -> None:
        """Subscribe all universe instruments (indices + F&O stocks) to WebSocket feed."""
        if not self.ws_manager:
            return
        instruments_to_sub: list[tuple[int, int]] = []
        for inst in self.universe_mgr.get_universe():
            try:
                seg_int = (
                    0
                    if (inst.instrument_type == "INDEX" or "IDX" in inst.exchange_segment)
                    else 1
                )
                sec_id_int = int(inst.security_id)
                instruments_to_sub.append((seg_int, sec_id_int))
            except (ValueError, TypeError):
                continue
        if instruments_to_sub:
            await self.ws_manager.subscribe(instruments_to_sub)

    async def _subscribe_active_positions(self) -> None:
        """Subscribe all active live paper trading option contracts to WebSocket feed."""
        if not self.ws_manager:
            return
        active_pos = paper_trader.get_portfolio(mode="live").active_positions
        opt_instruments: list[tuple[int, int]] = []
        for p in active_pos:
            if p.option_security_id:
                try:
                    opt_instruments.append((2, int(p.option_security_id)))
                except (ValueError, TypeError):
                    pass
        if opt_instruments:
            await self.ws_manager.subscribe(opt_instruments)

    async def _connect_websocket(
        self, client_id: str, access_token: str, generation: Optional[int] = None
    ) -> None:
        """Establish persistent binary streaming connection and subscribe universe."""
        if not self.ws_manager:
            return
        if os.environ.get("PYTEST_CURRENT_TEST"):
            from unittest.mock import AsyncMock, MagicMock

            if not isinstance(self.ws_manager.connect, (AsyncMock, MagicMock)):
                logger.debug("Skipping unmocked live WebSocket connect during pytest")
                return

        try:
            await self.ws_manager.connect(client_id, access_token)
            # Finding 5: Abort if disconnected or session generation changed during connect
            if (generation is not None and self._session_generation != generation) or not self._session_credentials:
                logger.info("WebSocket connect aborted: session credentials cleared or generation changed")
                return

            await self._subscribe_universe_instruments()
            await self._subscribe_active_positions()

            if (generation is not None and self._session_generation != generation) or not self._session_credentials:
                return

            self._state.ws_connected = True
            self._state.feed_status = "WS_LIVE"
            logger.info("Dhan WebSocket connected and universe instruments subscribed")
        except Exception as exc:
            logger.warning(
                "Could not connect Dhan WebSocket: %s; falling back seamlessly to HTTP polling",
                type(exc).__name__,
            )


    async def _handle_incoming_ws_tick(self, tick: dict) -> None:
        """
        Sub-second tick handler from Dhan WebSocket feed.
        - Immediately updates active paper trading positions with live option ticks,
          triggering instantaneous trailing stop-loss and profit target exits.
        - Updates in-memory prices and radar for underlying instruments.
        - Broadcasts real-time tick delta to connected SSE stream subscribers.
        """
        if not isinstance(tick, dict):
            return

        sec_id = tick.get("security_id")
        ltp = tick.get("ltp")
        if sec_id is None or ltp is None:
            return

        try:
            ltp = float(ltp)
        except (ValueError, TypeError):
            return
        if ltp <= 0:
            return

        if not self._state.ws_connected:
            self._state.ws_connected = True
            self._state.feed_status = "WS_LIVE"

        sec_id_str = str(sec_id)
        seg = tick.get("exchange_segment")
        raw_vol = tick.get("volume")
        vol = int(raw_vol) if raw_vol is not None else None

        # 1. Check if tick corresponds to active live paper trading option contract
        active_live = paper_trader.get_portfolio(mode="live").active_positions
        matching_opt_positions = [
            p for p in active_live if p.option_security_id == sec_id_str
        ]
        is_option = bool(matching_opt_positions) or (seg == 2) or (seg == "NSE_FNO")

        if is_option:
            # Extract real bid price from tick for live exit slippage measurement
            bid = (
                tick.get("bid_price")
                if tick.get("bid_price") is not None
                else (
                    tick.get("bid")
                    if tick.get("bid") is not None
                    else (
                        tick.get("best_bid_price")
                        if tick.get("best_bid_price") is not None
                        else tick.get("top_bid_price")
                    )
                )
            )
            if ltp > 0:
                self.record_option_quote(sec_id_str, ltp=ltp, bid=bid, source="ws")
            # Maintain live option candle formation
            self._get_or_update_option_candles(sec_id_str, ltp, vol)
            option_bid_map: Optional[dict[str, float]] = None
            if bid is not None:
                try:
                    bid_f = float(bid)
                    if bid_f > 0:
                        option_bid_map = {sec_id_str: bid_f}
                except (ValueError, TypeError):
                    pass

            # Instantaneous position evaluation and exit execution
            paper_trader.update_market_prices(
                price_map={},
                option_price_map={sec_id_str: ltp},
                feed_mode="live",
                option_bid_map=option_bid_map,
            )
            mode_to_query = "live" if matching_opt_positions else self._state.active_mode
            self._state.paper_portfolio = paper_trader.get_portfolio(
                mode=mode_to_query
            )

        # 2. Check if tick corresponds to an underlying instrument in universe
        inst = None
        if seg is not None:
            try:
                inst = self._seg_sec_id_to_instrument.get((int(seg), sec_id_str))
            except (ValueError, TypeError):
                pass
        if not inst:
            inst = self._sec_id_to_instrument.get(sec_id_str)
        if inst:
            # Update live intraday candles
            self.get_or_update_live_candles(inst, {"last_price": ltp, "volume": vol})

            # Update index radar if applicable
            if inst.symbol in self._state.radar:
                radar_item = self._state.radar[inst.symbol]
                radar_item.close = round(ltp, 2)

            # Update any active paper positions matching the underlying instrument
            underlying_positions = [p for p in active_live if p.symbol == inst.symbol]
            if underlying_positions:
                paper_trader.update_market_prices(
                    price_map={inst.symbol: ltp},
                    option_price_map=None,
                    feed_mode="live",
                )
                self._state.paper_portfolio = paper_trader.get_portfolio(
                    mode=self._state.active_mode
                )

        # 3. Broadcast real-time tick delta to active SSE subscriber queues
        broadcast_data: dict = {
            "type": "tick",
            "security_id": sec_id,
            "ltp": round(ltp, 2),
            "volume": vol,
            "response_code": tick.get("response_code", 2),
            "timestamp": tick.get("ltt"),
        }
        if inst:
            broadcast_data["symbol"] = inst.symbol
            broadcast_data["instrument_type"] = inst.instrument_type
        elif matching_opt_positions:
            broadcast_data["symbol"] = matching_opt_positions[0].symbol
            broadcast_data["strike_symbol"] = matching_opt_positions[0].strike_symbol
            broadcast_data["is_option"] = True

        await self.broadcast(broadcast_data)

    def check_session_reset(self):
        today = market_hours.now_ist().date()
        if self._last_session_date != today:
            logger.info(f"Resetting session candles for new trading day {today}")
            self._candle_history.clear()
            self._current_forming_candle.clear()
            self._option_candle_history.clear()
            self._option_forming_candle.clear()
            self._option_chart_cache.clear()
            self._option_last_cum_volume.clear()
            self._last_cumulative_volume.clear()
            self._instrument_last_quote_time.clear()
            self._last_session_date = today

    def _chain_age_s(self, symbol: str) -> Optional[float]:
        """Seconds since the cached option chain for ``symbol`` was fetched (None if unknown)."""
        cached = self._option_chain_cache.get(symbol)
        if not cached:
            return None
        return round(max(0.0, time.monotonic() - cached[0]), 1)

    def _can_retry_contract_candle(self, sec_id: str, current_time: float) -> bool:
        failed_ts = self._failed_candle_sec_ids.get(sec_id)
        if failed_ts is None:
            return True
        return (current_time - failed_ts) >= 60.0

    def _load_saved_session(self):
        # Zero-Token Persistence: Clean up any stale disk session file
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    def set_session_credentials(
        self, client_id: Optional[str], access_token: Optional[str]
    ):
        self._historical_disabled = False
        self._session_generation += 1
        self._historical_seed_attempts.clear()
        self._historical_seed_fail_count.clear()
        self._option_last_quote_time.clear()
        self._latest_option_quotes.clear()

        if client_id and access_token:
            self._session_credentials = (client_id, access_token)
            self._state.active_mode = "live"
            # Launch async WebSocket connection
            try:
                loop = asyncio.get_running_loop()
                if self._ws_connect_task and not self._ws_connect_task.done():
                    self._ws_connect_task.cancel()
                gen = self._session_generation
                self._ws_connect_task = loop.create_task(
                    self._connect_websocket(client_id, access_token, generation=gen)
                )
            except RuntimeError:
                pass
        else:
            self._session_credentials = None
            self._state.active_mode = "demo"
            self._state.feed_status = "DEMO"
            self._state.ws_connected = False
            # F3: Purge radar and signals on session disconnect
            self._state.signals = []
            self._state.radar = {}
            self._option_chart_cache.clear()
            # Finding 5: Explicitly cancel pending connection task upon disconnect
            if self._ws_connect_task and not self._ws_connect_task.done():
                self._ws_connect_task.cancel()
                self._ws_connect_task = None
            if self.ws_manager:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.ws_manager.disconnect())
                except RuntimeError:
                    pass


        # Zero-Token Persistence: Strictly in-memory, remove file if present
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Could not clear session file: {e}")

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
        """Fallback simulated candles STRICTLY for offline demo mode when market quotes are unavailable."""
        if self._state.active_mode != "demo":
            return pd.DataFrame()

        base_map = {
            "NIFTY 50": 22500.0,
            "NIFTY BANK": 48500.0,
            "FINNIFTY": 21500.0,
            "SENSEX": 74000.0,
            "RELIANCE": 2980.0,
            "HDFCBANK": 1680.0,
            "ICICIBANK": 1280.0,
            "TATAMOTORS": 940.0,
            "INFY": 1920.0,
        }
        base_p = float(base_price) if (base_price and base_price > 0) else base_map.get(inst.symbol, 1500.0)
        start_time = market_hours.now_ist_naive().replace(hour=9, minute=15, second=0, microsecond=0)
        minutes_step = 5 if inst.default_timeframe == "5m" else 15

        records = []
        curr_p = base_p
        for i in range(n):
            ts = start_time + timedelta(minutes=minutes_step * i)
            wave = (np.sin(i * 0.3) * base_p * 0.002)
            open_p = curr_p
            close_p = round(open_p + wave, 2)
            high_p = round(max(open_p, close_p) + (base_p * 0.001), 2)
            low_p = round(min(open_p, close_p) - (base_p * 0.001), 2)
            records.append({
                "timestamp": ts,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 10000
            })
            curr_p = close_p
        return pd.DataFrame(records)

    async def seed_historical_candles_if_needed(
        self,
        client_id: str,
        access_token: str,
        inst: Instrument
    ) -> bool:
        """
        Seed valid current-session historical OHLCV bars from Dhan /charts/intraday API.
        Ensures >= 20 bars are available immediately upon launch or restart.
        """
        sym = inst.symbol
        if len(self._candle_history.get(sym, [])) >= 20:
            return True
        if not client_id or not access_token:
            return False

        # Finding 15: Exponential backoff for failed historical seed attempts
        now_time = time.time()
        fail_count = self._historical_seed_fail_count.get(sym, 0)
        last_attempt = self._historical_seed_attempts.get(sym, 0.0)
        backoff_delay = min(300.0, 30.0 * (2 ** min(fail_count, 4)))
        if (now_time - last_attempt) < backoff_delay:
            return False

        self._historical_seed_attempts[sym] = now_time

        try:
            interval = 5 if inst.default_timeframe == "5m" else 15
            df = await self.dhan_client.fetch_intraday_candles(
                client_id=client_id,
                access_token=access_token,
                security_id=str(inst.security_id),
                exchange_segment=str(inst.exchange_segment),
                instrument_type=str(inst.instrument_type),
                interval=interval,
            )
            if df is not None and not df.empty:
                df = df.copy()
                df["parsed_ts"] = pd.to_datetime(df["timestamp"])
                df = df.dropna(subset=["parsed_ts"]).drop_duplicates(subset=["parsed_ts"]).sort_values("parsed_ts")

                # F8: Validate unique deduplicated bar count
                if len(df) < 20:
                    self._historical_seed_fail_count[sym] = fail_count + 1
                    return False

                # F4: Separate completed bars from any current unfinished bar
                now = market_hours.now_ist_naive()
                completed_records = []
                unfinished_bar = None

                for _, row in df.iterrows():
                    bar_dict = {
                        "timestamp": row["parsed_ts"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row.get("volume", 0)),
                    }
                    slot_end = row["parsed_ts"] + timedelta(minutes=interval)
                    if slot_end <= now:
                        completed_records.append(bar_dict)
                    else:
                        unfinished_bar = bar_dict

                if len(completed_records) < 20:
                    self._historical_seed_fail_count[sym] = fail_count + 1
                    return False

                self._candle_history[sym] = completed_records
                if unfinished_bar:
                    # Merge into active forming candle so it is treated as provisional
                    self._current_forming_candle[sym] = unfinished_bar

                self._historical_seed_attempts.pop(sym, None)
                self._historical_seed_fail_count.pop(sym, None)
                logger.info(f"Successfully seeded {len(completed_records)} historical candles for {sym}")
                return True
            else:
                self._historical_seed_fail_count[sym] = fail_count + 1
        except Exception as e:
            self._historical_seed_fail_count[sym] = fail_count + 1
            logger.debug(f"Could not seed historical candles for {sym}: {e}")
        return False

    def get_or_update_live_candles(self, inst: Instrument, inst_quote: Optional[dict]) -> pd.DataFrame:
        """
        Build and maintain 100% real intraday OHLCV bars populated and updated continuously
        by live Dhan market ticks. Strictly zero random/synthetic data in live mode.
        """
        now = market_hours.now_ist_naive()
        step_min = 5 if inst.default_timeframe == "5m" else 15
        sym = inst.symbol

        if not inst_quote or float(inst_quote.get("last_price", 0.0)) <= 0:
            if self._state.active_mode != "demo":
                forming = self._current_forming_candle.get(sym)
                history = self._candle_history.get(sym, [])
                all_bars = history + ([forming] if forming else [])
                return pd.DataFrame(all_bars)
            return self.generate_synthetic_candles(inst)

        live_ltp = float(inst_quote["last_price"])
        self._instrument_last_quote_time[sym] = time.time()
        
        # Findings 8 & 9: Real incremental volume calculation from cumulative day volume
        raw_vol = inst_quote.get("volume")
        incremental_vol = 0
        if raw_vol is not None:
            quote_vol = int(raw_vol)
            last_cum_vol = self._last_cumulative_volume.get(sym)
            if last_cum_vol is not None and quote_vol >= last_cum_vol:
                incremental_vol = quote_vol - last_cum_vol
            elif quote_vol > 0 and last_cum_vol is None:
                # F6: Subtract volume already represented in today's completed and forming bars
                def _is_today(ts):
                    if not ts:
                        return False
                    if hasattr(ts, "date"):
                        return ts.date() == now.date()
                    try:
                        return pd.to_datetime(ts).date() == now.date()
                    except Exception:
                        return False

                completed_today_vol = sum(
                    int(b.get("volume", 0) or 0)
                    for b in self._candle_history.get(sym, [])
                    if _is_today(b.get("timestamp"))
                )
                forming_bar = self._current_forming_candle.get(sym)
                forming_today_vol = 0
                if forming_bar and _is_today(forming_bar.get("timestamp")):
                    forming_today_vol = int(forming_bar.get("volume", 0) or 0)

                total_represented_vol = completed_today_vol + forming_today_vol
                incremental_vol = max(0, quote_vol - total_represented_vol)
            self._last_cumulative_volume[sym] = quote_vol

        # Initialize intraday history if not present
        if sym not in self._candle_history:
            self._candle_history[sym] = []

        if sym not in self._current_forming_candle:
            forming_ts = now.replace(second=0, microsecond=0)
            forming_min = (forming_ts.minute // step_min) * step_min
            forming_ts = forming_ts.replace(minute=forming_min)
            self._current_forming_candle[sym] = {
                "timestamp": forming_ts,
                "open": live_ltp,
                "high": live_ltp,
                "low": live_ltp,
                "close": live_ltp,
                "volume": 0,
            }

        # Update the forming candle with the live tick
        forming = self._current_forming_candle[sym]
        forming_ts = forming["timestamp"]
        bar_elapsed = (now - forming_ts).total_seconds()

        current_slot_min = (now.minute // step_min) * step_min
        current_slot_ts = now.replace(minute=current_slot_min, second=0, microsecond=0)

        if bar_elapsed >= (step_min * 60) or forming_ts.date() != now.date():
            self._candle_history[sym].append(forming)
            self._bar_completed_symbols.add(sym)
            forming = {
                "timestamp": current_slot_ts,
                "open": live_ltp,
                "high": live_ltp,
                "low": live_ltp,
                "close": live_ltp,
                "volume": 0,
            }
            self._current_forming_candle[sym] = forming
        else:
            forming["high"] = max(forming["high"], live_ltp)
            forming["low"] = min(forming["low"], live_ltp)
            forming["close"] = live_ltp

        # Finding 9: Increment volume exactly once on the unified path
        forming["volume"] = max(0, forming.get("volume", 0) + incremental_vol)

        all_bars = self._candle_history[sym] + [forming]
        return pd.DataFrame(all_bars)

    async def get_or_fetch_option_chain(
        self,
        client_id: str,
        access_token: str,
        inst: Instrument
    ) -> tuple[str, dict]:
        """Fetch and cache (with 15s TTL) the nearest expiry option chain for an instrument."""
        now_mono = time.monotonic()
        sym = inst.symbol

        today_str = market_hours.now_ist_naive().strftime("%Y-%m-%d")
        expiry = self._expiry_cache.get(sym)
        if expiry and expiry < today_str:
            self._expiry_cache.pop(sym, None)
            expiry = None

        if not expiry:
            try:
                exp_list = await self.dhan_client.fetch_expiry_list(
                    client_id=client_id,
                    access_token=access_token,
                    underlying_scrip=int(inst.security_id),
                    underlying_seg=inst.exchange_segment
                )
                if exp_list and len(exp_list) > 0:
                    valid_expiries = [e for e in exp_list if str(e) >= today_str]
                    expiry = valid_expiries[0] if valid_expiries else exp_list[0]
                    self._expiry_cache[sym] = expiry
            except Exception as e:
                logger.warning(f"Error resolving expiry for {sym}: {e}")

        if not expiry:
            return "", {}

        cached = self._option_chain_cache.get(sym)
        if cached:
            ts, oc = cached
            if (now_mono - ts) < 15.0:
                return expiry, oc

        try:
            oc = await self.dhan_client.fetch_option_chain(
                client_id=client_id,
                access_token=access_token,
                underlying_scrip=int(inst.security_id),
                underlying_seg=inst.exchange_segment,
                expiry=expiry
            )
            fetch_mono = time.monotonic()
            if oc:
                self._option_chain_cache[sym] = (fetch_mono, oc)
                return expiry, oc
            else:
                self._expiry_cache.pop(sym, None)
        except Exception as e:
            logger.warning(f"Error fetching option chain for {sym}: {e}")
            self._expiry_cache.pop(sym, None)

        return expiry, {}

    async def run_single_scan_cycle(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> ScannerState:
        """Run a full cycle across all instruments in the universe with re-entrancy protection."""
        if self._scan_lock.locked():
            return self._state
        async with self._scan_lock:
            return await self._execute_scan_cycle(client_id, access_token)

    async def _execute_scan_cycle(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> ScannerState:
        """Execute scan cycle with guaranteed is_scanning = False reset via finally block."""
        self._state.is_scanning = True
        self._state.scan_progress = 0.0
        try:
            return await self._run_scan_cycle_body(client_id, access_token)
        finally:
            self._state.is_scanning = False

    async def _run_scan_cycle_body(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> ScannerState:
        self.check_session_reset()
        gen = self._session_generation

        cid = client_id or (self._session_credentials[0] if self._session_credentials else None)
        tok = access_token or (self._session_credentials[1] if self._session_credentials else None)

        instruments = self.universe_mgr.get_universe()
        total_count = len(instruments)
        self._state.universe_count = total_count

        new_signals: list[Signal] = []
        new_radar: dict[str, IndexRadarItem] = {}
        price_map: dict[str, float] = {}

        # Batch-fetch real-time market quotes (LTP, OHLC, volume, net change) via marketfeed
        live_quotes: dict = {}
        has_creds = bool(cid and tok)
        if has_creds:
            try:
                req_securities: dict[str, list[int]] = {}
                for inst in instruments:
                    try:
                        sec_id_int = int(inst.security_id)
                        req_securities.setdefault(inst.exchange_segment, []).append(sec_id_int)
                    except ValueError:
                        pass

                # Also batch-fetch active paper positions option quotes on NSE_FNO
                active_pos = paper_trader.get_portfolio().active_positions
                for p in active_pos:
                    if p.option_security_id:
                        try:
                            req_securities.setdefault("NSE_FNO", []).append(int(p.option_security_id))
                        except ValueError:
                            pass

                fetch_fn = getattr(self.dhan_client, "fetch_marketfeed_quotes", None)
                import inspect
                if fetch_fn and inspect.iscoroutinefunction(fetch_fn):
                    live_quotes = await fetch_fn(cid, tok, req_securities)
                    if live_quotes:
                        logger.debug(f"Live marketfeed quotes fetched for {sum(len(v) for v in live_quotes.values())} securities")
            except Exception as e:
                logger.warning(f"Error fetching live marketfeed quotes: {e}")

        # Finding 6: Abort if disconnected or session generation changed during await
        if self._session_generation != gen or (cid and not self._session_credentials and not client_id):
            logger.info("Scan cycle aborted: credentials disconnected in-flight")
            self._state.is_scanning = False
            self._state.active_mode = "demo"
            self._state.feed_status = "DEMO"
            return self._state

        # Derive active mode and feed health from quote success or active WebSocket feed
        loop_time = asyncio.get_running_loop().time()
        ws_healthy = bool(self.ws_manager and self.ws_manager.is_healthy)
        self._state.ws_connected = bool(self.ws_manager and self.ws_manager.is_connected)
        if has_creds and (self._session_credentials or client_id):
            if ws_healthy:
                self._last_successful_quote_time = loop_time
                mode = "live"
                self._state.active_mode = "live"
                self._state.feed_status = "WS_LIVE"
                self._state.last_quote_time = market_hours.now_ist_naive().strftime("%H:%M:%S")
            elif live_quotes and len(live_quotes) > 0:
                self._last_successful_quote_time = loop_time
                mode = "live"
                self._state.active_mode = "live"
                self._state.feed_status = "LIVE"
                self._state.last_quote_time = market_hours.now_ist_naive().strftime("%H:%M:%S")
            elif self._last_successful_quote_time and (loop_time - self._last_successful_quote_time) <= 30.0:
                mode = "live"
                self._state.active_mode = "live"
                self._state.feed_status = "WS_LIVE" if ws_healthy else "LIVE"
            elif self._last_successful_quote_time and (loop_time - self._last_successful_quote_time) <= 60.0:
                mode = "stale"
                self._state.active_mode = "stale"
                self._state.feed_status = "STALE"
            else:
                mode = "error"
                self._state.active_mode = "error"
                self._state.feed_status = "ERROR"
        else:
            mode = "demo"
            self._state.active_mode = "demo"
            self._state.feed_status = "DEMO"

        # P0-1: outside the exchange session a credentialed scan is "closed", never "live":
        # no auto-entries, no new option forming bars, no Setup 1-5 evaluation on stale data.
        if mode != "demo" and not market_hours.is_market_open():
            mode = "closed"
            self._state.active_mode = "closed"
            self._state.feed_status = "CLOSED"

        # Extract live option quotes and bid prices from NSE_FNO
        option_price_map: dict[str, float] = {}
        option_bid_map: dict[str, float] = {}
        if live_quotes:
            quotes_dict = live_quotes.get("data", live_quotes) if isinstance(live_quotes.get("data"), dict) else live_quotes
            fno_quotes = quotes_dict.get("NSE_FNO", {})
            for sec_k, q in fno_quotes.items():
                if isinstance(q, dict):
                    if "last_price" in q:
                        try:
                            opt_ltp = float(q["last_price"])
                            if opt_ltp > 0:
                                option_price_map[str(sec_k)] = opt_ltp
                        except (ValueError, TypeError):
                            pass
                    bid_val = (
                        q.get("top_bid_price")
                        if q.get("top_bid_price") is not None
                        else (
                            q.get("bid")
                            if q.get("bid") is not None
                            else (
                                q.get("best_bid_price")
                                if q.get("best_bid_price") is not None
                                else q.get("bid_price")
                            )
                        )
                    )
                    if bid_val is not None:
                        try:
                            b_f = float(bid_val)
                            if b_f > 0:
                                option_bid_map[str(sec_k)] = b_f
                        except (ValueError, TypeError):
                            pass

        # Rank momentum stocks across the entire F&O universe based on real-time marketfeed quotes
        stock_quotes_for_ranking: dict[str, dict] = {}
        if live_quotes:
            quotes_dict = live_quotes.get("data", live_quotes) if isinstance(live_quotes.get("data"), dict) else live_quotes
            eq_quotes = quotes_dict.get("NSE_EQ", {})
            for stock_inst in self.universe_mgr.get_fno_stocks():
                q = eq_quotes.get(str(stock_inst.security_id)) or eq_quotes.get(int(stock_inst.security_id))
                if q and isinstance(q, dict):
                    stock_quotes_for_ranking[stock_inst.symbol] = q

            # Also populate full price_map across all instruments from live quotes
            for inst in instruments:
                seg_quotes = quotes_dict.get(inst.exchange_segment, {})
                q = seg_quotes.get(str(inst.security_id)) or seg_quotes.get(int(inst.security_id))
                if q and isinstance(q, dict) and "last_price" in q:
                    lp = float(q["last_price"])
                    if lp > 0:
                        price_map[inst.symbol] = lp

        rankings = self.momentum_ranker.rank_stocks(stock_quotes_for_ranking)
        market_bias = "NEUTRAL"

        # Tier 2 Selection: Deep Bollinger setup scanning on Indices + Top Momentum stocks + active positions
        top_symbols = set(rankings.top_bullish + rankings.top_bearish)
        active_symbols = set(p.symbol for p in paper_trader.get_portfolio().active_positions)

        deep_scan_targets: list[Instrument] = []
        for inst in self.universe_mgr.get_indices():
            deep_scan_targets.append(inst)

        for sym in (top_symbols | active_symbols):
            inst = self.universe_mgr.get_instrument(sym)
            if inst and inst not in deep_scan_targets:
                deep_scan_targets.append(inst)

        # In demo mode fallback if quotes are synthetic, include core momentum stocks
        if mode == "demo" and len(deep_scan_targets) <= 4:
            for inst in self.universe_mgr.get_momentum_stocks():
                if inst not in deep_scan_targets:
                    deep_scan_targets.append(inst)

        for idx, inst in enumerate(deep_scan_targets):
            inst_quote = None
            if live_quotes:
                quotes_dict = live_quotes.get("data", live_quotes) if isinstance(live_quotes.get("data"), dict) else live_quotes
                seg_quotes = quotes_dict.get(inst.exchange_segment, {})
                inst_quote = seg_quotes.get(str(inst.security_id)) or seg_quotes.get(int(inst.security_id))

            if mode == "live" and cid and tok and len(self._candle_history.get(inst.symbol, [])) < 20:
                await self.seed_historical_candles_if_needed(cid, tok, inst)
                if self._session_generation != gen or (cid and not self._session_credentials and not client_id):
                    return self._state

            # Maintain and update 100% real candles
            df = self.get_or_update_live_candles(inst, inst_quote)
            live_ltp = float(inst_quote.get("last_price", 0.0)) if inst_quote else None
            if (live_ltp is None or live_ltp <= 0) and inst.symbol in self._current_forming_candle:
                live_ltp = float(self._current_forming_candle[inst.symbol].get("close", 0.0))
            # Compute Indicators
            ind_df = calculate_indicators(df)
            current_price = float(live_ltp) if (live_ltp and live_ltp > 0) else 0.0
            if not ind_df.empty:
                if current_price <= 0:
                    current_price = float(ind_df.iloc[-1]["close"])

                # Finding 4: In non-demo modes, only populate trade price_map if this instrument has a fresh quote
                if mode != "demo":
                    is_fresh = (
                        inst_quote is not None and float(inst_quote.get("last_price", 0.0)) > 0
                        and (time.time() - self._instrument_last_quote_time.get(inst.symbol, 0.0)) <= 15.0
                    )
                    if is_fresh:
                        price_map[inst.symbol] = float(inst_quote["last_price"])
                else:
                    price_map[inst.symbol] = current_price

                # If Dhan provides official session VWAP (average_price), use it
                if inst_quote and float(inst_quote.get("average_price", 0.0)) > 0:
                    ind_df.iloc[-1, ind_df.columns.get_loc("vwap")] = float(inst_quote["average_price"])

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

                is_sq = bw_val <= bw_min * 1.25
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

                if inst.symbol == "NIFTY 50":
                    market_bias = "BULLISH" if vwap_b == "ABOVE_VWAP" else "BEARISH"

            # Evaluate Setups with stock momentum and market bias filtering
            stock_bias = rankings.get_bias(inst.symbol) if inst.instrument_type == "EQUITY" else None

            # 1. Closed bars: evaluate on completed history for confirmed signals
            confirmed_signals: list[Signal] = []
            completed_bars = self._candle_history.get(inst.symbol, [])
            if mode == "live" and len(completed_bars) >= 20:
                completed_df = calculate_indicators(pd.DataFrame(completed_bars))
                signals_on_closed = evaluate_signals(
                    inst.symbol,
                    completed_df,
                    timeframe=inst.default_timeframe,
                    stock_bias=stock_bias,
                    market_bias=market_bias
                )
                today_date = market_hours.now_ist_naive().date()
                for s in signals_on_closed:
                    # Finding 1: Only bars completed in today's active session can generate confirmed signals
                    try:
                        s_dt = pd.to_datetime(s.timestamp)
                        if s_dt.date() == today_date:
                            s.is_confirmed = True
                            confirmed_signals.append(s)
                    except Exception:
                        pass

            # 2. Forming bar: evaluate on ind_df (which includes active forming candle)
            provisional_signals = evaluate_signals(
                inst.symbol,
                ind_df,
                timeframe=inst.default_timeframe,
                stock_bias=stock_bias,
                market_bias=market_bias
            )
            for sig in provisional_signals:
                # Finding 3: In live mode, ANY signal evaluated on the active forming candle is provisional
                if mode == "live":
                    sig.is_confirmed = False
                else:
                    sig.is_confirmed = True

            # Merge: confirmed signals take priority over provisional signals
            det_map = {s.id: s for s in provisional_signals}
            for cs in confirmed_signals:
                det_map[cs.id] = cs
            detected = list(det_map.values())

            # Enrich signals and evaluate Setup 5 with live option chain from Dhan
            if mode == "live" and cid and tok:
                try:
                    expiry, oc = await self.get_or_fetch_option_chain(cid, tok, inst)
                    if self._session_generation != gen or (cid and not self._session_credentials and not client_id):
                        return self._state
                    if oc:
                        cached_entry = self._option_chain_cache.get(inst.symbol)
                        chain_fetch_ts = cached_entry[0] if cached_entry else time.monotonic()
                        # Extract strike quotes (LTP, bid) from option chain into option_price_map & option_bid_map
                        for strike_k, strike_data in oc.items():
                            if isinstance(strike_data, dict):
                                for side in ("ce", "pe"):
                                    contract = strike_data.get(side)
                                    if isinstance(contract, dict):
                                        c_sec_id = contract.get("security_id")
                                        if c_sec_id is not None:
                                            c_sec_id_str = str(c_sec_id)
                                            c_bid = (
                                                contract.get("top_bid_price")
                                                if contract.get("top_bid_price") is not None
                                                else (
                                                    contract.get("bid")
                                                    if contract.get("bid") is not None
                                                    else (
                                                        contract.get("best_bid_price")
                                                        if contract.get("best_bid_price") is not None
                                                        else contract.get("bid_price")
                                                    )
                                                )
                                            )
                                            c_bid_f = None
                                            if c_bid is not None:
                                                try:
                                                    b = float(c_bid)
                                                    if b > 0:
                                                        c_bid_f = b
                                                        option_bid_map[c_sec_id_str] = b
                                                except (ValueError, TypeError):
                                                    pass

                                            c_ltp = contract.get("last_price")
                                            if c_ltp is not None:
                                                try:
                                                    c_ltp_f = float(c_ltp)
                                                    if c_ltp_f > 0:
                                                        option_price_map[c_sec_id_str] = c_ltp_f
                                                        self.record_option_quote(
                                                            c_sec_id_str,
                                                            ltp=c_ltp_f,
                                                            bid=c_bid_f,
                                                            source="chain",
                                                            timestamp=chain_fetch_ts
                                                        )
                                                except (ValueError, TypeError):
                                                    pass

                        # Enrich detected signals with live option quotes
                        if detected:
                            for sig in detected:
                                is_snapback = sig.setup_type in (
                                    SetupType.SETUP_6_PINBAR_SNAPBACK,
                                    SetupType.SETUP_7_INSIDE_BAR_SNAPBACK,
                                    SetupType.SETUP_8_DIVERGENCE_SNAPBACK,
                                ) or "Setup 6" in str(sig.setup_type) or "Setup 7" in str(sig.setup_type) or "Setup 8" in str(sig.setup_type)
                                pref = "ITM_1" if is_snapback else "DEFAULT"
                                live_rec = resolve_live_strike_from_chain(
                                    symbol=sig.symbol,
                                    underlying_price=sig.entry_price,
                                    option_type=sig.option_type,
                                    option_chain_oc=oc,
                                    expiry_date=expiry,
                                    stop_loss=sig.stop_loss,
                                    target_1=sig.target_1,
                                    target_2=sig.target_2,
                                    strike_preference=pref,
                                 )
                                live_rec.quote_age_s = round(max(0.0, time.monotonic() - chain_fetch_ts), 1)
                                sig.strike_recommendation = live_rec

                        # Also evaluate Setup 5 (Option Chart BB Scalp) directly on live option candles
                        if current_price > 0:
                            opt_signals = await self._evaluate_option_chart_setups(cid, tok, inst, oc, expiry, current_price)
                            # Finding 5: Abort if disconnected or session generation changed during option candle await
                            if self._session_generation != gen or (cid and not self._session_credentials and not client_id):
                                logger.info("Scan cycle aborted after option chart setups evaluation: session disconnected")
                                return self._state
                            detected.extend(opt_signals)
                except Exception as e:
                    logger.warning(f"Error processing option chain for {inst.symbol}: {e}")

            new_signals.extend(detected)
            self._bar_completed_symbols.discard(inst.symbol)

            # Update progress
            self._state.scan_progress = round(((idx + 1) / max(1, len(deep_scan_targets))) * 100.0, 1)

        # Finding 5: Abort before trade mutation or price update if session was invalidated
        if cid and (self._session_generation != gen or (not self._session_credentials and not client_id)):
            logger.info("Scan cycle aborted before trade execution: session disconnected")
            self._state.is_scanning = False
            self._state.active_mode = "demo"
            self._state.feed_status = "DEMO"
            return self._state

        # Update paper trading engine with latest market prices and real option prices
        paper_trader.update_market_prices(
            price_map,
            option_price_map,
            feed_mode=mode,
            option_bid_map=option_bid_map,
        )
        if mode != "demo":
            # P0-5: close stale carry-overs and square off at the EOD time (live positions only)
            paper_trader.flag_stale_carryover()
            paper_trader.square_off_if_due(feed_mode="live")
        if mode in ("live", "demo"):
            paper_trader.on_signals_cycle(new_signals, feed_mode=mode)
        if mode == "live" and ws_healthy:
            await self._subscribe_active_positions()

        # F5: Abort state publication if session generation changed or disconnected during subscription await
        if cid and (self._session_generation != gen or (not self._session_credentials and not client_id)):
            logger.info("Scan cycle aborted after position subscription: session disconnected")
            self._state.active_mode = "demo"
            self._state.feed_status = "DEMO"
            return self._state

        self._state.signals = new_signals
        self._state.radar = new_radar
        self._state.top_bullish = rankings.top_bullish
        self._state.top_bearish = rankings.top_bearish
        self._state.market_bias = market_bias
        self._state.paper_portfolio = paper_trader.get_portfolio(mode=mode)
        self._state.last_scan_time = market_hours.now_ist_naive().strftime("%H:%M:%S")
        self._state.scan_cycle_count += 1
        self._state.is_scanning = False
        self._state.scan_progress = 100.0

        # Broadcast update to connected SSE subscribers
        await self.broadcast(self._state.model_dump())
        return self._state

    def _option_volume_increment(self, sec_id: str, cumulative: Optional[int]) -> Optional[int]:
        """Per-update volume increment from Dhan's cumulative day volume.

        Returns None when no increment can be derived (volume missing, first observation,
        or the counter went backwards, e.g. a new session), in which case the bar volume
        is treated as unknown rather than being taken as the day's total.
        """
        if cumulative is None:
            return None
        last = self._option_last_cum_volume.get(sec_id)
        self._option_last_cum_volume[sec_id] = cumulative
        if last is None or cumulative < last:
            return None
        return cumulative - last

    def _get_or_update_option_candles(
        self,
        sec_id: str,
        ltp: float,
        volume: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Maintain 5m option bars from ticks. ``volume`` is the CUMULATIVE day volume
        (None if unknown). Bars are only created/updated while the exchange is open and
        are keyed on IST slot starts, never on wall-clock elapsed time."""
        step_min = 5
        history = self._option_candle_history.setdefault(sec_id, [])
        forming = self._option_forming_candle.get(sec_id)

        if market_hours.is_market_open(now):
            slot = market_hours.ist_slot_start(now, step_min)
            inc = self._option_volume_increment(sec_id, volume)

            if forming is not None and pd.Timestamp(forming["timestamp"]) < slot:
                history.append(forming)
                forming = None

            if forming is None:
                forming = {
                    "timestamp": slot,
                    "open": ltp, "high": ltp, "low": ltp, "close": ltp,
                    "volume": inc or 0,
                    "volume_known": inc is not None,
                }
                self._option_forming_candle[sec_id] = forming
            else:
                forming["high"] = max(forming["high"], ltp)
                forming["low"] = min(forming["low"], ltp)
                forming["close"] = ltp
                if inc is not None:
                    forming["volume"] = int(forming.get("volume", 0)) + inc
                    forming["volume_known"] = True

        all_bars = history + ([forming] if forming else [])
        return pd.DataFrame(all_bars)

    async def _evaluate_option_chart_setups(
        self,
        cid: str,
        tok: str,
        inst: Instrument,
        oc: dict,
        expiry: str,
        underlying_price: float
    ) -> list[Signal]:
        results: list[Signal] = []
        if not oc or underlying_price <= 0:
            return results
        # P0-1/P0-4: no Setup 5 evaluation outside the session or after the 15:15 entry cutoff
        if not market_hours.is_entry_allowed():
            return results

        strikes = []
        for k in oc.keys():
            try:
                strikes.append(float(k))
            except ValueError:
                pass
        if not strikes:
            return results

        atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))
        atm_int = int(atm_strike) if atm_strike.is_integer() else atm_strike
        atm_key = (
            str(atm_int) if str(atm_int) in oc
            else (str(atm_strike) if str(atm_strike) in oc
            else (f"{atm_strike:.6f}" if f"{atm_strike:.6f}" in oc else str(atm_strike)))
        )
        strike_data = oc.get(atm_key, oc.get(str(atm_int), oc.get(str(atm_strike), oc.get(f"{atm_strike:.6f}", {}))))
        if not isinstance(strike_data, dict):
            return results

        lot_size = get_lot_size(inst.symbol)
        inst_type_dhan = "OPTIDX" if inst.instrument_type == "INDEX" else "OPTSTK"

        for opt_type in ("CE", "PE"):
            opt_info = strike_data.get(opt_type.lower(), {})
            if not isinstance(opt_info, dict):
                continue
            sec_id = opt_info.get("security_id")
            if not sec_id:
                continue

            opt_ltp = float(opt_info.get("last_price", 0.0))
            # Dhan chain volume is the CUMULATIVE day volume; None when absent (unknown)
            raw_opt_vol = opt_info.get("volume")
            opt_vol = int(raw_opt_vol) if raw_opt_vol is not None else None
            sec_id_str = str(sec_id)
            strike_symbol = f"{inst.symbol} {int(atm_strike)} {opt_type}"

            completed_df = pd.DataFrame()
            current_slot_ts = market_hours.ist_slot_start()
            now_loop = asyncio.get_running_loop().time()

            cached = self._option_chart_cache.get(sec_id_str)
            if cached and cached[0] == current_slot_ts:
                completed_df = cached[1]
            elif self._can_retry_contract_candle(sec_id_str, now_loop):
                try:
                    fetched_df = await self.dhan_client.fetch_intraday_candles(
                        client_id=cid,
                        access_token=tok,
                        security_id=sec_id_str,
                        exchange_segment="NSE_FNO",
                        instrument_type=inst_type_dhan,
                        interval=5
                    )
                    if fetched_df.empty:
                        self._failed_candle_sec_ids[sec_id_str] = now_loop
                    else:
                        self._failed_candle_sec_ids.pop(sec_id_str, None)
                        # F5: Cache only completed bars strictly before the current forming slot
                        if "timestamp" in fetched_df.columns:
                            ts_series = pd.to_datetime(fetched_df["timestamp"])
                            completed_df = fetched_df[ts_series < current_slot_ts].copy()
                            forming_rows = fetched_df[ts_series >= current_slot_ts]
                            if not forming_rows.empty and sec_id_str not in self._option_forming_candle:
                                seed_bar = forming_rows.iloc[-1].to_dict()
                                self._option_forming_candle[sec_id_str] = {
                                    "timestamp": seed_bar.get("timestamp", current_slot_ts),
                                    "open": float(seed_bar.get("open", opt_ltp)),
                                    "high": float(seed_bar.get("high", opt_ltp)),
                                    "low": float(seed_bar.get("low", opt_ltp)),
                                    "close": float(seed_bar.get("close", opt_ltp)),
                                    "volume": int(seed_bar.get("volume", 0)),
                                    "volume_known": True,
                                }
                        else:
                            completed_df = fetched_df.copy()
                        self._option_chart_cache[sec_id_str] = (current_slot_ts, completed_df)
                except Exception as e:
                    logger.debug(f"Error checking option chart candles for {strike_symbol}: {e}")
                    self._failed_candle_sec_ids[sec_id_str] = now_loop

            # Maintain the live forming candle with the latest tick (only while the market is open)
            if opt_ltp > 0:
                self._get_or_update_option_candles(sec_id_str, opt_ltp, opt_vol)

            # P0-4: Setup 5 is evaluated on COMPLETED bars only. The forming bar is excluded,
            # so a signal can never be raised (or acted on) from a half-formed candle.
            local_history = self._option_candle_history.get(sec_id_str, [])
            local_df = pd.DataFrame(local_history) if local_history else pd.DataFrame()
            frames = [f for f in (local_df, completed_df) if not f.empty]
            if frames:
                # Exchange-fetched bars (listed last) win over locally built bars for the same slot
                opt_candles = pd.concat(frames, ignore_index=True)
                opt_candles["timestamp"] = pd.to_datetime(opt_candles["timestamp"])
                opt_candles = opt_candles[opt_candles["timestamp"] < current_slot_ts]
                opt_candles = opt_candles.drop_duplicates(subset=["timestamp"], keep="last")
                opt_candles = opt_candles.sort_values("timestamp").reset_index(drop=True)
            else:
                opt_candles = pd.DataFrame()

            # Ignore stale series (e.g. last completed bar is from a previous session / long gap)
            if not opt_candles.empty and opt_candles["timestamp"].iloc[-1] < current_slot_ts - timedelta(minutes=10):
                opt_candles = pd.DataFrame()

            if not opt_candles.empty and len(opt_candles) >= 20:
                ind_opt = calculate_indicators(opt_candles)
                sig = evaluate_option_chart_signal(
                    symbol=inst.symbol,
                    strike_symbol=strike_symbol,
                    option_type=opt_type,
                    option_df=ind_opt,
                    underlying_price=underlying_price,
                    strike_price=atm_strike,
                    expiry_date=expiry,
                    lot_size=lot_size,
                    option_security_id=sec_id_str,
                    timeframe="5m",
                    current_quote={
                        "quote_age_s": self._chain_age_s(inst.symbol),
                        "last_price": opt_ltp,
                        "volume": opt_vol,
                        "ask_price": float(opt_info.get("top_ask_price", 0.0) or opt_info.get("ask_price", 0.0) or 0.0),
                        "bid_price": float(opt_info.get("top_bid_price", 0.0) or opt_info.get("bid_price", 0.0) or 0.0),
                        "is_live_quote": bool(opt_ltp > 0 or float(opt_info.get("top_ask_price", 0.0) or 0.0) > 0)
                    }
                )
                if sig:
                    results.append(sig)

        return results

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
        if paper_trader.on_position_opened == self._on_paper_position_opened:
            paper_trader.on_position_opened = None
        if self._ws_connect_task and not self._ws_connect_task.done():
            self._ws_connect_task.cancel()
            try:
                await self._ws_connect_task
            except asyncio.CancelledError:
                pass
            self._ws_connect_task = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.ws_manager:
            try:
                await self.ws_manager.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting ws_manager: {e}")
        close_fn = getattr(self.dhan_client, "close", None)
        if close_fn:
            import inspect
            if inspect.iscoroutinefunction(close_fn):
                await close_fn()
            else:
                res = close_fn()
                if asyncio.iscoroutine(res):
                    await res
        logger.info("ScannerWorker background loop stopped")
