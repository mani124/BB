"""Setup 3 (W-bottom / M-top) rules: window, higher low inside band, RSI margin, EMA9 trigger."""
from datetime import datetime, timedelta

import pandas as pd

from app.services import strategy_engine as se
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import SetupType, evaluate_signals

T0 = datetime(2026, 10, 8, 9, 15)
FLAT = dict(open=100.0, high=100.5, low=99.5, close=100.0, volume=2000)


def _bar(o, h, l, c, v=2000):
    return dict(open=o, high=h, low=l, close=c, volume=v)


# W: L1 at index 25 (age 6), L2 at index 28 (low 95.9 inside the band), trigger at 31
W = [
    _bar(100, 100, 92, 93, 3000), _bar(93, 98, 93, 97.5), _bar(97.5, 98.5, 97, 98),
    _bar(98, 98, 95.9, 96.2), _bar(96.2, 97, 96, 96.5), _bar(96.5, 98, 96.5, 98),
    _bar(98, 101, 98, 100.5, 5000),
]


def _df(rows, lead=25):
    recs = [dict(FLAT) for _ in range(lead)] + rows
    return calculate_indicators(pd.DataFrame(
        [dict(r, timestamp=T0 + timedelta(minutes=5 * i)) for i, r in enumerate(recs)]))


def _mirror(rows, pivot=200.0):
    """Reflect prices about `pivot` so a W becomes an M."""
    return [_bar(pivot - r["open"], pivot - r["low"], pivot - r["high"], pivot - r["close"], r["volume"])
            for r in rows]


def _s3(df, opt):
    return [s for s in evaluate_signals("NIFTY 50", df)
            if s.setup_type == SetupType.SETUP_3_REVERSAL and s.option_type == opt]


def _df_mirror(rows, lead=25):
    recs = [dict(open=100.0, high=100.5, low=99.5, close=100.0, volume=2000) for _ in range(lead)] + _mirror(rows)
    # reflect the lead too so bands line up
    for r in recs[:lead]:
        r.update(open=100.0, high=100.5, low=99.5, close=100.0)
    return calculate_indicators(pd.DataFrame(
        [dict(r, timestamp=T0 + timedelta(minutes=5 * i)) for i, r in enumerate(recs)]))


def test_valid_w_fires_and_mirror_m_fires():
    assert len(_s3(_df(W), "CE")) == 1
    assert len(_s3(_df_mirror(W), "PE")) == 1


def test_second_low_below_band_rejected():
    rows = [dict(r) for r in W]
    rows[3] = _bar(98, 98, 94.5, 96.2)  # L2 low pierces its own lower band
    assert _s3(_df(rows), "CE") == []


def test_lower_low_rejected():
    rows = [dict(r) for r in W]
    rows[0] = _bar(100, 100, 95.2, 96.0, 3000)  # shallow L1 (still below its band)
    rows[3] = _bar(98, 98, 94.0, 96.2)          # L2 undercuts L1 by far more than 0.25 ATR
    assert _s3(_df(rows), "CE") == []


def test_rsi_margin_required():
    df = _df(W)
    legs = se._reversal_legs(df, True)
    assert legs is not None
    r1, r2, _ = legs
    assert r2["rsi"] > r1["rsi"] + se.S3_RSI_MARGIN
    old = se.S3_RSI_MARGIN
    try:
        se.S3_RSI_MARGIN = 1000.0
        assert se._reversal_legs(df, True) is None
    finally:
        se.S3_RSI_MARGIN = old


def test_ema9_trigger_required():
    df = _df(W)
    assert len(_s3(df, "CE")) == 1
    df.loc[df.index[-1], "ema_9"] = df.iloc[-1]["close"] + 1.0
    assert _s3(df, "CE") == []


def test_leg1_beyond_old_12_bar_window_accepted():
    # Pad between leg 1 and leg 2 so leg 1 is 16 bars back; the old fixed 12-bar window missed this.
    pad = [_bar(98, 98.5, 97.5, 98) for _ in range(10)]
    df = _df(W[:3] + pad + W[3:])
    legs = se._reversal_legs(df, True)
    assert legs is not None
    assert len(df) - 1 - legs[0].name >= 13


def _scaled(rows, k=250.0):
    return [_bar(r["open"] * k, r["high"] * k, r["low"] * k, r["close"] * k, r["volume"]) for r in rows]


def _df_scaled(rows, lead=25, k=250.0):
    recs = [dict(open=100 * k, high=100.5 * k, low=99.5 * k, close=100 * k, volume=2000) for _ in range(lead)] + rows
    return calculate_indicators(pd.DataFrame(
        [dict(r, timestamp=T0 + timedelta(minutes=5 * i)) for i, r in enumerate(recs)]))


def test_stop_sits_atr_buffer_beyond_second_low():
    # NIFTY-scale prices so the minimum-risk floor does not bind
    df = _df_scaled(_scaled(W))
    sig = _s3(df, "CE")[0]
    legs = se._reversal_legs(df, True)
    expected = round(legs[1]["low"] - se.S3_SL_ATR_BUFFER * se._recent_atr(df), 2)
    assert sig.stop_loss == expected
    # leg 1 is deeper than leg 2 here; the stop is no longer anchored to it
    assert sig.stop_loss > legs[0]["low"]


def test_m_top_stop_above_second_high():
    df = _df_scaled(_scaled(_mirror(W, pivot=200.0), k=250.0))
    sig = _s3(df, "PE")[0]
    legs = se._reversal_legs(df, False)
    assert sig.stop_loss == round(legs[1]["high"] + se.S3_SL_ATR_BUFFER * se._recent_atr(df), 2)
    assert sig.stop_loss < legs[0]["high"] or legs[0]["high"] <= legs[1]["high"]
