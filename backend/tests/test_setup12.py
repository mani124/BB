from datetime import datetime, timedelta

import pandas as pd

from app.services.indicators import calculate_indicators
from app.services.setup12 import evaluate_adx_ema_cross
from app.services.setup_switches import block_reason, DEFAULT_MODES
from app.services.strategy_engine import SetupType

START = datetime(2026, 10, 15, 9, 15)


def _df(closes, start=START):
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": prev,
                     "high": max(prev, c) + 0.3, "low": min(prev, c) - 0.3, "close": c, "volume": 1000})
        prev = c
    return calculate_indicators(pd.DataFrame(rows))


def _cross_df(sign=1, **over):
    """Trend, a 4-bar pullback through the 20 EMA, then a sharp bar back across it.
    Gate columns are pinned so each test changes exactly one gate."""
    base = [100 + sign * 1.0 * i for i in range(32)]
    last = base[-1]
    closes = base + [last - sign * d for d in (6, 12, 14, 13)] + [last - sign * 8]
    df = _df(closes)
    cols = {"adx": 30.0, "plus_di": 30.0 if sign > 0 else 10.0, "minus_di": 10.0 if sign > 0 else 30.0, "atr": 3.0}
    back = over.pop("adx_back", 25.0)
    cols.update(over)
    for k, v in cols.items():
        df[k] = v
    df.loc[df.index[-4], "adx"] = back
    return df


def test_ce_cross_fires_with_adx_gate():
    df = _cross_df(+1)
    e = df["close"].ewm(span=20, adjust=False).mean()
    assert df["close"].iloc[-2] <= e.iloc[-2] and df["close"].iloc[-1] > e.iloc[-1]
    sigs = evaluate_adx_ema_cross("NIFTY 50", df)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_type == SetupType.SETUP_12_ADX_EMA_CROSS and s.option_type == "CE" and s.is_confirmed
    assert s.stop_loss < float(df["low"].iloc[-1])
    assert s.target_1 > s.entry_price


def test_pe_cross_mirror():
    df = _cross_df(-1)
    sigs = evaluate_adx_ema_cross("NIFTY 50", df)
    assert len(sigs) == 1 and sigs[0].option_type == "PE"
    assert sigs[0].stop_loss > float(df["high"].iloc[-1])


def test_adx_below_20_blocks():
    assert evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, adx=19.0)) == []


def test_adx_not_rising_blocks():
    assert evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, adx_back=35.0)) == []
    assert len(evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, adx_back=25.0))) == 1


def test_di_direction_blocks():
    assert evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, plus_di=10.0, minus_di=30.0)) == []


def test_cross_distance_band():
    assert evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, atr=0.5)) == []  # chased: > 1 ATR beyond EMA
    assert evaluate_adx_ema_cross("NIFTY 50", _cross_df(+1, atr=500.0)) == []  # marginal: < 0.1 ATR


def test_no_signal_in_chop_adx_low():
    closes = [100 + (0.4 if i % 2 else -0.4) for i in range(26)] + [100.6]
    df = _df(closes)
    assert evaluate_adx_ema_cross("NIFTY 50", df) == []


def test_no_signal_before_20_session_bars():
    df = _df([100 - 1.0 * i for i in range(14)] + [80.0, 90.0])
    assert evaluate_adx_ema_cross("NIFTY 50", df) == []


def test_no_signal_after_cutoff():
    df = _df([100 for _ in range(10)] + [100 - 1.0 * i for i in range(1, 17)] + [86.0, 92.0],
             start=datetime(2026, 10, 15, 13, 40))
    assert evaluate_adx_ema_cross("NIFTY 50", df) == []


def test_no_signal_when_di_disagrees_or_no_cross():
    df = _df([100 - 1.0 * i for i in range(26)])  # trending down, never crosses up
    assert evaluate_adx_ema_cross("NIFTY 50", df) == []


def test_default_switch_is_index_only():
    assert DEFAULT_MODES["12"] == "index"
    assert block_reason(DEFAULT_MODES, SetupType.SETUP_12_ADX_EMA_CROSS, "RELIANCE")
    assert block_reason(DEFAULT_MODES, SetupType.SETUP_12_ADX_EMA_CROSS, "NIFTY 50") is None
