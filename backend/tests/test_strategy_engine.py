import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, SetupType

def create_series_df(n: int = 30, base_p: float = 100.0, start_time: datetime = datetime(2026, 10, 8, 9, 15)) -> pd.DataFrame:
    records = []
    p = base_p
    for i in range(n):
        ts = start_time + timedelta(minutes=5 * i)
        # Oscillation to warm up RSI and BB
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
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert sig.target_1 == sig.strike_recommendation.target_1
    assert sig.target_2 == sig.strike_recommendation.target_2

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
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert sig.target_1 == sig.strike_recommendation.target_1
    assert sig.target_2 == sig.strike_recommendation.target_2

def test_setup2_walking_bands_ce():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 100.0
    for i in range(20):
        ts = start_t + timedelta(minutes=5 * i)
        p += 0.5
        records.append({
            "timestamp": ts,
            "open": p - 0.5,
            "high": p + 0.5,
            "low": p - 0.5,
            "close": p,
            "volume": 2000
        })

    for i in range(20, 26):
        ts = start_t + timedelta(minutes=5 * i)
        p += 3.0
        records.append({
            "timestamp": ts,
            "open": p - 2.5,
            "high": p + 0.5,
            "low": p - 2.5,
            "close": p,
            "volume": 5000
        })

    # Candle 26: retests 9 EMA and closes green
    ts = start_t + timedelta(minutes=5 * 26)
    records.append({
        "timestamp": ts,
        "open": 123.0,
        "high": 126.0,
        "low": 120.0,
        "close": 125.0,
        "volume": 4000
    })

    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    assert len(s2_signals) >= 1
    sig = s2_signals[0]
    assert sig.option_type == "CE"
    assert sig.entry_price == 125.0
    assert sig.stop_loss < 125.0
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert "9 EMA support bounce" in sig.rationale

def test_setup2_walking_bands_pe():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 200.0
    for i in range(20):
        ts = start_t + timedelta(minutes=5 * i)
        p -= 0.5
        records.append({
            "timestamp": ts,
            "open": p + 0.5,
            "high": p + 0.5,
            "low": p - 0.5,
            "close": p,
            "volume": 2000
        })

    for i in range(20, 26):
        ts = start_t + timedelta(minutes=5 * i)
        p -= 3.0
        records.append({
            "timestamp": ts,
            "open": p + 2.5,
            "high": p + 2.5,
            "low": p - 0.5,
            "close": p,
            "volume": 5000
        })

    # Candle 26: retest near 9 EMA and closes red
    ts = start_t + timedelta(minutes=5 * 26)
    records.append({
        "timestamp": ts,
        "open": 177.0,
        "high": 180.0,
        "low": 174.0,
        "close": 175.0,
        "volume": 4000
    })

    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    
    s2_signals = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "PE"]
    assert len(s2_signals) >= 1
    sig = s2_signals[0]
    assert sig.option_type == "PE"
    assert sig.entry_price == 175.0
    assert sig.stop_loss > 175.0
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert "9 EMA resistance rejection" in sig.rationale

def test_setup3_w_bottom_reversal_ce():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    for i in range(25):
        ts = start_t + timedelta(minutes=5 * i)
        records.append({
            "timestamp": ts,
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 2000
        })

    base_idx = len(records)
    # Trough 1: drop below lower BB
    records.append({"timestamp": start_t + timedelta(minutes=5 * base_idx), "open": 100.0, "high": 100.0, "low": 92.0, "close": 93.0, "volume": 3000})
    # Bounce towards neckline
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 1)), "open": 93.0, "high": 98.0, "low": 93.0, "close": 97.5, "volume": 2500})
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 2)), "open": 97.5, "high": 98.5, "low": 97.0, "close": 98.0, "volume": 2000})
    # Trough 2: inside lower BB, higher RSI
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 3)), "open": 98.0, "high": 98.0, "low": 94.5, "close": 95.0, "volume": 2000})
    # Consolidation below neckline
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 4)), "open": 95.0, "high": 97.0, "low": 95.0, "close": 96.5, "volume": 2000})
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 5)), "open": 96.5, "high": 98.0, "low": 96.5, "close": 98.0, "volume": 2000})
    # Breakout candle above neckline (98.5)
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 6)), "open": 98.0, "high": 101.0, "low": 98.0, "close": 100.5, "volume": 5000})

    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")

    s3_signals = [s for s in signals if s.setup_type == SetupType.SETUP_3_REVERSAL and s.option_type == "CE"]
    assert len(s3_signals) >= 1
    sig = s3_signals[0]
    assert sig.option_type == "CE"
    assert sig.entry_price == 100.5
    assert sig.stop_loss < 100.5
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert "W-Bottom" in sig.rationale

def test_setup3_m_top_reversal_pe():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    for i in range(25):
        ts = start_t + timedelta(minutes=5 * i)
        records.append({
            "timestamp": ts,
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 2000
        })

    base_idx = len(records)
    # Peak 1: above upper BB
    records.append({"timestamp": start_t + timedelta(minutes=5 * base_idx), "open": 100.0, "high": 108.0, "low": 100.0, "close": 107.0, "volume": 3000})
    # Pullback to neckline
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 1)), "open": 107.0, "high": 107.0, "low": 102.0, "close": 102.5, "volume": 2500})
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 2)), "open": 102.5, "high": 103.0, "low": 101.5, "close": 102.0, "volume": 2000})
    # Peak 2: inside upper BB, lower RSI
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 3)), "open": 102.0, "high": 105.5, "low": 102.0, "close": 104.5, "volume": 2000})
    # Consolidation above neckline
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 4)), "open": 104.5, "high": 105.0, "low": 103.0, "close": 103.5, "volume": 2000})
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 5)), "open": 103.5, "high": 104.0, "low": 102.0, "close": 102.0, "volume": 2000})
    # Breakdown candle below neckline (101.5)
    records.append({"timestamp": start_t + timedelta(minutes=5 * (base_idx + 6)), "open": 102.0, "high": 102.0, "low": 99.0, "close": 99.5, "volume": 5000})

    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")

    s3_signals = [s for s in signals if s.setup_type == SetupType.SETUP_3_REVERSAL and s.option_type == "PE"]
    assert len(s3_signals) >= 1
    sig = s3_signals[0]
    assert sig.option_type == "PE"
    assert sig.entry_price == 99.5
    assert sig.stop_loss > 99.5
    assert sig.stop_loss == sig.strike_recommendation.stop_loss
    assert "M-Top" in sig.rationale

def test_setup4_opening_range_breakout_ce():
    df = create_series_df(25, 100.0)
    # Candle 24 at 11:15 is inside the 09:30 - 11:30 AM window
    df.loc[24, "open"] = 102.0
    df.loc[24, "close"] = 110.0
    df.loc[24, "high"] = 110.5
    
    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s4_signals = [s for s in signals if s.setup_type == SetupType.SETUP_4_ORB and s.option_type == "CE"]
    assert len(s4_signals) >= 1
    sig = s4_signals[0]
    assert sig.option_type == "CE"
    assert sig.entry_price == 110.0
    assert sig.stop_loss < 110.0
    assert sig.stop_loss == sig.strike_recommendation.stop_loss

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
    sig = s4_signals[0]
    assert sig.option_type == "PE"
    assert sig.entry_price == 88.0
    assert sig.stop_loss > 88.0
    assert sig.stop_loss == sig.strike_recommendation.stop_loss

def test_setup4_outside_orb_window_no_signal():
    # Start at 12:00 PM (after 11:30 AM window)
    start_afternoon = datetime(2026, 10, 8, 12, 0)
    df = create_series_df(25, 100.0, start_time=start_afternoon)
    df.loc[24, "open"] = 102.0
    df.loc[24, "close"] = 110.0
    df.loc[24, "high"] = 110.5

    ind_df = calculate_indicators(df)
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s4_signals = [s for s in signals if s.setup_type == SetupType.SETUP_4_ORB]
    assert len(s4_signals) == 0

def test_edge_cases_handling():
    # Empty DataFrame
    assert evaluate_signals("NIFTY 50", pd.DataFrame()) == []
    
    # Under 20 rows
    short_df = pd.DataFrame([{"close": 100.0, "timestamp": datetime.now()}] * 10)
    assert evaluate_signals("NIFTY 50", short_df) == []

    # Missing indicator columns
    df_missing_cols = pd.DataFrame([{"open": 100.0, "close": 101.0, "timestamp": datetime.now()}] * 25)
    assert evaluate_signals("NIFTY 50", df_missing_cols) == []

def test_setup2_ce_rejected_when_below_vwap():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 100.0
    for i in range(20):
        ts = start_t + timedelta(minutes=5 * i)
        p += 0.5
        records.append({
            "timestamp": ts,
            "open": p - 0.5,
            "high": p + 0.5,
            "low": p - 0.5,
            "close": p,
            "volume": 2000
        })
    for i in range(20, 26):
        ts = start_t + timedelta(minutes=5 * i)
        p += 3.0
        records.append({
            "timestamp": ts,
            "open": p - 2.5,
            "high": p + 0.5,
            "low": p - 2.5,
            "close": p,
            "volume": 5000
        })
    ts = start_t + timedelta(minutes=5 * 26)
    records.append({
        "timestamp": ts,
        "open": 123.0,
        "high": 126.0,
        "low": 120.0,
        "close": 125.0,
        "volume": 4000
    })
    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    
    # Simulate a down-day where session VWAP is 150.0 (well above current close 125.0)
    ind_df["vwap"] = 150.0
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s2_ce = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    assert len(s2_ce) == 0, "CE buy must be rejected when price is below session VWAP"

def test_setup2_pe_rejected_when_above_vwap():
    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 200.0
    for i in range(20):
        ts = start_t + timedelta(minutes=5 * i)
        p -= 0.5
        records.append({
            "timestamp": ts,
            "open": p + 0.5,
            "high": p + 0.5,
            "low": p - 0.5,
            "close": p,
            "volume": 2000
        })
    for i in range(20, 26):
        ts = start_t + timedelta(minutes=5 * i)
        p -= 3.0
        records.append({
            "timestamp": ts,
            "open": p + 2.5,
            "high": p + 0.5,
            "low": p - 2.5,
            "close": p,
            "volume": 5000
        })
    ts = start_t + timedelta(minutes=5 * 26)
    records.append({
        "timestamp": ts,
        "open": 177.0,
        "high": 180.0,
        "low": 174.0,
        "close": 175.0,
        "volume": 4000
    })
    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    
    # Simulate an up-day where session VWAP is 160.0 (below current close 175.0)
    ind_df["vwap"] = 160.0
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s2_pe = [s for s in signals if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "PE"]
    assert len(s2_pe) == 0, "PE buy must be rejected when price is above session VWAP"

def test_intraday_cutoff_rejects_entries_after_15_15():
    # Construct a breakout at 15:25 (after 15:15 cutoff)
    start_late = datetime(2026, 10, 8, 13, 25)
    # 25 bars * 5m = 120 minutes -> bar 24 is at 15:25:00
    df = create_series_df(25, 100.0, start_time=start_late)
    df.loc[22, "close"] = 102.0
    df.loc[23, "close"] = 104.0
    df.loc[24, "open"] = 104.0
    df.loc[24, "close"] = 108.0
    df.loc[24, "high"] = 108.5
    df.loc[24, "volume"] = 10000
    
    ind_df = calculate_indicators(df)
    assert ind_df.iloc[-1]["timestamp"].time() == datetime.strptime("15:25:00", "%H:%M:%S").time()
    
    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    assert len(signals) == 0, "No fresh entry signals should be generated after 15:15:00 IST"

