"""After-close watchlist for Setup 16 (option squeeze breakout).

After the close the F&O stocks are screened on their own daily charts for a squeeze: Bollinger BandWidth (20, 2)
of the daily closes in the lowest part of its last 120 days, or a narrow-range day (NR7: the day's high-low range is
the smallest of the last seven). The most liquid qualifiers become the next trading day's watchlist. The scanner
checks those stocks for Setup 16 only (the other setups keep their usual universe). Watchlist membership never
opens a trade; the setup rules and the per-setup switch still decide.

The screen is a hypothesis (a daily squeeze improving next-day option breakouts is untested here). Every number is a
runtime setting (``watchlist_*``).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd

from app.services import market_hours

logger = logging.getLogger(__name__)

BB_WINDOW = 20
HISTORY_BARS = 120
MIN_BARS = 60
NR_DAYS = 7
AVG_VALUE_DAYS = 20
CRORE = 1e7


@dataclass
class Candidate:
    symbol: str
    bw_percentile: float      # latest daily BandWidth's rank among the last 120 days (0 = tightest)
    bandwidth: float
    nr7: bool
    avg_value_cr: float       # 20-day average traded value, INR crore (liquidity proxy for the stock's options)
    reasons: list[str]


def screen_symbol(symbol: str, bars: pd.DataFrame, bw_percentile_max: float = 20.0, use_nr7: bool = True,
                  min_avg_value_cr: float = 50.0) -> Optional[Candidate]:
    """One stock's daily bars (columns date, open, high, low, close, volume) -> a Candidate, or None when it does not qualify."""
    if bars is None or len(bars) < MIN_BARS or not {"high", "low", "close", "volume"}.issubset(bars.columns):
        return None
    df = bars.tail(HISTORY_BARS + BB_WINDOW).reset_index(drop=True)
    close = df["close"].astype(float)
    mid = close.rolling(BB_WINDOW).mean()
    sd = close.rolling(BB_WINDOW).std(ddof=0)
    bw = (4.0 * sd / mid.where(mid > 0) * 100.0).dropna().tail(HISTORY_BARS)
    if len(bw) < 30:
        return None
    latest = float(bw.iloc[-1])
    pct = float((bw <= latest).sum()) / len(bw) * 100.0
    rng = (df["high"].astype(float) - df["low"].astype(float)).tail(NR_DAYS)
    nr7 = bool(len(rng) == NR_DAYS and float(rng.iloc[-1]) <= float(rng.min()) and float(rng.iloc[-1]) > 0)
    value = (df["close"].astype(float) * df["volume"].astype(float)).tail(AVG_VALUE_DAYS).mean()
    avg_cr = float(value) / CRORE if pd.notna(value) else 0.0
    if avg_cr < min_avg_value_cr:
        return None
    reasons = []
    if pct <= bw_percentile_max:
        reasons.append(f"BandWidth in lowest {pct:.0f}% of last {len(bw)} days")
    if use_nr7 and nr7:
        reasons.append("NR7 (narrowest range of 7 days)")
    if not reasons:
        return None
    return Candidate(symbol=symbol, bw_percentile=round(pct, 1), bandwidth=round(latest, 2), nr7=nr7,
                     avg_value_cr=round(avg_cr, 1), reasons=reasons)


def screen(bars_by_symbol: dict[str, pd.DataFrame], size: int = 40, bw_percentile_max: float = 20.0,
           use_nr7: bool = True, min_avg_value_cr: float = 50.0) -> list[Candidate]:
    """Qualifying stocks, tightest squeeze first (a narrow-range day counts as tightest when BandWidth ties), top ``size``."""
    out = []
    for sym, df in bars_by_symbol.items():
        try:
            c = screen_symbol(sym, df, bw_percentile_max, use_nr7, min_avg_value_cr)
        except Exception:
            logger.warning("watchlist screen failed for %s", sym, exc_info=True)
            c = None
        if c:
            out.append(c)
    out.sort(key=lambda c: (c.bw_percentile, -c.avg_value_cr, c.symbol))
    return out[:max(0, int(size))]


def next_trading_day(after: date) -> date:
    d = after + timedelta(days=1)
    for _ in range(14):
        if market_hours.is_trading_day(d):
            return d
        d += timedelta(days=1)
    return after + timedelta(days=1)


class WatchlistStore:
    """The latest watchlist as a small JSON file next to the databases."""

    def __init__(self, path: Optional[str]):
        self.path = path
        self._mem: Optional[dict] = None
        self._lock = threading.Lock()

    def load(self) -> Optional[dict]:
        with self._lock:
            if not self.path:
                return self._mem
            try:
                with open(self.path) as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None

    def save(self, data: dict) -> None:
        with self._lock:
            if not self.path:
                self._mem = data
                return
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".", suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)


def _hhmm_minutes(s: str) -> int:
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


class WatchlistService:
    def __init__(self, store: WatchlistStore, runtime: Any, provider: Any = None):
        self.store = store
        self.runtime = runtime
        self.provider = provider
        self.last_cycle: dict = {}

    def symbols_for(self, today: Optional[date] = None) -> list[str]:
        """Symbols to check for Setup 16 today: the list built for exactly this trading day, else nothing (a stale list is never reused)."""
        if not self.runtime.get("watchlist_enabled"):
            return []
        data = self.store.load()
        today = today or market_hours.now_ist().date()
        if not data or data.get("built_for") != today.isoformat():
            return []
        return [c["symbol"] for c in data.get("candidates", [])]

    def current(self) -> dict:
        data = self.store.load() or {}
        return {"enabled": bool(self.runtime.get("watchlist_enabled")), **data, "last_cycle": self.last_cycle}

    async def build(self, today: date) -> dict:
        symbols = self.provider.symbols()
        bars = await self.provider.bars(symbols, today)
        cands = screen(
            bars,
            size=int(self.runtime.get("watchlist_size")),
            bw_percentile_max=float(self.runtime.get("watchlist_bw_percentile")),
            use_nr7=bool(self.runtime.get("watchlist_use_nr7")),
            min_avg_value_cr=float(self.runtime.get("watchlist_min_avg_value_cr")),
        )
        last_bar = max((str(df["date"].iloc[-1])[:10] for df in bars.values() if len(df)), default=None)
        data = {
            "built_for": next_trading_day(today).isoformat(),
            "built_on": today.isoformat(),
            "built_at": market_hours.now_ist().isoformat(timespec="seconds"),
            "last_bar_day": last_bar,
            "screened": len(bars),
            "candidates": [asdict(c) for c in cands],
        }
        self.store.save(data)
        return data

    async def run_cycle(self, now: Optional[datetime] = None) -> dict:
        """After the build time on a trading day, build tomorrow's list once."""
        now = now or market_hours.now_ist()
        today = now.date()
        result: dict = {"at": now.isoformat(), "status": "ok"}
        try:
            if not self.runtime.get("watchlist_enabled"):
                result["status"] = "disabled"
            elif self.provider is None or not self.provider.has_credentials():
                result["status"] = "no_credentials"
            elif not market_hours.is_trading_day(today):
                result["status"] = "not_a_trading_day"
            elif now.hour * 60 + now.minute < _hhmm_minutes(self.runtime.get("watchlist_build_time")):
                result["status"] = "before_build_time"
            elif (self.store.load() or {}).get("built_on") == today.isoformat():
                result["status"] = "up_to_date"
            else:
                data = await self.build(today)
                result["status"] = "built"
                result["candidates"] = len(data["candidates"])
        except Exception as exc:
            logger.warning("watchlist cycle failed: %s", exc, exc_info=True)
            result["status"] = "error"
            result["error"] = str(exc)
        self.last_cycle = result
        return result

    async def poll_loop(self) -> None:
        import asyncio
        while True:
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("watchlist poll failed", exc_info=True)
            await asyncio.sleep(600)
