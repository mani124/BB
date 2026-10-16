"""Setup 12: ADX + EMA 20 Trend Cross (from the "Trinity ADX + EMA Scalper" Pine script).

Evaluated only on completed 5m index-or-stock spot bars (the caller passes closed history), so every
signal is a confirmed candle close. The ADX filter is always on. See docs/SETUPS_SPECIFICATION.md
section 15.
"""
from datetime import time as dtime

import pandas as pd

from app.services.strategy_engine import Signal, SetupType, _session_bars
from app.services.strike_selector import recommend_strike

EMA_PERIOD = 20
ADX_MIN = 20.0            # Pine "strong trend" level
ADX_RISING_BARS = 3       # ADX must be above its value this many bars back
MIN_DIST_ATR = 0.1        # close must clear the EMA by this many ATRs (drops marginal crosses)
MAX_DIST_ATR = 1.0        # ...but not by more than this (no chasing)
MIN_HISTORY_BARS = 30       # ADX (Wilder 14) is filled with a neutral 20.0 until about 28 bars exist
MIN_SESSION_BARS = 20     # first entry about 10:55 IST
WINDOW_END = dtime(14, 25)  # bar start; a 14:25 bar confirms at 14:30

REQUIRED = {"timestamp", "open", "high", "low", "close", "atr", "adx", "plus_di", "minus_di"}


def evaluate_adx_ema_cross(symbol: str, df: pd.DataFrame, timeframe: str = "5m") -> list[Signal]:
    """`df` is completed bars with indicators (needs atr, adx, plus_di, minus_di). At most one signal."""
    if df is None or df.empty or len(df) < MIN_HISTORY_BARS or timeframe != "5m" or not REQUIRED.issubset(df.columns):
        return []
    last_ts = pd.to_datetime(df["timestamp"].iloc[-1])
    if last_ts.time() > WINDOW_END or _session_bars(df) < MIN_SESSION_BARS:
        return []

    close_s = df["close"].astype(float)
    ema_s = close_s.ewm(span=EMA_PERIOD, adjust=False).mean()
    t = len(df) - 1
    curr, prev = df.iloc[t], df.iloc[t - 1]
    close, prev_close = float(close_s.iloc[t]), float(close_s.iloc[t - 1])
    ema, prev_ema = float(ema_s.iloc[t]), float(ema_s.iloc[t - 1])
    adx, adx_back = float(curr["adx"]), float(df["adx"].iloc[t - ADX_RISING_BARS])
    plus_di, minus_di = float(curr["plus_di"]), float(curr["minus_di"])
    atr = float(curr["atr"] or 0.0)
    high, low = float(curr["high"]), float(curr["low"])
    if close <= 0 or atr <= 0 or any(pd.isna(v) for v in (adx, adx_back, plus_di, minus_di, ema, prev_ema)):
        return []
    if adx < ADX_MIN or adx <= adx_back:
        return []

    if prev_close <= prev_ema and close > ema and close > prev_close and plus_di > minus_di:
        side, dist = "CE", close - ema
    elif prev_close >= prev_ema and close < ema and close < prev_close and minus_di > plus_di:
        side, dist = "PE", ema - close
    else:
        return []
    if not (MIN_DIST_ATR * atr <= dist <= MAX_DIST_ATR * atr):
        return []

    bar_range = high - low
    buf = max(bar_range * 0.25, close * 0.0005)
    sl = round(min(ema, low) - buf, 2) if side == "CE" else round(max(ema, high) + buf, 2)
    strike_rec = recommend_strike(symbol, close, side, sl)
    ts_str = str(curr["timestamp"])
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    snap = {
        "close": round(close, 2),
        "ema_20": round(ema, 2),
        "adx": round(adx, 2),
        "adx_3_bars_ago": round(adx_back, 2),
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
        "ema_dist_atr": round(dist / atr, 2),
    }
    word = "above" if side == "CE" else "below"
    return [Signal(
        id=f"{symbol}_{timeframe}_S12_{side}_{ts_clean}",
        symbol=symbol,
        timeframe=timeframe,
        setup_type=SetupType.SETUP_12_ADX_EMA_CROSS,
        option_type=side,
        timestamp=ts_str,
        entry_price=round(close, 2),
        stop_loss=strike_rec.stop_loss,
        target_1=strike_rec.target_1,
        target_2=strike_rec.target_2,
        strike_recommendation=strike_rec,
        indicators_snapshot=snap,
        rationale=f"Close crossed {word} the 20 EMA with ADX {adx:.0f} rising and DI aligned",
        is_confirmed=True,
    )]
