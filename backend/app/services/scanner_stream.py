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
from app.services.scanner_models import *  # noqa: F401,F403


class ScannerStreamMixin:
    """Methods split out of ScannerWorker (no behaviour change)."""

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
            self._state.paper_portfolio = paper_trader.get_portfolio_summary(
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
                self._state.paper_portfolio = paper_trader.get_portfolio_summary(
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
