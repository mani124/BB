import numpy as np
import pandas as pd
from app.services.indicators import calculate_indicators, INDICATOR_COLUMNS


def test_extreme_25_sigma_bands_calculation():
    # 25 bars of linear close prices
    closes = np.linspace(100, 120, 25)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-10-10 09:15", periods=25, freq="5min"),
        "open": closes - 0.5,
        "high": closes + 1.0,
        "low": closes - 1.0,
        "close": closes,
        "volume": [1000] * 25
    })
    res = calculate_indicators(df)
    assert "bb_upper_25" in res.columns
    assert "bb_lower_25" in res.columns
    last = res.iloc[-1]
    expected_upper_25 = last["bb_middle"] + 2.5 * last["bb_std"]
    expected_lower_25 = last["bb_middle"] - 2.5 * last["bb_std"]
    assert np.isclose(last["bb_upper_25"], expected_upper_25)
    assert np.isclose(last["bb_lower_25"], expected_lower_25)
    assert last["bb_upper_25"] > last["bb_upper"]
    assert last["bb_lower_25"] < last["bb_lower"]


def test_extreme_25_sigma_bands_empty_df():
    assert "bb_upper_25" in INDICATOR_COLUMNS
    assert "bb_lower_25" in INDICATOR_COLUMNS
    empty = calculate_indicators(pd.DataFrame())
    assert "bb_upper_25" in empty.columns
    assert "bb_lower_25" in empty.columns
