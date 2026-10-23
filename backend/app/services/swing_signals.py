"""Daily-bar swing signals (Setup 15: ATR trend flip). Pure functions on a daily OHLCV frame, no I/O.

The intraday indicators in ``indicators.py`` carry session VWAP and opening-range logic that has no meaning on daily
bars, so the Supertrend and the filters live here. A signal is read from the *last completed* daily bar only; the engine
fills it at the next open, so nothing here may look past the last row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from app.services.indicators import _wilder

SETUP_15 = "Setup 15: ATR Trend Flip"
SUPERTREND_WINDOW = 200  # bars fed to the Supertrend: caps the cost of a daily scan and keeps live and replay identical


@dataclass(frozen=True)
class Setup15Config:
    atr_period: int = 3
    atr_mult: float = 1.0
    sma_filter_days: int = 200      # 0 disables the long-term trend filter
    min_price: float = 50.0
    min_avg_volume: float = 100_000.0
    volume_window: int = 20
    rank_return_days: int = 63      # tie-break when more flips than free slots

    def min_bars(self) -> int:
        return max(self.atr_period + 3, self.sma_filter_days, self.volume_window, self.rank_return_days + 1, 30)


@dataclass(frozen=True)
class Setup15Signal:
    symbol: str
    day: str            # date of the bar the flip printed on
    close: float
    stop: float         # Supertrend line on that bar: the initial protective stop
    atr: float
    rank_return: float  # return over `rank_return_days`, used only to order candidates
    avg_volume: float

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "day": self.day, "close": self.close, "stop": self.stop, "atr": self.atr,
                "rank_return": self.rank_return, "avg_volume": self.avg_volume}


def supertrend(df: pd.DataFrame, period: int, mult: float) -> pd.DataFrame:
    """Supertrend on high/low/close. Returns ``line`` (the active band) and ``trend`` (+1 up, -1 down).

    Same recursion as the common Pine ``ta.supertrend``: bands only ratchet toward price while the previous close stays
    on their side, the trend flips when the close crosses the opposite band. ATR is Wilder-smoothed, so the first
    ``period`` bars have no value (trend stays 0 there)."""
    n = len(df)
    out = pd.DataFrame({"line": np.nan, "trend": 0}, index=df.index)
    if n <= period + 1 or period < 1:
        return out
    high, low, close = (df[c].astype("float64").to_numpy() for c in ("high", "low", "close"))
    prev_close = np.concatenate([[np.nan], close[:-1]])
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev_close), np.abs(low - prev_close)]), axis=0)
    tr[0] = high[0] - low[0]
    atr = _wilder(pd.Series(tr), period=period, first_valid=0).to_numpy()
    hl2 = (high + low) / 2.0
    up = (hl2 - mult * atr).tolist()   # lower band, the stop while the trend is up
    dn = (hl2 + mult * atr).tolist()   # upper band, the stop while the trend is down
    close = close.tolist()             # plain floats: the loop below is the hot path of a backtest
    trend = [0] * n
    line = [float("nan")] * n
    start = period  # first bar with an ATR value
    trend[start] = 1
    line[start] = up[start]
    for i in range(start + 1, n):
        up1, dn1 = up[i - 1], dn[i - 1]  # previous *final* bands
        if close[i - 1] > up1:
            up[i] = max(up[i], up1)
        if close[i - 1] < dn1:
            dn[i] = min(dn[i], dn1)
        if trend[i - 1] == -1 and close[i] > dn1:
            trend[i] = 1
        elif trend[i - 1] == 1 and close[i] < up1:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
        line[i] = up[i] if trend[i] == 1 else dn[i]
    out["line"] = line
    out["trend"] = trend
    return out


def evaluate_setup15(symbol: str, df: pd.DataFrame, cfg: Setup15Config = Setup15Config()) -> Optional[Setup15Signal]:
    """A long entry signal if the *last* bar of ``df`` flipped the Supertrend from down to up and passes the filters.

    ``df`` needs columns date, open, high, low, close, volume, oldest first, ending on the bar being evaluated."""
    if df is None or len(df) < cfg.min_bars():
        return None
    st = supertrend(df.tail(SUPERTREND_WINDOW), cfg.atr_period, cfg.atr_mult)
    if int(st["trend"].iloc[-1]) != 1 or int(st["trend"].iloc[-2]) != -1:
        return None
    close = float(df["close"].iloc[-1])
    stop = float(st["line"].iloc[-1])
    if not (close > 0 and 0 < stop < close):
        return None
    if close < cfg.min_price:
        return None
    avg_vol = float(df["volume"].tail(cfg.volume_window).mean())
    if avg_vol < cfg.min_avg_volume:
        return None
    if cfg.sma_filter_days > 0 and close <= float(df["close"].tail(cfg.sma_filter_days).mean()):
        return None
    past = float(df["close"].iloc[-1 - cfg.rank_return_days])
    atr_now = float((df["high"] - df["low"]).tail(cfg.atr_period).mean())
    return Setup15Signal(symbol=symbol, day=str(df["date"].iloc[-1])[:10], close=close, stop=stop, atr=round(atr_now, 4),
                         rank_return=round(close / past - 1.0, 4) if past > 0 else 0.0, avg_volume=round(avg_vol, 0))


def trend_state(df: pd.DataFrame, cfg: Setup15Config = Setup15Config()) -> tuple[int, float]:
    """(trend, line) on the last bar: used to trail the stop of an open position and to spot a flip back down."""
    st = supertrend(df.tail(SUPERTREND_WINDOW), cfg.atr_period, cfg.atr_mult)
    return int(st["trend"].iloc[-1]), float(st["line"].iloc[-1]) if pd.notna(st["line"].iloc[-1]) else float("nan")
