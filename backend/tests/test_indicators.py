import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators import calculate_indicators

def generate_sample_candles(n: int = 50, base_price: float = 100.0) -> pd.DataFrame:
    """Generate realistic OHLCV candle dataframe."""
    np.random.seed(42)
    start_time = datetime(2026, 10, 8, 9, 15)
    records = []
    curr_price = base_price
    
    for i in range(n):
        ts = start_time + timedelta(minutes=5 * i)
        step = np.random.normal(0, 1)
        open_p = curr_price
        close_p = open_p + step
        high_p = max(open_p, close_p) + abs(np.random.normal(0.5, 0.2))
        low_p = min(open_p, close_p) - abs(np.random.normal(0.5, 0.2))
        vol = int(np.random.uniform(1000, 5000))
        records.append({
            "timestamp": ts,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": vol
        })
        curr_price = close_p
        
    return pd.DataFrame(records)

def test_bollinger_bands_calculation():
    df = generate_sample_candles(50)
    result = calculate_indicators(df)
    
    assert "bb_middle" in result.columns
    assert "bb_upper" in result.columns
    assert "bb_lower" in result.columns
    assert "bandwidth" in result.columns
    assert "percent_b" in result.columns
    
    # Check on row 30 (after warm-up)
    row = result.iloc[30]
    expected_mid = df["close"].iloc[11:31].mean()
    expected_std = df["close"].iloc[11:31].std(ddof=0)
    
    assert pytest.approx(row["bb_middle"], rel=1e-3) == expected_mid
    assert pytest.approx(row["bb_upper"], rel=1e-3) == expected_mid + 2 * expected_std
    assert pytest.approx(row["bb_lower"], rel=1e-3) == expected_mid - 2 * expected_std
    assert row["bandwidth"] > 0

def test_vwap_and_rsi():
    df = generate_sample_candles(50)
    result = calculate_indicators(df)
    
    assert "vwap" in result.columns
    assert "rsi" in result.columns
    assert "ema_9" in result.columns
    assert "adx" in result.columns
    
    # RSI must be bounded between 0 and 100
    valid_rsi = result["rsi"].dropna()
    assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()
    
    # VWAP must be positive and close to price range
    valid_vwap = result["vwap"].dropna()
    assert (valid_vwap > 50).all() and (valid_vwap < 200).all()

def test_opening_range_calculation():
    df = generate_sample_candles(50)
    result = calculate_indicators(df)
    
    assert "or_high" in result.columns
    assert "or_low" in result.columns
    
    # In first 3 candles (09:15, 09:20, 09:25), or_high is the max high of those candles
    first_3_high = df["high"].iloc[:3].max()
    first_3_low = df["low"].iloc[:3].min()
    
    assert pytest.approx(result["or_high"].iloc[10], rel=1e-3) == first_3_high
    assert pytest.approx(result["or_low"].iloc[10], rel=1e-3) == first_3_low

def test_handles_zero_volume_and_flat_data():
    """Verify zero division is safely handled."""
    records = []
    for i in range(30):
        records.append({
            "timestamp": datetime(2026, 10, 8, 9, 15) + timedelta(minutes=5 * i),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 0
        })
    df = pd.DataFrame(records)
    result = calculate_indicators(df)
    assert not result["bandwidth"].isna().all()
