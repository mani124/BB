"""Setup 20: T315, the EMA 3 / EMA 15 crossover on the index chart.

The cross is read on completed 5m INDEX spot bars only, so every signal is a confirmed candle close. The
option is only the instrument bought afterwards (1 strike ITM, from `recommend_strike`); no indicator is
applied to the option chart. The stop is an index level, and the paper engine already exits when spot
reaches `underlying_sl`. Open T315 positions are closed at 3:15 PM (see `market_hours.is_t315_cutoff_due`).
See docs/SETUPS_SPECIFICATION.md section 17.
"""
from datetime import time as dtime

import pandas as pd

from app.services.strategy_engine import INDEX_SYMBOLS, SetupType, Signal
from app.services.strike_selector import recommend_strike

FAST_EMA = 3
SLOW_EMA = 15
TREND_EMA = 50            # the optional trend filter, always on here
MIN_HISTORY_BARS = 50     # enough bars for the 50 EMA to be meaningful
WINDOW_START = dtime(9, 30)   # bar start; the 9:15-9:25 bars are too noisy for a 3/15 cross
WINDOW_END = dtime(15, 5)     # bar start; a 15:05 bar confirms at 15:10, before the 3:15 PM cutoff

REQUIRED = {"timestamp", "open", "high", "low", "close"}


def evaluate_t315(symbol: str, df: pd.DataFrame, timeframe: str = "5m") -> list[Signal]:
    """`df` is completed bars. At most one signal: the bar on which the 3 EMA crosses the 15 EMA."""
    if symbol.upper() not in INDEX_SYMBOLS or timeframe != "5m":
        return []
    if df is None or df.empty or len(df) < MIN_HISTORY_BARS or not REQUIRED.issubset(df.columns):
        return []
    last_ts = pd.to_datetime(df["timestamp"].iloc[-1])
    if not (WINDOW_START <= last_ts.time() <= WINDOW_END):
        return []

    close_s = df["close"].astype(float)
    fast = close_s.ewm(span=FAST_EMA, adjust=False).mean()
    slow = close_s.ewm(span=SLOW_EMA, adjust=False).mean()
    trend = close_s.ewm(span=TREND_EMA, adjust=False).mean()
    t = len(df) - 1
    f, s, f0, s0 = float(fast.iloc[t]), float(slow.iloc[t]), float(fast.iloc[t - 1]), float(slow.iloc[t - 1])
    close, trend_now = float(close_s.iloc[t]), float(trend.iloc[t])
    if close <= 0 or any(pd.isna(v) for v in (f, s, f0, s0, trend_now)):
        return []

    # Cross on this bar only (`ta.crossover` semantics), and only in the direction of the 50 EMA.
    if f0 <= s0 and f > s and close > trend_now:
        side = "CE"
    elif f0 >= s0 and f < s and close < trend_now:
        side = "PE"
    else:
        return []

    curr = df.iloc[t]
    high, low = float(curr["high"]), float(curr["low"])
    buf = max((high - low) * 0.25, close * 0.0005)
    sl = round(min(s, low) - buf, 2) if side == "CE" else round(max(s, high) + buf, 2)
    strike_rec = recommend_strike(symbol, close, side, sl)
    ts_str = str(curr["timestamp"])
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    word = "above" if side == "CE" else "below"
    return [Signal(
        id=f"{symbol}_{timeframe}_T315_{side}_{ts_clean}",
        symbol=symbol,
        timeframe=timeframe,
        setup_type=SetupType.SETUP_20_T315,
        option_type=side,
        timestamp=ts_str,
        entry_price=round(close, 2),
        stop_loss=strike_rec.stop_loss,
        target_1=strike_rec.target_1,
        target_2=strike_rec.target_2,
        strike_recommendation=strike_rec,
        indicators_snapshot={
            "close": round(close, 2),
            "ema_3": round(f, 2),
            "ema_15": round(s, 2),
            "ema_50": round(trend_now, 2),
            "ema_gap": round(abs(f - s), 2),
        },
        rationale=f"3 EMA crossed {word} the 15 EMA on the index, {word} the 50 EMA",
        is_confirmed=True,
    )]
