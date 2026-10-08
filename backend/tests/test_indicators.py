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

def test_rsi_extremes_all_gain_and_all_loss():
    # Relentless rally: price goes strictly up on every bar
    dates = pd.date_range("2026-10-08 09:15", periods=25, freq="5min")
    df_rally = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0 + i for i in range(25)],
        "high": [101.0 + i for i in range(25)],
        "low": [99.5 + i for i in range(25)],
        "close": [100.5 + i for i in range(25)],
        "volume": [1000] * 25
    })
    res_rally = calculate_indicators(df_rally)
    assert res_rally["rsi"].iloc[-1] == 100.0

    # Relentless selloff: price goes strictly down on every bar
    df_drop = pd.DataFrame({
        "timestamp": dates,
        "open": [200.0 - i for i in range(25)],
        "high": [200.5 - i for i in range(25)],
        "low": [199.0 - i for i in range(25)],
        "close": [199.5 - i for i in range(25)],
        "volume": [1000] * 25
    })
    res_drop = calculate_indicators(df_drop)
    assert res_drop["rsi"].iloc[-1] == 0.0

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
    # On completely flat data, percent_b should be neutral 0.5
    assert result["percent_b"].iloc[-1] == 0.5
    assert result["bandwidth"].iloc[-1] == 0.0
    assert result["rsi"].iloc[-1] == 50.0
    assert result["vwap"].iloc[-1] == 100.0

def test_empty_dataframe():
    """Verify empty DataFrame returns all required indicator columns without crashing."""
    df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    result = calculate_indicators(df)
    expected_cols = [
        "bb_middle", "bb_std", "bb_upper", "bb_lower",
        "bandwidth", "bandwidth_20_min", "percent_b",
        "vwap", "rsi", "ema_9", "adx", "or_high", "or_low"
    ]
    for col in expected_cols:
        assert col in result.columns

def test_short_dataframe_under_5_rows():
    """Verify DataFrame with < 5 rows returns all indicator columns and valid values."""
    dates = pd.date_range("2026-10-08 09:15", periods=3, freq="5min")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0, 101.0, 102.0],
        "high": [101.5, 102.5, 103.5],
        "low": [99.5, 100.5, 101.5],
        "close": [101.0, 102.0, 103.0],
        "volume": [1000, 1500, 2000]
    })
    result = calculate_indicators(df)
    assert len(result) == 3
    assert "percent_b" in result.columns
    assert "vwap" in result.columns
    assert "or_high" in result.columns
    assert result["or_high"].iloc[0] == 103.5
    assert result["or_low"].iloc[0] == 99.5

def test_timezone_aware_timestamps():
    """Verify tz-aware UTC timestamps are converted to IST and don't trigger numpy type errors."""
    # 03:45 UTC is 09:15 IST
    dates_utc = pd.date_range("2026-10-08 03:45", periods=10, freq="5min", tz="UTC")
    df = pd.DataFrame({
        "timestamp": dates_utc,
        "open": [100.0 + i for i in range(10)],
        "high": [101.0 + i for i in range(10)],
        "low": [99.0 + i for i in range(10)],
        "close": [100.5 + i for i in range(10)],
        "volume": [1000] * 10
    })
    result = calculate_indicators(df)
    # The first 3 bars (09:15, 09:20, 09:25 IST) determine ORB
    assert result["or_high"].iloc[0] == 103.0  # max high of bars 0, 1, 2
    assert result["or_low"].iloc[0] == 99.0   # min low of bars 0, 1, 2

def test_multi_day_session_vwap_reset():
    """Verify VWAP resets per session date."""
    d1 = pd.date_range("2026-10-07 09:15", periods=5, freq="5min")
    d2 = pd.date_range("2026-10-08 09:15", periods=5, freq="5min")
    df = pd.DataFrame({
        "timestamp": list(d1) + list(d2),
        "open": [100.0] * 5 + [200.0] * 5,
        "high": [100.0] * 5 + [200.0] * 5,
        "low": [100.0] * 5 + [200.0] * 5,
        "close": [100.0] * 5 + [200.0] * 5,
        "volume": [1000] * 10
    })
    result = calculate_indicators(df)
    # Day 1 VWAP should be 100.0
    assert result["vwap"].iloc[0] == 100.0
    assert result["vwap"].iloc[4] == 100.0
    # Day 2 VWAP should reset immediately to 200.0
    assert result["vwap"].iloc[5] == 200.0
    assert result["vwap"].iloc[9] == 200.0

def test_percent_b_breakouts():
    """Verify %B > 1.0 above upper band and %B < 0.0 below lower band."""
    df = generate_sample_candles(30)
    # Massive breakout candle
    df.loc[29, "close"] = df["close"].iloc[10:29].max() + 50.0
    df.loc[29, "high"] = df.loc[29, "close"] + 1.0
    result = calculate_indicators(df)
    assert result["percent_b"].iloc[29] > 1.0

    # Massive breakdown candle
    df.loc[29, "close"] = df["close"].iloc[10:29].min() - 50.0
    df.loc[29, "low"] = df.loc[29, "close"] - 1.0
    result_down = calculate_indicators(df)
    assert result_down["percent_b"].iloc[29] < 0.0

def test_adx_responsive_trend():
    """Verify that a sustained 25-candle trend generates ADX > 25."""
    dates = pd.date_range("2026-10-08 09:15", periods=25, freq="5min")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0 + i * 2.0 for i in range(25)],
        "high": [101.5 + i * 2.0 for i in range(25)],
        "low": [99.5 + i * 2.0 for i in range(25)],
        "close": [101.0 + i * 2.0 for i in range(25)],
        "volume": [5000] * 25
    })
    result = calculate_indicators(df)
    assert result["adx"].iloc[-1] > 25.0

def test_unsorted_timestamps():
    """Verify calculate_indicators sorts timestamps chronologically."""
    df = generate_sample_candles(25)
    df_shuffled = df.sample(frac=1.0, random_state=42)
    result = calculate_indicators(df_shuffled)
    assert result["timestamp"].is_monotonic_increasing

def test_bandwidth_20_min_no_warmup_zero_pollution():
    """Verify bandwidth_20_min is not polluted by 0.0 warmup values at bar 19 and bar 20."""
    df = generate_sample_candles(25)
    result = calculate_indicators(df)
    
    bw_19 = result["bandwidth"].iloc[19]
    bw_20 = result["bandwidth"].iloc[20]
    bw_min_20 = result["bandwidth_20_min"].iloc[20]
    
    assert bw_min_20 > 0.0
    assert pytest.approx(bw_min_20, rel=1e-5) == min(bw_19, bw_20)

def test_vwap_nan_volume_coercion():
    """Verify session VWAP safely coerces NaN volumes to 0 without NaN propagation."""
    df = generate_sample_candles(15)
    df.loc[3, "volume"] = np.nan
    df.loc[7, "volume"] = np.nan
    result = calculate_indicators(df)
    assert not result["vwap"].isna().any()
    assert (result["vwap"] > 0).all()


