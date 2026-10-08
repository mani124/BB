import enum
from datetime import datetime
from typing import Literal
from pydantic import BaseModel
import pandas as pd
from app.services.strike_selector import recommend_strike, OptionStrikeRecommendation

class SetupType(str, enum.Enum):
    SETUP_1_SQUEEZE = "Setup 1: BB Squeeze Breakout"
    SETUP_2_WALKING = "Setup 2: Walking the Bands (9 EMA)"
    SETUP_3_REVERSAL = "Setup 3: W/M Reversal"
    SETUP_4_ORB = "Setup 4: 9:30 AM Opening Range Breakout"

class Signal(BaseModel):
    id: str
    symbol: str
    timeframe: str
    setup_type: SetupType
    option_type: Literal["CE", "PE"]
    timestamp: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    strike_recommendation: OptionStrikeRecommendation
    indicators_snapshot: dict[str, float]
    rationale: str

def evaluate_signals(symbol: str, df: pd.DataFrame, timeframe: str = "5m") -> list[Signal]:
    """
    Evaluate all 4 Bollinger Band setups across recent candles for both CE and PE.
    Returns list of active signals.
    """
    signals: list[Signal] = []
    if df.empty or len(df) < 20:
        return signals

    last_idx = len(df) - 1
    curr = df.iloc[last_idx]
    prev = df.iloc[last_idx - 1]

    # Current snapshot
    snap = {
        "close": round(float(curr.get("close", 0.0)), 2),
        "bb_upper": round(float(curr.get("bb_upper", 0.0)), 2),
        "bb_middle": round(float(curr.get("bb_middle", 0.0)), 2),
        "bb_lower": round(float(curr.get("bb_lower", 0.0)), 2),
        "bandwidth": round(float(curr.get("bandwidth", 0.0)), 2),
        "percent_b": round(float(curr.get("percent_b", 0.0)), 2),
        "vwap": round(float(curr.get("vwap", 0.0)), 2),
        "rsi": round(float(curr.get("rsi", 50.0)), 2),
        "ema_9": round(float(curr.get("ema_9", 0.0)), 2),
        "adx": round(float(curr.get("adx", 20.0)), 2),
    }

    ts_raw = curr.get("timestamp", last_idx)
    ts_str = str(ts_raw)
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")

    close = curr["close"]
    upper = curr["bb_upper"]
    lower = curr["bb_lower"]
    mid = curr["bb_middle"]
    vwap = curr["vwap"]
    rsi = curr["rsi"]
    bw = curr["bandwidth"]
    bw_min = curr.get("bandwidth_20_min", bw)
    ema_9 = curr["ema_9"]
    adx = curr["adx"]

    # =========================================================================
    # SETUP 1: Volatility Squeeze & Expansion Breakout
    # =========================================================================
    # Squeeze condition: BandWidth was recently at or near 20-period minimum
    if bw_min <= 0.0001:
        is_squeeze = bw <= 5.0 or prev["bandwidth"] <= 5.0
    else:
        is_squeeze = prev["bandwidth"] <= bw_min * 1.3 or bw <= bw_min * 1.3

    if is_squeeze:
        # CE Squeeze Breakout: Close > Upper Band, Close > VWAP, RSI > 60
        if close > upper and close > vwap and rsi >= 58.0:
            sl = round(max(mid, curr["low"] - 2.0), 2)
            strike_rec = recommend_strike(symbol, close, "CE", sl)
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S1_CE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_1_SQUEEZE,
                option_type="CE",
                timestamp=ts_str,
                entry_price=round(close, 2),
                stop_loss=sl,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Squeeze expansion above Upper BB with VWAP & RSI confirmation"
            ))

        # PE Squeeze Breakdown: Close < Lower Band, Close < VWAP, RSI < 42
        elif close < lower and close < vwap and rsi <= 42.0:
            sl = round(min(mid, curr["high"] + 2.0), 2)
            strike_rec = recommend_strike(symbol, close, "PE", sl)
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S1_PE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_1_SQUEEZE,
                option_type="PE",
                timestamp=ts_str,
                entry_price=round(close, 2),
                stop_loss=sl,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Squeeze breakdown below Lower BB with VWAP & RSI confirmation"
            ))

    # =========================================================================
    # SETUP 2: Walking the Bands with 9 EMA
    # =========================================================================
    if len(df) >= 22 and adx >= 23.0:
        prev2 = df.iloc[last_idx - 2]
        # CE Walking: Prior 2 candles had strong closes near or above upper band
        prior_bull = (prev["close"] >= prev["bb_upper"] * 0.998) or (prev2["close"] >= prev2["bb_upper"] * 0.998)
        if prior_bull and ema_9 > mid and close > ema_9:
            # Low retested near 9 EMA and closed green
            if curr["low"] <= ema_9 * 1.004 and curr["close"] >= curr["open"]:
                sl = round(ema_9 - (curr["high"] - curr["low"]) * 0.3, 2)
                strike_rec = recommend_strike(symbol, close, "CE", sl)
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S2_CE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_2_WALKING,
                    option_type="CE",
                    timestamp=ts_str,
                    entry_price=round(close, 2),
                    stop_loss=sl,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Bullish momentum trend riding Upper Band with 9 EMA support bounce"
                ))

        # PE Walking: Prior 2 candles had strong closes near or below lower band
        prior_bear = (prev["close"] <= prev["bb_lower"] * 1.002) or (prev2["close"] <= prev2["bb_lower"] * 1.002)
        if prior_bear and ema_9 < mid and close < ema_9:
            # High retested near 9 EMA and closed red
            if curr["high"] >= ema_9 * 0.996 and curr["close"] <= curr["open"]:
                sl = round(ema_9 + (curr["high"] - curr["low"]) * 0.3, 2)
                strike_rec = recommend_strike(symbol, close, "PE", sl)
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S2_PE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_2_WALKING,
                    option_type="PE",
                    timestamp=ts_str,
                    entry_price=round(close, 2),
                    stop_loss=sl,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Bearish momentum trend riding Lower Band with 9 EMA resistance rejection"
                ))

    # =========================================================================
    # SETUP 3: W-Bottom (CE) & M-Top (PE) Reversals
    # =========================================================================
    if len(df) >= 15:
        # Search backward for trough 1 and trough 2 (W-bottom)
        recent_window = df.iloc[-12:]
        # W-Bottom:
        # Look for a trough outside lower band, intermediate bounce, second trough inside lower band
        min1_idx = recent_window["low"].iloc[:6].idxmin()
        min2_idx = recent_window["low"].iloc[6:].idxmin()
        if min1_idx != min2_idx and min2_idx > min1_idx:
            row_min1 = df.loc[min1_idx]
            row_min2 = df.loc[min2_idx]
            # Low 1 was outside lower band
            if row_min1["low"] < row_min1["bb_lower"]:
                # Low 2 was strictly inside lower band
                if row_min2["close"] > row_min2["bb_lower"] and row_min2["rsi"] > row_min1["rsi"]:
                    # Neckline is max high between the two troughs
                    neckline = df.loc[min1_idx:min2_idx, "high"].max()
                    if close > neckline and prev["close"] <= neckline:
                        sl = round(min(row_min1["low"], row_min2["low"]) - 1.0, 2)
                        strike_rec = recommend_strike(symbol, close, "CE", sl)
                        signals.append(Signal(
                            id=f"{symbol}_{timeframe}_S3_CE_{ts_clean}",
                            symbol=symbol,
                            timeframe=timeframe,
                            setup_type=SetupType.SETUP_3_REVERSAL,
                            option_type="CE",
                            timestamp=ts_str,
                            entry_price=round(close, 2),
                            stop_loss=sl,
                            target_1=strike_rec.target_1,
                            target_2=strike_rec.target_2,
                            strike_recommendation=strike_rec,
                            indicators_snapshot=snap,
                            rationale="Bollinger W-Bottom reversal with Bullish RSI Divergence breaking neckline"
                        ))

        # M-Top:
        max1_idx = recent_window["high"].iloc[:6].idxmax()
        max2_idx = recent_window["high"].iloc[6:].idxmax()
        if max1_idx != max2_idx and max2_idx > max1_idx:
            row_max1 = df.loc[max1_idx]
            row_max2 = df.loc[max2_idx]
            # High 1 was outside upper band
            if row_max1["high"] > row_max1["bb_upper"]:
                # High 2 was inside upper band
                if row_max2["close"] < row_max2["bb_upper"] and row_max2["rsi"] < row_max1["rsi"]:
                    # Neckline is min low between the two peaks
                    neckline = df.loc[max1_idx:max2_idx, "low"].min()
                    if close < neckline and prev["close"] >= neckline:
                        sl = round(max(row_max1["high"], row_max2["high"]) + 1.0, 2)
                        strike_rec = recommend_strike(symbol, close, "PE", sl)
                        signals.append(Signal(
                            id=f"{symbol}_{timeframe}_S3_PE_{ts_clean}",
                            symbol=symbol,
                            timeframe=timeframe,
                            setup_type=SetupType.SETUP_3_REVERSAL,
                            option_type="PE",
                            timestamp=ts_str,
                            entry_price=round(close, 2),
                            stop_loss=sl,
                            target_1=strike_rec.target_1,
                            target_2=strike_rec.target_2,
                            strike_recommendation=strike_rec,
                            indicators_snapshot=snap,
                            rationale="Bollinger M-Top reversal with Bearish RSI Divergence breaking neckline"
                        ))

    # =========================================================================
    # SETUP 4: 9:30 AM Opening Range Breakout (ORB)
    # =========================================================================
    or_high = curr.get("or_high")
    or_low = curr.get("or_low")

    # Active strictly during the morning breakout window (09:30 - 11:30 AM IST)
    is_orb_time = True
    if isinstance(ts_raw, (pd.Timestamp, datetime)):
        bar_t = ts_raw.time()
        is_orb_time = (bar_t >= pd.to_datetime("09:30:00").time()) and (bar_t <= pd.to_datetime("11:30:00").time())

    if is_orb_time and or_high is not None and or_low is not None:
        # CE ORB: Breaks above OR High, Above Upper BB, Above VWAP
        if close > or_high and close > upper and close > vwap:
            sl = round(max(mid, or_high * 0.997), 2)
            strike_rec = recommend_strike(symbol, close, "CE", sl)
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S4_CE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_4_ORB,
                option_type="CE",
                timestamp=ts_str,
                entry_price=round(close, 2),
                stop_loss=sl,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="9:30 AM Opening Range Breakout above Upper Band and VWAP"
            ))

        # PE ORB: Breaks below OR Low, Below Lower BB, Below VWAP
        elif close < or_low and close < lower and close < vwap:
            sl = round(min(mid, or_low * 1.003), 2)
            strike_rec = recommend_strike(symbol, close, "PE", sl)
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S4_PE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_4_ORB,
                option_type="PE",
                timestamp=ts_str,
                entry_price=round(close, 2),
                stop_loss=sl,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="9:30 AM Opening Range Breakdown below Lower Band and VWAP"
            ))

    return signals
