import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.services.strategy_engine import evaluate_signals, SetupType

def create_base_df(n: int = 30) -> pd.DataFrame:
    base_time = datetime(2026, 10, 9, 10, 0)
    records = []
    p = 100.0
    for i in range(n):
        ts = base_time + timedelta(minutes=5 * i)
        records.append({
            "timestamp": ts,
            "open": p,
            "high": p + 1.0,
            "low": p - 1.0,
            "close": p + 0.5,
            "volume": 5000,
            "bb_middle": p,
            "bb_upper": p + 2.0,
            "bb_lower": p - 2.0,
            "bandwidth": 4.0,
            "bandwidth_20_min": 3.0,
            "percent_b": 0.8,
            "vwap": p - 0.5,
            "rsi": 62.0,
            "ema_9": p + 0.2,
            "adx": 26.0,
            "plus_di": 28.0,
            "minus_di": 14.0
        })
        p += 0.2
    return pd.DataFrame(records)

def test_setup2_ce_rejected_when_upper_band_is_curling_down():
    df = create_base_df(30)
    # Set prior bull bars
    df.loc[28, "bb_upper"] = 110.0
    df.loc[28, "close"] = 110.2
    
    # Current bar touches 9 EMA and closes green
    curr_ema = df.loc[29, "ema_9"]
    df.loc[29, "open"] = curr_ema
    df.loc[29, "low"] = curr_ema - 0.1
    df.loc[29, "close"] = curr_ema + 0.5
    df.loc[29, "high"] = curr_ema + 0.8
    df.loc[29, "plus_di"] = 28.0
    df.loc[29, "minus_di"] = 14.0

    # Simulate flat / downward curling upper band (e.g. consolidation ceiling)
    df.loc[29, "bb_upper"] = 109.8  # curling down!

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    assert len(s2_signals) == 0, "Setup 2 CE should be rejected when Upper Band is curling downward"

def test_setup2_ce_accepted_when_upper_band_is_expanding_upward():
    df = create_base_df(30)
    # Set prior bull bars
    df.loc[28, "bb_upper"] = 110.0
    df.loc[28, "close"] = 110.2
    
    # Current bar touches 9 EMA and closes green
    curr_ema = df.loc[29, "ema_9"]
    df.loc[29, "open"] = curr_ema
    df.loc[29, "low"] = curr_ema - 0.1
    df.loc[29, "close"] = curr_ema + 0.5
    df.loc[29, "high"] = curr_ema + 0.8

    # Expanding upper band
    df.loc[29, "bb_upper"] = 110.5  # expanding up!
    df.loc[29, "plus_di"] = 28.0
    df.loc[29, "minus_di"] = 14.0

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    assert len(s2_signals) == 1, "Setup 2 CE should be accepted when Upper Band is expanding upward"

def test_setup2_pe_rejected_when_lower_band_is_curling_up():
    df = create_base_df(30)
    # Set prior bear bars
    df.loc[28, "bb_lower"] = 90.0
    df.loc[28, "close"] = 89.8
    
    # Current bar touches 9 EMA and closes red
    curr_ema = df.loc[29, "ema_9"]
    df.loc[29, "open"] = curr_ema
    df.loc[29, "high"] = curr_ema + 0.1
    df.loc[29, "close"] = curr_ema - 0.5
    df.loc[29, "low"] = curr_ema - 0.8
    df.loc[29, "bb_middle"] = curr_ema + 2.0
    df.loc[29, "vwap"] = curr_ema + 1.0
    df.loc[29, "minus_di"] = 28.0
    df.loc[29, "plus_di"] = 14.0

    # Simulate flat / curling up lower band (support bounce/chop)
    df.loc[29, "bb_lower"] = 90.2  # curling up!

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "PE"]
    assert len(s2_signals) == 0, "Setup 2 PE should be rejected when Lower Band is curling upward"

def test_setup2_pe_accepted_when_lower_band_is_expanding_down():
    df = create_base_df(30)
    # Set prior bear bars
    df.loc[28, "bb_lower"] = 90.0
    df.loc[28, "close"] = 89.8
    
    # Current bar touches 9 EMA and closes red
    curr_ema = df.loc[29, "ema_9"]
    df.loc[29, "open"] = curr_ema
    df.loc[29, "high"] = curr_ema + 0.1
    df.loc[29, "close"] = curr_ema - 0.5
    df.loc[29, "low"] = curr_ema - 0.8
    df.loc[29, "bb_middle"] = curr_ema + 2.0
    df.loc[29, "vwap"] = curr_ema + 1.0
    df.loc[29, "minus_di"] = 28.0
    df.loc[29, "plus_di"] = 14.0

    # Expanding lower band
    df.loc[29, "bb_lower"] = 89.5  # expanding down!

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "PE"]
    assert len(s2_signals) == 1, "Setup 2 PE should be accepted when Lower Band is expanding downward"

