"""Candle and option-chain building for the scanner (underlying 5m bars, option bars, chain cache)."""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd

from app.services import market_hours
from app.services.universe_manager import Instrument

logger = logging.getLogger(__name__)


class ScannerCandlesMixin:
    """Candle and option-chain building for the scanner (underlying 5m bars, option bars, chain cache)."""

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
