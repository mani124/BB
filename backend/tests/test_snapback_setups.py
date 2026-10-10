import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, SetupType


def create_base_df(n: int = 30, base_p: float = 100.0) -> pd.DataFrame:
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = base_p
    for i in range(n):
        ts = start_t + timedelta(minutes=5 * i)
        step = 0.3 if i % 2 == 0 else -0.3
        p += step
        records.append({
            "timestamp": ts,
            "open": p - step,
            "high": max(p, p - step) + 0.5,
            "low": min(p, p - step) - 0.5,
            "close": p,
            "volume": 3000
        })
    df = pd.DataFrame(records)
    return calculate_indicators(df)


def test_setup6_bearish_pe_pinbar():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    
    # Ensure wide enough bandwidth
    ind_df.loc[:, "bandwidth"] = 8.0
    upper_band = ind_df.loc[last_idx, "bb_upper"]
    
    # Candle t: High punches above upper band, rejection upper wick >= 50%, closes back inside
    ind_df.loc[last_idx, "high"] = upper_band + 4.0
    ind_df.loc[last_idx, "open"] = upper_band - 1.0
    ind_df.loc[last_idx, "close"] = upper_band - 1.5
    ind_df.loc[last_idx, "low"] = upper_band - 2.0
    ind_df.loc[last_idx, "rsi"] = 72.0
    ind_df.loc[last_idx, "adx"] = 20.0
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s6_signals = [s for s in signals if s.setup_type == SetupType.SETUP_6_PINBAR_SNAPBACK and s.option_type == "PE"]
    
    assert len(s6_signals) >= 1
    sig = s6_signals[0]
    assert sig.option_type == "PE"
    assert sig.entry_price == round(ind_df.loc[last_idx, "close"], 2)
    assert sig.stop_loss >= ind_df.loc[last_idx, "high"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_setup6_adx_runaway_trend_invalidation():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    
    ind_df.loc[:, "bandwidth"] = 8.0
    upper_band = ind_df.loc[last_idx, "bb_upper"]
    
    ind_df.loc[last_idx, "high"] = upper_band + 4.0
    ind_df.loc[last_idx, "open"] = upper_band - 1.0
    ind_df.loc[last_idx, "close"] = upper_band - 1.5
    ind_df.loc[last_idx, "low"] = upper_band - 2.0
    ind_df.loc[last_idx, "rsi"] = 72.0
    ind_df.loc[last_idx, "adx"] = 32.0  # Runaway trend: should invalidate mean-reversion
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s6_signals = [s for s in signals if s.setup_type == SetupType.SETUP_6_PINBAR_SNAPBACK]
    
    assert len(s6_signals) == 0


def test_setup6_bullish_ce_pinbar():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    
    ind_df.loc[:, "bandwidth"] = 8.0
    lower_band = ind_df.loc[last_idx, "bb_lower"]
    
    # Candle t: Low pierces below lower band, lower wick >= 50%, closes back inside
    ind_df.loc[last_idx, "low"] = lower_band - 4.0
    ind_df.loc[last_idx, "open"] = lower_band + 1.0
    ind_df.loc[last_idx, "close"] = lower_band + 1.5
    ind_df.loc[last_idx, "high"] = lower_band + 2.0
    ind_df.loc[last_idx, "rsi"] = 28.0
    ind_df.loc[last_idx, "adx"] = 22.0
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s6_signals = [s for s in signals if s.setup_type == SetupType.SETUP_6_PINBAR_SNAPBACK and s.option_type == "CE"]
    
    assert len(s6_signals) >= 1
    sig = s6_signals[0]
    assert sig.option_type == "CE"
    assert sig.entry_price == round(ind_df.loc[last_idx, "close"], 2)
    assert sig.stop_loss <= ind_df.loc[last_idx, "low"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_setup7_extreme_25_inside_bar_pe():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    prev_idx = last_idx - 1
    
    ind_df.loc[:, "bandwidth"] = 8.0
    upper_25 = ind_df.loc[prev_idx, "bb_upper_25"]
    
    # Bar t-1 (Mother bar): Punctures extreme 2.5 sigma band
    ind_df.loc[prev_idx, "high"] = upper_25 + 1.0
    ind_df.loc[prev_idx, "low"] = upper_25 - 4.0
    ind_df.loc[prev_idx, "close"] = upper_25 - 0.5
    
    # Bar t (Inside bar): Contained inside Mother bar range, breakdown trigger
    ind_df.loc[last_idx, "high"] = ind_df.loc[prev_idx, "high"] - 0.5
    ind_df.loc[last_idx, "open"] = ind_df.loc[prev_idx, "low"] + 1.0
    ind_df.loc[last_idx, "low"] = ind_df.loc[prev_idx, "low"] + 0.2
    ind_df.loc[last_idx, "close"] = ind_df.loc[last_idx, "low"]  # Breakdown at inside bar low
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s7_signals = [s for s in signals if s.setup_type == SetupType.SETUP_7_INSIDE_BAR_SNAPBACK and s.option_type == "PE"]
    
    assert len(s7_signals) >= 1
    sig = s7_signals[0]
    assert sig.option_type == "PE"
    assert sig.stop_loss >= ind_df.loc[prev_idx, "high"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_setup7_extreme_25_inside_bar_ce():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    prev_idx = last_idx - 1
    
    ind_df.loc[:, "bandwidth"] = 8.0
    lower_25 = ind_df.loc[prev_idx, "bb_lower_25"]
    
    # Bar t-1 (Mother bar): Punctures extreme lower 2.5 sigma band
    ind_df.loc[prev_idx, "low"] = lower_25 - 1.0
    ind_df.loc[prev_idx, "high"] = lower_25 + 4.0
    ind_df.loc[prev_idx, "close"] = lower_25 + 0.5
    
    # Bar t (Inside bar): Contained inside Mother bar range, breakout trigger
    ind_df.loc[last_idx, "low"] = ind_df.loc[prev_idx, "low"] + 0.5
    ind_df.loc[last_idx, "open"] = ind_df.loc[prev_idx, "high"] - 1.0
    ind_df.loc[last_idx, "high"] = ind_df.loc[prev_idx, "high"] - 0.2
    ind_df.loc[last_idx, "close"] = ind_df.loc[last_idx, "high"]  # Breakout at inside bar high
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s7_signals = [s for s in signals if s.setup_type == SetupType.SETUP_7_INSIDE_BAR_SNAPBACK and s.option_type == "CE"]
    
    assert len(s7_signals) >= 1
    sig = s7_signals[0]
    assert sig.option_type == "CE"
    assert sig.stop_loss <= ind_df.loc[prev_idx, "low"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_setup8_climax_rsi_divergence_pe():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    swing1_idx = last_idx - 5
    
    ind_df.loc[:, "bandwidth"] = 8.0
    
    # Swing 1: Pierced upper band with high RSI
    ind_df.loc[swing1_idx, "high"] = ind_df.loc[swing1_idx, "bb_upper"] + 2.0
    ind_df.loc[swing1_idx, "close"] = ind_df.loc[swing1_idx, "bb_upper"] + 1.0
    ind_df.loc[swing1_idx, "rsi"] = 76.0
    
    # Swing 2 (current bar): Retests or exceeds Swing 1 high, but has lower RSI (divergence >= 2.0 pts)
    ind_df.loc[last_idx, "high"] = ind_df.loc[swing1_idx, "high"] + 0.5
    ind_df.loc[last_idx, "close"] = ind_df.loc[last_idx, "bb_upper"] - 0.5  # Closes back inside band
    ind_df.loc[last_idx, "rsi"] = 68.0  # Divergence delta = 8.0 >= 2.0 pts
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s8_signals = [s for s in signals if s.setup_type == SetupType.SETUP_8_DIVERGENCE_SNAPBACK and s.option_type == "PE"]
    
    assert len(s8_signals) >= 1
    sig = s8_signals[0]
    assert sig.option_type == "PE"
    assert sig.stop_loss >= ind_df.loc[last_idx, "high"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_setup8_climax_rsi_divergence_ce():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    swing1_idx = last_idx - 5
    
    ind_df.loc[:, "bandwidth"] = 8.0
    
    # Swing 1: Pierced lower band with low RSI
    ind_df.loc[swing1_idx, "low"] = ind_df.loc[swing1_idx, "bb_lower"] - 2.0
    ind_df.loc[swing1_idx, "close"] = ind_df.loc[swing1_idx, "bb_lower"] - 1.0
    ind_df.loc[swing1_idx, "rsi"] = 22.0
    
    # Swing 2 (current bar): Retests or breaks below Swing 1 low, but higher RSI (divergence >= 2.0 pts)
    ind_df.loc[last_idx, "low"] = ind_df.loc[swing1_idx, "low"] - 0.5
    ind_df.loc[last_idx, "close"] = ind_df.loc[last_idx, "bb_lower"] + 0.5  # Closes back inside band
    ind_df.loc[last_idx, "rsi"] = 30.0  # Divergence delta = 8.0 >= 2.0 pts
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s8_signals = [s for s in signals if s.setup_type == SetupType.SETUP_8_DIVERGENCE_SNAPBACK and s.option_type == "CE"]
    
    assert len(s8_signals) >= 1
    sig = s8_signals[0]
    assert sig.option_type == "CE"
    assert sig.stop_loss <= ind_df.loc[last_idx, "low"]
    assert sig.target_1 == round(ind_df.loc[last_idx, "bb_middle"], 2)


def test_zero_division_and_flat_candle_guards():
    ind_df = create_base_df(25, 100.0)
    last_idx = len(ind_df) - 1
    
    # Flat candle: high == low, zero bandwidth
    ind_df.loc[last_idx, "high"] = 100.0
    ind_df.loc[last_idx, "low"] = 100.0
    ind_df.loc[last_idx, "open"] = 100.0
    ind_df.loc[last_idx, "close"] = 100.0
    ind_df.loc[last_idx, "bandwidth"] = 0.0
    
    # Must not raise ZeroDivisionError
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    assert isinstance(signals, list)
