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
from app.services.scanner_models import *  # noqa: F401,F403
from app.services.scanner_candles import ScannerCandlesMixin
from app.services.scanner_stream import ScannerStreamMixin
from app.services.universe_manager import UniverseManager, Instrument
from app.services.dhan_client import DhanClient
from app.services.dhan_websocket import DhanWebSocketManager
from app.services.dhan_packet_codec import segment_to_int
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, Signal, SetupType
from app.services.relative_strength import evaluate_relative_strength, NIFTY_SYMBOL
from app.services.strike_selector import resolve_live_strike_from_chain, get_lot_size, option_exchange_segment
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.setup11 import evaluate_setup11
from app.services.setup13 import evaluate_option_vwap_reclaim
from app.services.setup12 import evaluate_adx_ema_cross
from app.services.setup14 import WALL_REFRESH_S, compute_oi_walls, evaluate_oi_wall_bounce
from app.services.straddle_squeeze import StraddleLeg, evaluate_straddle_squeeze
from app.services.paper_trader import paper_trader, PaperPortfolio, PaperPosition
from app.services.momentum_ranker import MomentumRanker, MomentumRankings
logger = logging.getLogger(__name__)


from app.services import notifier


class ScannerWorker(ScannerCandlesMixin, ScannerStreamMixin):
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
        self._last_tick_broadcast: dict[str, float] = {}
        self._last_portfolio_publish: float = 0.0
        self._portfolio_publish_pending: bool = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session_credentials: Optional[tuple[str, str]] = None
        self._historical_disabled: bool = False
        self._session_generation: int = 0
        self._expiry_cache: dict[str, str] = {}
        self._option_chain_cache: dict[str, tuple[float, dict]] = {}
        self._oi_wall_cache: dict[str, tuple[float, object]] = {}  # Setup 14: symbol -> (monotonic ts, OIWalls)
        self._option_chart_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._candle_history: dict[str, list[dict]] = {}
        self._trade_candle_saved_at: dict[str, float] = {}
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

    def _on_paper_position_opened(self, pos: PaperPosition) -> None:
        """Whenever a live paper trading position is opened, dynamically subscribe its option contract."""
        if pos.feed_mode == "live" and pos.option_security_id:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.subscribe_option_instrument(pos.option_security_id, pos.symbol))
            except RuntimeError:
                pass


    def persist_trade_candles(self, throttle_s: float = 30.0) -> None:
        """Save the candles each open trade charts from, so closed trades and restarts keep their chart.
        Open trades are re-saved at most every `throttle_s`; a trade that closed since the last call gets a final save."""
        storage = paper_trader.storage
        if storage is None:
            return
        try:
            pf = paper_trader._portfolio
            now = time.time()
            last = self._trade_candle_saved_at
            targets = [p for p in pf.active_positions if now - last.get(p.id, 0.0) >= throttle_s]
            # Closed trades still owed a final snapshot: ones seen open earlier, and ones that opened and
            # closed between two calls (never in `last`) unless a snapshot is already stored.
            for p in pf.closed_trades:
                if last.get(p.id, 0.0) < 0:
                    continue
                if p.id in last or not storage.load_trade_candles(p.id, "option"):
                    targets.append(p)
                else:
                    last[p.id] = -1.0
            closed_ids = {p.id for p in pf.closed_trades}
            from app.api.position_chart import position_bars
            for p in targets:
                try:
                    opt, und = position_bars(self, p)
                    if opt is not None and not opt.empty:
                        storage.save_trade_candles(p.id, "option", opt.to_dict("records"))
                    if und is not None and not und.empty:
                        storage.save_trade_candles(p.id, "underlying", und.to_dict("records"))
                except Exception as e:
                    logger.warning(f"Could not persist candles for {p.id}: {e}")  # retried next call
                    continue
                last[p.id] = -1.0 if p.id in closed_ids else now  # -1: final snapshot taken
        except Exception as e:
            logger.warning(f"Could not persist trade candles: {e}")

    def check_session_reset(self):
        today = market_hours.now_ist().date()
        if self._last_session_date != today:
            logger.info(f"Resetting session candles for new trading day {today}")
            self._candle_history.clear()
            self._current_forming_candle.clear()
            self._option_candle_history.clear()
            self._option_forming_candle.clear()
            self._option_chart_cache.clear()
            self._oi_wall_cache.clear()
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
        self._last_successful_quote_time = None

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
        started = time.monotonic()
        try:
            return await self._run_scan_cycle_body(client_id, access_token)
        finally:
            self._state.is_scanning = False
            self._state.last_scan_seconds = round(time.monotonic() - started, 2)
            logger.info("Scan cycle %d took %.2fs", self._state.scan_cycle_count, self._state.last_scan_seconds)

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
                            req_securities.setdefault(option_exchange_segment(p.symbol), []).append(int(p.option_security_id))
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
        notifier.report_feed_mode(mode)

        # Extract live option quotes and bid prices from NSE_FNO
        option_price_map: dict[str, float] = {}
        option_bid_map: dict[str, float] = {}
        if live_quotes:
            quotes_dict = live_quotes.get("data", live_quotes) if isinstance(live_quotes.get("data"), dict) else live_quotes
            fno_quotes = {**quotes_dict.get("NSE_FNO", {}), **quotes_dict.get("BSE_FNO", {})}
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

                is_sq = (bw_val <= bw_min * 1.25) or (bw_val <= float(settings.SQUEEZE_ABS_BW_PCT))
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
            completed_df = None
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

                # Setup 12 (ADX + EMA 20 trend cross) only fires on completed bars; isolated like Setup 9
                try:
                    s12_signals = evaluate_adx_ema_cross(inst.symbol, completed_df, timeframe=inst.default_timeframe)
                except Exception as e:
                    logger.warning(f"Setup 12 evaluation failed for {inst.symbol}: {e}")
                    s12_signals = []
                for s in s12_signals:
                    try:
                        if pd.to_datetime(s.timestamp).date() == today_date:
                            confirmed_signals.append(s)
                    except Exception:
                        pass

                # Setup 9 (relative strength vs NIFTY) only fires on completed bars
                nifty_bars = self._candle_history.get(NIFTY_SYMBOL, [])
                if stock_bias and inst.instrument_type == "EQUITY" and nifty_bars:
                    # Isolated so a bad candle can never abort the cycle (and with it exits for open positions)
                    try:
                        rs_signals = evaluate_relative_strength(
                            inst.symbol,
                            completed_df,
                            pd.DataFrame(nifty_bars),
                            timeframe=inst.default_timeframe,
                            stock_bias=stock_bias,
                        )
                    except Exception as e:
                        logger.warning(f"Setup 9 evaluation failed for {inst.symbol}: {e}")
                        rs_signals = []
                    for s in rs_signals:
                        if pd.to_datetime(s.timestamp).date() == today_date:
                            confirmed_signals.append(s)

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

                        # Setup 14 (OI wall bounce): walls from the chain's open interest, refreshed every 15 minutes
                        if completed_df is not None and market_hours.is_entry_allowed():
                            try:
                                cached_w = self._oi_wall_cache.get(inst.symbol)
                                if cached_w is None or (time.monotonic() - cached_w[0]) >= WALL_REFRESH_S:
                                    w = compute_oi_walls(oc, current_price)
                                    cached_w = (time.monotonic(), w)
                                    self._oi_wall_cache[inst.symbol] = cached_w
                                s14 = evaluate_oi_wall_bounce(
                                    inst.symbol, completed_df, cached_w[1],
                                    timeframe=inst.default_timeframe,
                                    chain_age_s=max(0.0, time.monotonic() - chain_fetch_ts),
                                )
                            except Exception as e:
                                logger.warning(f"Setup 14 evaluation failed for {inst.symbol}: {e}")
                                s14 = []
                            for s in s14:
                                if pd.to_datetime(s.timestamp).date() == today_date:
                                    detected.append(s)

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
                                live_rec.quote_as_of = time.time() - live_rec.quote_age_s
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

            # Closed session: candles are yesterday's, so nothing is a live/confirmed signal.
            if mode != "closed":
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
        # P0-5: in every mode (a demo scan after a disconnect too) close positions carried over
        # from an earlier date (both books) and square off live positions at the EOD time.
        paper_trader.flag_stale_carryover()
        paper_trader.square_off_if_due(feed_mode="live")
        self.persist_trade_candles()
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
        # Market bias comes from NIFTY vs VWAP on stale candles outside the session: not meaningful.
        self._state.market_bias = "NEUTRAL" if mode == "closed" else market_bias
        self._state.paper_portfolio = paper_trader.get_portfolio_summary(mode=mode)
        self._state.last_scan_time = market_hours.now_ist_naive().strftime("%H:%M:%S")
        self._state.scan_cycle_count += 1
        self._state.is_scanning = False
        self._state.scan_progress = 100.0

        # Broadcast update to connected SSE subscribers
        await self.broadcast(self._state.model_dump())
        return self._state

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
        straddle_legs: dict[str, StraddleLeg] = {}
        s13_candidates: list[Signal] = []

        # Setup 13 compares the option's VWAP reclaim with the underlying's own VWAP (completed spot bars)
        spot_bars = self._candle_history.get(inst.symbol, [])
        spot_ind = calculate_indicators(pd.DataFrame(spot_bars)) if len(spot_bars) >= 20 else None

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
                        exchange_segment=option_exchange_segment(inst.symbol),
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
                leg_quote = {
                    "quote_age_s": self._chain_age_s(inst.symbol),
                    "last_price": opt_ltp,
                    "volume": opt_vol,
                    # Chain snapshot, logged on the trade so a liquidity filter can be tested later.
                    "day_volume": opt_info.get("volume"),
                    "oi": opt_info.get("oi"),
                    "top_bid_quantity": opt_info.get("top_bid_quantity"),
                    "top_ask_quantity": opt_info.get("top_ask_quantity"),
                    "ask_price": float(opt_info.get("top_ask_price", 0.0) or opt_info.get("ask_price", 0.0) or 0.0),
                    "bid_price": float(opt_info.get("top_bid_price", 0.0) or opt_info.get("bid_price", 0.0) or 0.0),
                    "is_live_quote": bool(opt_ltp > 0 or float(opt_info.get("top_ask_price", 0.0) or 0.0) > 0)
                }
                straddle_legs[opt_type] = StraddleLeg(
                    df=ind_opt, strike_symbol=strike_symbol, security_id=sec_id_str, quote=leg_quote,
                )
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
                    current_quote=leg_quote,
                )
                if sig:
                    results.append(sig)
                    s11 = evaluate_setup11(ind_opt, sig)
                    if s11:
                        results.append(s11)
                try:
                    s13 = evaluate_option_vwap_reclaim(
                        symbol=inst.symbol,
                        strike_symbol=strike_symbol,
                        option_type=opt_type,
                        option_df=ind_opt,
                        spot_df=spot_ind,
                        underlying_price=underlying_price,
                        strike_price=atm_strike,
                        expiry_date=expiry,
                        lot_size=lot_size,
                        option_security_id=sec_id_str,
                        timeframe="5m",
                        current_quote=leg_quote,
                    )
                except Exception as e:
                    logger.warning(f"Setup 13 evaluation failed for {strike_symbol}: {e}")
                    s13 = None
                if s13:
                    s13_candidates.append(s13)

        # Setup 10: ATM straddle premium squeeze, from the same two completed-bar series.
        # Skipped when Setup 5 already fired on this side, so one contract is never entered twice.
        if len(straddle_legs) == 2:
            s10 = evaluate_straddle_squeeze(
                symbol=inst.symbol,
                legs=straddle_legs,
                underlying_price=underlying_price,
                strike_price=atm_strike,
                expiry_date=expiry,
                lot_size=lot_size,
                timeframe="5m",
            )
            if s10 and not any(r.option_type == s10.option_type and r.setup_type == SetupType.SETUP_5_OPTION_BB
                               for r in results):
                results.append(s10)

        # Setup 13: never enter the same side as Setup 5 or Setup 10 in one scan (one contract, one entry)
        for s13 in s13_candidates:
            if not any(r.option_type == s13.option_type and r.setup_type in (
                    SetupType.SETUP_5_OPTION_BB, SetupType.SETUP_10_STRADDLE_SQUEEZE) for r in results):
                results.append(s13)

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
