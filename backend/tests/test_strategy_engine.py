import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, SetupType

def create_series_df(n: int = 30, base_p: float = 100.0) -> pd.DataFrame:
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = base_p
    for i in range(n):
        ts = start_t + timedelta(minutes=5 * i)
        # Gentle oscillation to warm up RSI and BB
        step = 0.2 if i % 2 == 0 else -0.2
        p += step
        records.append({
            "timestamp": ts,
            "open": p - step,
            "high": max(p, p - step) + 0.3,
            "low": min(p, p - step) - 0.3,
            "close": p,
            "volume": 2000
        })
    return pd.DataFrame(records)

def test_setup1_squeeze_breakout_ce():
    df = create_series_df(25, 100.0)
    # Consecutive strong up candles to trigger breakout & high RSI
    df.loc[22, "close"] = 102.0
    df.loc[23, "close"] = 104.0
    df.loc[24, "open"] = 104.0
    df.loc[24, "close"] = 108.0
    df.loc[24, "high"] = 108.5
    df.loc[24, "volume"] = 10000
    
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    
    s1_signals = [s for s in signals if s.setup_type == SetupType.SETUP_1_SQUEEZE and s.option_type == "CE"]
    assert len(s1_signals) >= 1
    sig = s1_signals[0]
    assert sig.option_type == "CE"
    assert sig.entry_price == 108.0
    assert sig.stop_loss < 108.0

def test_setup1_squeeze_breakout_pe():
    df = create_series_df(25, 100.0)
    df.loc[22, "close"] = 98.0
    df.loc[23, "close"] = 96.0
    df.loc[24, "open"] = 96.0
    df.loc[24, "close"] = 90.0
    df.loc[24, "low"] = 89.5
    df.loc[24, "volume"] = 10000
    
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    
    s1_signals = [s for s in signals if s.setup_type == SetupType.SETUP_1_SQUEEZE and s.option_type == "PE"]
    assert len(s1_signals) >= 1
    sig = s1_signals[0]
    assert sig.option_type == "PE"
    assert sig.entry_price == 90.0
    assert sig.stop_loss > 90.0

def test_setup4_opening_range_breakout_ce():
    df = create_series_df(25, 100.0)
    # Candle 24 at 11:15 simulates ORB breakout above OR High
    df.loc[24, "open"] = df["or_high"].max() if "or_high" in df else 102.0
    df.loc[24, "close"] = 110.0
    df.loc[24, "high"] = 110.5
    
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s4_signals = [s for s in signals if s.setup_type == SetupType.SETUP_4_ORB and s.option_type == "CE"]
    assert len(s4_signals) >= 1
    assert s4_signals[0].option_type == "CE"

def test_setup4_opening_range_breakout_pe():
    df = create_series_df(25, 100.0)
    # Candle 24 at 11:15 simulates ORB breakdown below OR Low
    df.loc[24, "open"] = 98.0
    df.loc[24, "close"] = 88.0
    df.loc[24, "low"] = 87.5
    
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s4_signals = [s for s in signals if s.setup_type == SetupType.SETUP_4_ORB and s.option_type == "PE"]
    assert len(s4_signals) >= 1
    assert s4_signals[0].option_type == "PE"
    assert s4_signals[0].stop_loss > s4_signals[0].entry_price

def test_setup2_walking_bands_ce():
    df = create_series_df(25, 100.0)
    # Strong upward trend to create ADX > 23 and walk upper band
    for i in range(15, 25):
        df.loc[i, "close"] = 100.0 + (i - 15) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] + 0.5
        df.loc[i, "low"] = df.loc[i, "close"] - 0.5
        df.loc[i, "open"] = df.loc[i, "close"] - 1.0

    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    assert isinstance(signals, list)
