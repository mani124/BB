"""Entry signals of the Commodities & Currency book, computed on 5-minute candles of the underlying future.

* Setup 17  range break with trend: the close breaks the prior N-bar high/low while ADX, DI and the 50 EMA agree.
* Setup 18  opening range break: the close breaks the high/low of the first N minutes of the session window.
* Setup 19  band fade in a range: low ADX, a close outside the Bollinger Band with RSI stretched, then the next bar closes
            back inside the band in the reversing direction.

Each signal names the option side to buy (CE for up, PE for down) and an ``invalidate_level`` on the underlying: the
engine exits when the future trades back through it. Signals are read on the last *completed* bar only; the caller
drops the bar still forming.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Optional

import numpy as np
import pandas as pd

from app.services.indicators import calculate_indicators

SETUP_17 = "SETUP_17_RANGE_BREAK"
SETUP_18 = "SETUP_18_OPENING_RANGE"
SETUP_19 = "SETUP_19_BAND_FADE"
SETUP_NAMES = {SETUP_17: "Setup 17 range break", SETUP_18: "Setup 18 opening range", SETUP_19: "Setup 19 band fade"}
MIN_BARS = 60


@dataclass
class CxSignalConfig:
    donchian_len: int = 20
    adx_min: float = 20.0
    orb_minutes: int = 30
    adx_max_fade: float = 22.0
    rsi_low: float = 30.0
    rsi_high: float = 70.0
    s17: bool = True
    s18: bool = True
    s19: bool = True


@dataclass
class CxSignal:
    setup: str
    symbol: str
    side: str                 # "CE" (underlying up) or "PE" (underlying down)
    bar_time: str
    price: float              # close of the signal bar
    invalidate_level: float   # exit when the future trades back through this
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"setup": self.setup, "symbol": self.symbol, "side": self.side, "bar_time": self.bar_time, "price": self.price,
                "invalidate_level": self.invalidate_level, **self.metrics}


def _f(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def prepare(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Indicator frame for the signal functions, or None when there is too little history."""
    if df is None or len(df) < MIN_BARS:
        return None
    ind = calculate_indicators(df.reset_index(drop=True))
    ind["ema_50"] = ind["close"].ewm(span=50, adjust=False).mean()
    ind["sma_20"] = ind["bb_middle"]
    return ind


def setup17(symbol: str, ind: pd.DataFrame, cfg: CxSignalConfig) -> Optional[CxSignal]:
    n = cfg.donchian_len
    if len(ind) < n + 3:
        return None
    last, prev = ind.iloc[-1], ind.iloc[-2]
    hi, lo = ind["high"].iloc[-n - 1:-1].max(), ind["low"].iloc[-n - 1:-1].min()
    p_hi, p_lo = ind["high"].iloc[-n - 2:-2].max(), ind["low"].iloc[-n - 2:-2].min()
    adx, atr = _f(last["adx"]), _f(last["atr"])
    if np.isnan(adx) or np.isnan(atr) or adx < cfg.adx_min:
        return None
    c = _f(last["close"])
    base = {"adx": round(adx, 1), "atr": round(atr, 4), "range_high": hi, "range_low": lo}
    if c > hi and _f(prev["close"]) <= p_hi and _f(last["plus_di"]) > _f(last["minus_di"]) and c > _f(last["ema_50"]):
        return CxSignal(SETUP_17, symbol, "CE", str(last["timestamp"]), c, round(hi - 0.5 * atr, 4), base)
    if c < lo and _f(prev["close"]) >= p_lo and _f(last["minus_di"]) > _f(last["plus_di"]) and c < _f(last["ema_50"]):
        return CxSignal(SETUP_17, symbol, "PE", str(last["timestamp"]), c, round(lo + 0.5 * atr, 4), base)
    return None


def setup18(symbol: str, ind: pd.DataFrame, cfg: CxSignalConfig, window_start: Optional[time]) -> Optional[CxSignal]:
    """``window_start`` is when today's session window opened (09:00, or 17:00 on an MCX evening-only day)."""
    if window_start is None:
        return None
    ts = pd.to_datetime(ind["timestamp"])
    last_day = ts.iloc[-1].date()
    today = ind[ts.dt.date == last_day]
    tt = pd.to_datetime(today["timestamp"])
    start = pd.Timestamp.combine(last_day, window_start)
    end = start + pd.Timedelta(minutes=cfg.orb_minutes)
    orb = today[(tt >= start) & (tt < end)]
    after = today[tt >= end]
    need = cfg.orb_minutes // 5
    if len(orb) < max(1, need - 1) or len(after) < 1:
        return None  # opening range incomplete, or no bar after it yet
    hi, lo = orb["high"].max(), orb["low"].min()
    if hi <= lo:
        return None
    c = _f(after["close"].iloc[-1])
    prior = after["close"].iloc[:-1]
    # fire on the first bar that closes beyond the range, not on every later bar
    if c > hi and not (prior > hi).any() and not (prior < lo).any():
        return CxSignal(SETUP_18, symbol, "CE", str(after["timestamp"].iloc[-1]), c, round((hi + lo) / 2, 4),
                        {"orb_high": hi, "orb_low": lo})
    if c < lo and not (prior < lo).any() and not (prior > hi).any():
        return CxSignal(SETUP_18, symbol, "PE", str(after["timestamp"].iloc[-1]), c, round((hi + lo) / 2, 4),
                        {"orb_high": hi, "orb_low": lo})
    return None


def setup19(symbol: str, ind: pd.DataFrame, cfg: CxSignalConfig) -> Optional[CxSignal]:
    if len(ind) < 3:
        return None
    stretch, last = ind.iloc[-2], ind.iloc[-1]
    adx, rsi = _f(stretch["adx"]), _f(stretch["rsi"])
    if np.isnan(adx) or np.isnan(rsi) or adx > cfg.adx_max_fade:
        return None
    c0, c1 = _f(stretch["close"]), _f(last["close"])
    base = {"adx": round(adx, 1), "rsi": round(rsi, 1), "sma_20": _f(last["sma_20"])}
    if c0 < _f(stretch["bb_lower"]) and rsi <= cfg.rsi_low and c1 > _f(last["bb_lower"]) and c1 > _f(last["open"]):
        return CxSignal(SETUP_19, symbol, "CE", str(last["timestamp"]), c1, _f(stretch["low"]), base)
    if c0 > _f(stretch["bb_upper"]) and rsi >= cfg.rsi_high and c1 < _f(last["bb_upper"]) and c1 < _f(last["open"]):
        return CxSignal(SETUP_19, symbol, "PE", str(last["timestamp"]), c1, _f(stretch["high"]), base)
    return None


def evaluate(symbol: str, df: pd.DataFrame, cfg: CxSignalConfig, window_start: Optional[time] = None) -> list[CxSignal]:
    """Signals on the last completed bar of ``df`` (columns timestamp, open, high, low, close, volume)."""
    ind = prepare(df)
    if ind is None:
        return []
    out = []
    if cfg.s17 and (s := setup17(symbol, ind, cfg)):
        out.append(s)
    if cfg.s18 and (s := setup18(symbol, ind, cfg, window_start)):
        out.append(s)
    if cfg.s19 and (s := setup19(symbol, ind, cfg)):
        out.append(s)
    return out
