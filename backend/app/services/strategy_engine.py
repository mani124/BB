import enum
from datetime import datetime
from typing import Literal
from pydantic import BaseModel
import pandas as pd
from app.core.config import settings
from app.services.strike_selector import recommend_strike, OptionStrikeRecommendation

class SetupType(str, enum.Enum):
    SETUP_1_SQUEEZE = "Setup 1: BB Squeeze Breakout"
    SETUP_2_WALKING = "Setup 2: Walking the Bands (9 EMA)"
    SETUP_3_REVERSAL = "Setup 3: W/M Reversal"
    SETUP_4_ORB = "Setup 4: 9:30 AM Opening Range Breakout"
    SETUP_5_OPTION_BB = "Setup 5: Option Chart BB Scalp"
    SETUP_6_PINBAR_SNAPBACK = "Setup 6: Pin Bar Exhaustion Snapback"
    SETUP_7_INSIDE_BAR_SNAPBACK = "Setup 7: 2.5σ Puncture & Inside Bar"
    SETUP_8_DIVERGENCE_SNAPBACK = "Setup 8: Climax Swing Divergence Fade"
    SETUP_9_RELATIVE_STRENGTH = "Setup 9: Relative Strength vs NIFTY (9 EMA Pullback)"

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
    is_confirmed: bool = True

# Setup 3 geometry: leg 1 is 5-20 bars back, leg 2 within the last 5 bars, at least 3 bars apart.
S3_LEG1_MIN_AGE, S3_LEG1_MAX_AGE = 5, 20
S3_LEG2_MAX_AGE = 5
S3_MIN_LEG_GAP = 3
S3_RSI_MARGIN = 1.5
S3_SL_ATR_BUFFER = 0.1  # stop sits this many ATRs beyond leg 2
S3_ATR_TOLERANCE = 0.25  # leg 2 may undercut (W) / overshoot (M) leg 1 by at most this many ATRs


def _recent_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Mean true range of the last `period` bars (price units)."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return float(tr.iloc[-period:].mean())


def _reversal_legs(df: pd.DataFrame, bullish: bool):
    """Find a Setup 3 double bottom (bullish) or double top (bearish).

    Returns (leg1_row, leg2_row, neckline) or None. Leg 1 pierces the outer band; leg 2 holds
    inside the band at a higher (W) / lower (M) extreme within an ATR tolerance, with RSI divergence
    of at least S3_RSI_MARGIN. The neckline is the best opposite extreme between the legs.
    """
    n = len(df)
    last = n - 1
    if n < 15:
        return None
    lo1 = max(0, last - S3_LEG1_MAX_AGE)
    hi1 = last - S3_LEG1_MIN_AGE
    lo2 = max(0, last - S3_LEG2_MAX_AGE)
    if hi1 < lo1:
        return None
    w1 = df.iloc[lo1:hi1 + 1]
    w2 = df.iloc[lo2:last]  # excludes the trigger bar
    if w1.empty or w2.empty:
        return None
    atr = _recent_atr(df)
    tol = S3_ATR_TOLERANCE * atr
    if bullish:
        pierce = w1[w1["low"] <= w1["bb_lower"]]
        if pierce.empty:
            return None
        i1 = pierce["low"].idxmin()
        w2b = w2.loc[i1 + S3_MIN_LEG_GAP:]
        if w2b.empty:
            return None
        i2 = w2b["low"].idxmin()
        r1, r2 = df.loc[i1], df.loc[i2]
        if r2["low"] < r1["low"] - tol or r2["low"] <= r2["bb_lower"]:
            return None
        if not r2["rsi"] > r1["rsi"] + S3_RSI_MARGIN:
            return None
        return r1, r2, float(df.loc[i1:i2, "high"].max())
    pierce = w1[w1["high"] >= w1["bb_upper"]]
    if pierce.empty:
        return None
    i1 = pierce["high"].idxmax()
    w2b = w2.loc[i1 + S3_MIN_LEG_GAP:]
    if w2b.empty:
        return None
    i2 = w2b["high"].idxmax()
    r1, r2 = df.loc[i1], df.loc[i2]
    if r2["high"] > r1["high"] + tol or r2["high"] >= r2["bb_upper"]:
        return None
    if not r2["rsi"] < r1["rsi"] - S3_RSI_MARGIN:
        return None
    return r1, r2, float(df.loc[i1:i2, "low"].min())



def is_setup5(setup_type) -> bool:
    """True for Setup 5 whether given as the enum, its value, or a legacy stored label."""
    if setup_type == SetupType.SETUP_5_OPTION_BB:
        return True
    return str(getattr(setup_type, "value", setup_type)) in (
        SetupType.SETUP_5_OPTION_BB.value, "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB",
    ) or "Setup 5" in str(setup_type)


INDEX_SYMBOLS = {"NIFTY 50", "NIFTY", "NIFTY BANK", "BANKNIFTY", "FINNIFTY", "NIFTY FINANCIAL SERVICES", "SENSEX", "MIDCPNIFTY"}

def evaluate_signals(
    symbol: str,
    df: pd.DataFrame,
    timeframe: str = "5m",
    stock_bias: str | None = None,
    market_bias: str | None = None,
) -> list[Signal]:
    """
    Evaluate all 7 Bollinger Band setups (Setups 1-4, 6-8) across recent candles for both CE and PE.
    Returns list of active signals.
    """
    signals: list[Signal] = []
    required_cols = {"close", "bb_upper", "bb_middle", "bb_lower", "bandwidth", "vwap", "rsi", "ema_9", "adx"}
    if df.empty or len(df) < 20 or not required_cols.issubset(df.columns):
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

    # Intraday fresh entry cutoff: Do not enter new positions after 15:15:00 IST
    if isinstance(ts_raw, (pd.Timestamp, datetime)):
        bar_t = ts_raw.time()
        if bar_t > pd.to_datetime("15:15:00").time():
            return signals

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
    # Squeeze condition: BandWidth was recently at or near 20-period minimum, or in absolute squeeze (<= 5.0%)
    abs_sq = float(settings.SQUEEZE_ABS_BW_PCT)
    if bw_min <= 0.0001:
        is_squeeze = bw <= abs_sq or prev["bandwidth"] <= abs_sq
    else:
        is_squeeze = (
            prev["bandwidth"] <= bw_min * 1.3
            or bw <= bw_min * 1.3
            or bw <= abs_sq
            or prev["bandwidth"] <= abs_sq
        )

    if is_squeeze:
        # CE Squeeze Breakout: Close > Upper Band, Close > VWAP, RSI >= 58
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
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Squeeze expansion above Upper BB with VWAP & RSI confirmation"
            ))

        # PE Squeeze Breakdown: Close < Lower Band, Close < VWAP, RSI <= 42
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
                stop_loss=strike_rec.stop_loss,
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
        # CE Walking: Prior 2 candles had strong closes near or above upper band AND trading above session VWAP
        # Must have expanding upper band (not curling downward into chop) and bullish directional movement (+DI >= -DI)
        upper_expanding = curr["bb_upper"] >= prev["bb_upper"]
        di_bull = curr.get("plus_di", 25.0) >= curr.get("minus_di", 20.0) if ("plus_di" in curr and "minus_di" in curr) else True
        prior_bull = (prev["close"] >= prev["bb_upper"] * 0.998) or (prev2["close"] >= prev2["bb_upper"] * 0.998)
        if prior_bull and upper_expanding and di_bull and ema_9 > mid and close > ema_9 and close > vwap:
            # Low retested near 9 EMA and closed green
            if curr["low"] <= max(ema_9 * 1.004, ema_9 + 0.5) and curr["close"] >= curr["open"]:
                bar_range = max(curr["high"] - curr["low"], close * 0.0015)
                sl = round(ema_9 - max(bar_range * 0.4, close * 0.001), 2)
                strike_rec = recommend_strike(symbol, close, "CE", sl)
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S2_CE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_2_WALKING,
                    option_type="CE",
                    timestamp=ts_str,
                    entry_price=round(close, 2),
                    stop_loss=strike_rec.stop_loss,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Bullish momentum trend riding Upper Band with 9 EMA support bounce"
                ))

        # PE Walking: Prior 2 candles had strong closes near or below lower band AND trading below session VWAP
        # Must have expanding lower band (not curling upward into chop) and bearish directional movement (-DI >= +DI)
        lower_expanding = curr["bb_lower"] <= prev["bb_lower"]
        di_bear = curr.get("minus_di", 25.0) >= curr.get("plus_di", 20.0) if ("plus_di" in curr and "minus_di" in curr) else True
        prior_bear = (prev["close"] <= prev["bb_lower"] * 1.002) or (prev2["close"] <= prev2["bb_lower"] * 1.002)
        if prior_bear and lower_expanding and di_bear and ema_9 < mid and close < ema_9 and close < vwap:
            # High retested near 9 EMA and closed red
            if curr["high"] >= min(ema_9 * 0.996, ema_9 - 0.5) and curr["close"] <= curr["open"]:
                bar_range = max(curr["high"] - curr["low"], close * 0.0015)
                sl = round(ema_9 + max(bar_range * 0.4, close * 0.001), 2)
                strike_rec = recommend_strike(symbol, close, "PE", sl)
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S2_PE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_2_WALKING,
                    option_type="PE",
                    timestamp=ts_str,
                    entry_price=round(close, 2),
                    stop_loss=strike_rec.stop_loss,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Bearish momentum trend riding Lower Band with 9 EMA resistance rejection"
                ))

    # =========================================================================
    # SETUP 3: W-Bottom (CE) & M-Top (PE) Reversals
    # =========================================================================
    for opt in ("CE", "PE"):
        legs = _reversal_legs(df, bullish=(opt == "CE"))
        if legs is None:
            continue
        bullish = opt == "CE"
        row1, row2, neckline = legs
        if bullish:
            if not (close > neckline and prev["close"] <= neckline and close > ema_9):
                continue
            sl = round(row2["low"] - S3_SL_ATR_BUFFER * _recent_atr(df), 2)
        else:
            if not (close < neckline and prev["close"] >= neckline and close < ema_9):
                continue
            sl = round(row2["high"] + S3_SL_ATR_BUFFER * _recent_atr(df), 2)
        strike_rec = recommend_strike(symbol, close, opt, sl)
        signals.append(Signal(
            id=f"{symbol}_{timeframe}_S3_{opt}_{ts_clean}",
            symbol=symbol,
            timeframe=timeframe,
            setup_type=SetupType.SETUP_3_REVERSAL,
            option_type=opt,
            timestamp=ts_str,
            entry_price=round(close, 2),
            stop_loss=strike_rec.stop_loss,
            target_1=strike_rec.target_1,
            target_2=strike_rec.target_2,
            strike_recommendation=strike_rec,
            indicators_snapshot=snap,
            rationale=(
                "Bollinger W-Bottom reversal with Bullish RSI Divergence breaking neckline"
                if bullish else
                "Bollinger M-Top reversal with Bearish RSI Divergence breaking neckline"
            ),
        ))

    # =========================================================================
    # SETUP 4: 9:30 AM Opening Range Breakout (ORB)
    # =========================================================================
    or_high = curr.get("or_high")
    or_low = curr.get("or_low")

    # Active strictly during the morning breakout window (09:30 - 11:30 AM IST)
    is_orb_time = True
    if ts_raw is not None:
        try:
            t_obj = pd.to_datetime(ts_raw)
            bar_t = t_obj.time()
            is_orb_time = (bar_t >= pd.to_datetime("09:30:00").time()) and (bar_t <= pd.to_datetime("11:30:00").time())
        except Exception:
            is_orb_time = True

    if is_orb_time and pd.notna(or_high) and pd.notna(or_low) and float(or_high) > 0 and float(or_low) > 0:
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
                stop_loss=strike_rec.stop_loss,
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
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="9:30 AM Opening Range Breakdown below Lower Band and VWAP"
            ))

    # =========================================================================
    # SETUP 6: Pin Bar Exhaustion Snapback
    # =========================================================================
    curr_high = float(curr.get("high", close))
    curr_low = float(curr.get("low", close))
    curr_open = float(curr.get("open", close))
    curr_close = float(close)
    bar_range = curr_high - curr_low

    if bw > abs_sq and adx <= 25.0 and bar_range > 0.0001:
        # Bearish PE Pin Bar: High > Upper Band, Upper Wick >= 50% range, Close < Upper Band, RSI >= 68
        upper_wick = curr_high - max(curr_open, curr_close)
        is_pe_pinbar = (
            curr_high > upper
            and curr_close < upper
            and (upper_wick >= 0.50 * bar_range)
            and (max(curr_open, curr_close) <= curr_low + 0.60 * bar_range)
            and rsi >= 68.0
            and mid < curr_close
        )
        if is_pe_pinbar:
            sl = round(curr_high + max(1.0, 0.0005 * curr_close), 2)
            strike_rec = recommend_strike(
                symbol, curr_close, "PE", sl,
                target_1=round(mid, 2), target_2=round(lower, 2),
                strike_preference="ITM_1"
            )
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S6_PE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_6_PINBAR_SNAPBACK,
                option_type="PE",
                timestamp=ts_str,
                entry_price=round(curr_close, 2),
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Pin Bar exhaustion at Upper BB with RSI overbought and ADX non-trend snapback"
            ))

        # Bullish CE Pin Bar: Low < Lower Band, Lower Wick >= 50% range, Close > Lower Band, RSI <= 32
        lower_wick = min(curr_open, curr_close) - curr_low
        is_ce_pinbar = (
            curr_low < lower
            and curr_close > lower
            and (lower_wick >= 0.50 * bar_range)
            and (min(curr_open, curr_close) >= curr_low + 0.40 * bar_range)
            and rsi <= 32.0
            and mid > curr_close
        )
        if is_ce_pinbar:
            sl = round(curr_low - max(1.0, 0.0005 * curr_close), 2)
            strike_rec = recommend_strike(
                symbol, curr_close, "CE", sl,
                target_1=round(mid, 2), target_2=round(upper, 2),
                strike_preference="ITM_1"
            )
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S6_CE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_6_PINBAR_SNAPBACK,
                option_type="CE",
                timestamp=ts_str,
                entry_price=round(curr_close, 2),
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Pin Bar exhaustion at Lower BB with RSI oversold and ADX non-trend snapback"
            ))

    # =========================================================================
    # SETUP 7: 2.5σ Puncture & Inside Bar Breakdown
    # =========================================================================
    if bw > abs_sq and len(df) >= 22:
        prev2 = df.iloc[last_idx - 2]
        prev2_high = float(prev2.get("high", prev2["close"]))
        prev2_low = float(prev2.get("low", prev2["close"]))
        prev2_bb_upper_25 = float(prev2.get("bb_upper_25", prev2["bb_middle"] + 2.5 * prev2.get("bb_std", (prev2["bb_upper"] - prev2["bb_middle"]) * 1.25)))
        prev2_bb_lower_25 = float(prev2.get("bb_lower_25", prev2["bb_middle"] - 2.5 * prev2.get("bb_std", (prev2["bb_middle"] - prev2["bb_lower"]) * 1.25)))

        prev_high = float(prev.get("high", prev["close"]))
        prev_low = float(prev.get("low", prev["close"]))

        # Bearish PE: Mother bar (t-2) pierced extreme 2.5σ band, inside bar at t-1 strictly contained,
        # trigger bar (t) breaks strictly below inside bar's low, and midline is below entry
        is_pe_inside_curr = (
            prev2_high >= prev2_bb_upper_25
            and prev_high <= prev2_high
            and prev_low >= prev2_low
            and curr_close < prev_low
            and mid < curr_close
        )
        pe_mother_high = prev2_high

        if is_pe_inside_curr:
            sl = round(pe_mother_high + max(0.5, 0.0005 * curr_close), 2)
            strike_rec = recommend_strike(
                symbol, curr_close, "PE", sl,
                target_1=round(mid, 2), target_2=round(lower, 2),
                strike_preference="ITM_1"
            )
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S7_PE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_7_INSIDE_BAR_SNAPBACK,
                option_type="PE",
                timestamp=ts_str,
                entry_price=round(curr_close, 2),
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Extreme 2.5σ puncture and Inside Bar breakdown snapback to 20-SMA"
            ))

        # Bullish CE: Mother bar (t-2) pierced extreme 2.5σ band, inside bar at t-1 strictly contained,
        # trigger bar (t) breaks strictly above inside bar's high, and midline is above entry
        is_ce_inside_curr = (
            prev2_low <= prev2_bb_lower_25
            and prev_high <= prev2_high
            and prev_low >= prev2_low
            and curr_close > prev_high
            and mid > curr_close
        )
        ce_mother_low = prev2_low

        if is_ce_inside_curr:
            sl = round(ce_mother_low - max(0.5, 0.0005 * curr_close), 2)
            strike_rec = recommend_strike(
                symbol, curr_close, "CE", sl,
                target_1=round(mid, 2), target_2=round(upper, 2),
                strike_preference="ITM_1"
            )
            signals.append(Signal(
                id=f"{symbol}_{timeframe}_S7_CE_{ts_clean}",
                symbol=symbol,
                timeframe=timeframe,
                setup_type=SetupType.SETUP_7_INSIDE_BAR_SNAPBACK,
                option_type="CE",
                timestamp=ts_str,
                entry_price=round(curr_close, 2),
                stop_loss=strike_rec.stop_loss,
                target_1=strike_rec.target_1,
                target_2=strike_rec.target_2,
                strike_recommendation=strike_rec,
                indicators_snapshot=snap,
                rationale="Extreme 2.5σ puncture and Inside Bar breakout snapback to 20-SMA"
            ))

    # =========================================================================
    # SETUP 8: Climax Swing RSI Divergence Fade
    # =========================================================================
    if bw > abs_sq and len(df) >= 20:
        window_size = min(15, len(df))
        lookback_window = df.iloc[-window_size:]
        recent_3 = lookback_window.iloc[-3:]
        prior_candles = lookback_window.iloc[:-3]

        if len(prior_candles) >= 3:
            # Bearish PE Fade: Peak 1 pierced upper band, Peak 2 tests/exceeds Peak 1, RSI divergence >= 2.0 pts
            p1_idx = prior_candles["high"].idxmax()
            row_p1 = df.loc[[p1_idx]].iloc[0]
            p2_idx = recent_3["high"].idxmax()
            row_p2 = df.loc[[p2_idx]].iloc[0]

            if (
                row_p1["high"] >= row_p1["bb_upper"]
                and row_p2["high"] >= row_p1["high"] * 0.998
                and (float(row_p1["rsi"]) - float(row_p2["rsi"]) >= 2.0)
                and curr_close < upper
                and mid < curr_close
            ):
                sl = round(max(float(row_p2["high"]), curr_high) + max(0.5, 0.0005 * curr_close), 2)
                strike_rec = recommend_strike(
                    symbol, curr_close, "PE", sl,
                    target_1=round(mid, 2), target_2=round(lower, 2),
                    strike_preference="ITM_1"
                )
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S8_PE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_8_DIVERGENCE_SNAPBACK,
                    option_type="PE",
                    timestamp=ts_str,
                    entry_price=round(curr_close, 2),
                    stop_loss=strike_rec.stop_loss,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Climax swing high with Bearish RSI Divergence snapback to 20-SMA"
                ))

            # Bullish CE Fade: Trough 1 pierced lower band, Trough 2 tests/breaks Trough 1, RSI divergence >= 2.0 pts
            t1_idx = prior_candles["low"].idxmin()
            row_t1 = df.loc[[t1_idx]].iloc[0]
            t2_idx = recent_3["low"].idxmin()
            row_t2 = df.loc[[t2_idx]].iloc[0]

            if (
                row_t1["low"] <= row_t1["bb_lower"]
                and row_t2["low"] <= row_t1["low"] * 1.002
                and (float(row_t2["rsi"]) - float(row_t1["rsi"]) >= 2.0)
                and curr_close > lower
                and mid > curr_close
            ):
                sl = round(min(float(row_t2["low"]), curr_low) - max(0.5, 0.0005 * curr_close), 2)
                strike_rec = recommend_strike(
                    symbol, curr_close, "CE", sl,
                    target_1=round(mid, 2), target_2=round(upper, 2),
                    strike_preference="ITM_1"
                )
                signals.append(Signal(
                    id=f"{symbol}_{timeframe}_S8_CE_{ts_clean}",
                    symbol=symbol,
                    timeframe=timeframe,
                    setup_type=SetupType.SETUP_8_DIVERGENCE_SNAPBACK,
                    option_type="CE",
                    timestamp=ts_str,
                    entry_price=round(curr_close, 2),
                    stop_loss=strike_rec.stop_loss,
                    target_1=strike_rec.target_1,
                    target_2=strike_rec.target_2,
                    strike_recommendation=strike_rec,
                    indicators_snapshot=snap,
                    rationale="Climax swing low with Bullish RSI Divergence snapback to 20-SMA"
                ))

    # Stock momentum and market bias filtering for non-index equities
    if symbol.upper() not in INDEX_SYMBOLS:
        if stock_bias not in ("BULLISH", "BEARISH"):
            return []
        if stock_bias == "BULLISH":
            if market_bias == "BEARISH":
                return []
            signals = [s for s in signals if s.option_type == "CE"]
        elif stock_bias == "BEARISH":
            if market_bias == "BULLISH":
                return []
            signals = [s for s in signals if s.option_type == "PE"]

    return signals
