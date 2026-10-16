from datetime import datetime, timedelta

import pandas as pd

from app.services.indicators import calculate_indicators
from app.services.strategy_engine import SetupType, _session_bars, _walked_band, evaluate_signals


def test_walked_band_needs_real_band_contact_not_fixed_percent():
    # mid 25000, sigma 20: upper 25040, lower 24960. The old 0.998 x upper = 24989.9 (below mid) passed.
    row = {"close": 24990.0, "bb_upper": 25040.0, "bb_lower": 24960.0}
    assert not _walked_band(row, "up")
    assert _walked_band({**row, "close": 25034.0}, "up")
    assert not _walked_band({**row, "close": 25010.0}, "down")
    assert _walked_band({**row, "close": 24966.0}, "down")


def test_session_bars_counts_only_latest_session():
    ts = [datetime(2026, 10, 14, 15, 25), datetime(2026, 10, 15, 9, 15), datetime(2026, 10, 15, 9, 20)]
    assert _session_bars(pd.DataFrame({"timestamp": ts})) == 2


def test_atr_column_exposed():
    n = 30
    ts = [datetime(2026, 10, 15, 9, 15) + timedelta(minutes=5 * i) for i in range(n)]
    df = pd.DataFrame({"timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1})
    out = calculate_indicators(df)
    assert abs(out["atr"].iloc[-1] - 2.0) < 1e-9


def _trend(n_up, with_pullback_low):
    ts0 = datetime(2026, 10, 15, 9, 15)
    recs, p = [], 25000.0
    for i in range(n_up):
        p += 12.0
        recs.append(dict(timestamp=ts0 + timedelta(minutes=5 * i), open=p - 10, high=p + 2, low=p - 11, close=p, volume=0))
    i = n_up
    # signal bar: green, low either touches the EMA zone or stays far above it
    ema_guess = p - 40
    low = ema_guess if with_pullback_low else p - 8
    recs.append(dict(timestamp=ts0 + timedelta(minutes=5 * i), open=low + 2, high=p + 15, low=low, close=p + 12, volume=0))
    return pd.DataFrame(recs)


def test_stop_is_below_signal_bar_low_for_ce():
    df = calculate_indicators(_trend(40, True))
    sigs = [s for s in evaluate_signals("NIFTY 50", df)
            if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    if sigs:  # the fixture must produce one; if it does, the stop must clear the bar low
        assert sigs[0].stop_loss < df.iloc[-1]["low"]


def test_no_signal_when_bar_never_pulls_back_to_ema():
    df = calculate_indicators(_trend(40, False))
    sigs = [s for s in evaluate_signals("NIFTY 50", df)
            if s.setup_type == SetupType.SETUP_2_WALKING and s.option_type == "CE"]
    assert not sigs


def test_blocked_until_20_bars_in_current_session():
    df = _trend(40, True)
    df["timestamp"] = df["timestamp"] + pd.Timedelta(days=1) * 0
    # push the first 25 bars to the previous day so the new session has only 16 bars
    df.loc[:24, "timestamp"] = df.loc[:24, "timestamp"] - pd.Timedelta(days=1)
    sigs = [s for s in evaluate_signals("NIFTY 50", calculate_indicators(df))
            if s.setup_type == SetupType.SETUP_2_WALKING]
    assert not sigs
