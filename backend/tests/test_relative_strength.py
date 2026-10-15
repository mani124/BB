import pandas as pd
import pytest
from datetime import datetime, timedelta

from app.services.indicators import calculate_indicators
from app.services.relative_strength import evaluate_relative_strength
from app.services.strategy_engine import SetupType

START = datetime(2026, 10, 15, 9, 15)


def _bars(closes, opens=None, spread=0.2):
    rows = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = opens[i] if opens else prev
        rows.append({
            "timestamp": START + timedelta(minutes=5 * i),
            "open": o, "high": max(o, c) + spread, "low": min(o, c) - spread,
            "close": c, "volume": 1000,
        })
        prev = c
    return pd.DataFrame(rows)


def _nifty(n, drift=0.0):
    base = 25000.0
    return _bars([base * (1 + drift * i / max(1, n - 1)) for i in range(n)], spread=1.0)


def _stock_with_pullback(sign=1):
    """Steady move away from the 9 EMA, then one pullback bar that touches it and closes back."""
    closes = [100.0 + sign * 0.15 * i for i in range(14)]
    df = _bars(closes)
    ind = calculate_indicators(df)
    ema = float(ind["ema_9"].iloc[-1])
    last = closes[-1]
    # pullback bar: dips (rises for PE) through the EMA, closes back on the trend side
    if sign > 0:
        row = {"open": last, "high": last + 0.1, "low": ema - 0.05, "close": last + 0.3}
    else:
        row = {"open": last, "high": ema + 0.05, "low": last - 0.1, "close": last - 0.3}
    row.update(timestamp=START + timedelta(minutes=5 * len(closes)), volume=1000)
    return calculate_indicators(pd.concat([df, pd.DataFrame([row])], ignore_index=True))


def test_ce_signal_on_first_pullback_with_nifty_flat():
    df = _stock_with_pullback(+1)
    sigs = evaluate_relative_strength("RELIANCE", df, _nifty(len(df), 0.0), stock_bias="BULLISH")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_type == SetupType.SETUP_9_RELATIVE_STRENGTH
    assert s.option_type == "CE" and s.is_confirmed
    assert s.stop_loss < float(df["low"].iloc[-1])
    assert s.target_1 > s.entry_price
    assert s.indicators_snapshot["rs_spread_pct"] >= 0.75


def test_ce_signal_when_nifty_falling():
    df = _stock_with_pullback(+1)
    assert len(evaluate_relative_strength("RELIANCE", df, _nifty(len(df), -0.004), stock_bias="BULLISH")) == 1


def test_no_signal_when_nifty_rising_with_stock():
    df = _stock_with_pullback(+1)
    assert evaluate_relative_strength("RELIANCE", df, _nifty(len(df), 0.01), stock_bias="BULLISH") == []


def test_pe_signal_when_stock_falls_and_nifty_rises():
    df = _stock_with_pullback(-1)
    sigs = evaluate_relative_strength("RELIANCE", df, _nifty(len(df), 0.004), stock_bias="BEARISH")
    assert len(sigs) == 1 and sigs[0].option_type == "PE"
    assert sigs[0].stop_loss > float(df["high"].iloc[-1])
    assert sigs[0].target_1 < sigs[0].entry_price


def test_bias_must_match_direction():
    df = _stock_with_pullback(+1)
    nifty = _nifty(len(df), 0.0)
    assert evaluate_relative_strength("RELIANCE", df, nifty, stock_bias="BEARISH") == []
    assert evaluate_relative_strength("RELIANCE", df, nifty, stock_bias=None) == []


def test_no_signal_for_indices_or_missing_index_data():
    df = _stock_with_pullback(+1)
    assert evaluate_relative_strength("NIFTY 50", df, _nifty(len(df)), stock_bias="BULLISH") == []
    assert evaluate_relative_strength("RELIANCE", df, None, stock_bias="BULLISH") == []


def test_red_pullback_bar_is_not_a_confirmation():
    df = _stock_with_pullback(+1)
    i = len(df) - 1
    df.loc[i, "open"] = df.loc[i, "close"] + 0.2  # bar closes below its open
    assert evaluate_relative_strength("RELIANCE", df, _nifty(len(df)), stock_bias="BULLISH") == []


def test_only_first_pullback():
    df = _stock_with_pullback(+1)
    # an earlier bar (after relative strength was already established) also touched the EMA
    j = len(df) - 4
    df.loc[j, "low"] = df.loc[j, "ema_9"] - 0.05
    assert evaluate_relative_strength("RELIANCE", df, _nifty(len(df)), stock_bias="BULLISH") == []


def test_outside_session_window():
    df = _stock_with_pullback(+1)
    # move the series so the pullback bar starts at 15:15, past the 15:10 last bar start
    shift = START.replace(hour=15, minute=15) - df["timestamp"].iloc[-1]
    late = df.copy()
    late["timestamp"] = late["timestamp"] + shift
    nifty = _nifty(len(df))
    nifty["timestamp"] = nifty["timestamp"] + shift
    assert evaluate_relative_strength("RELIANCE", late, nifty, stock_bias="BULLISH") == []
    early = df.iloc[:5].copy()  # last bar starts 09:35, before the 09:45 window
    assert evaluate_relative_strength("RELIANCE", early, _nifty(5), stock_bias="BULLISH") == []


def test_no_signal_when_nifty_lags_the_stock_bar():
    df = _stock_with_pullback(+1)
    nifty = _nifty(len(df)).iloc[:-1]  # NIFTY has not closed the signal bar yet
    assert evaluate_relative_strength("RELIANCE", df, nifty, stock_bias="BULLISH") == []


def test_duplicate_or_unordered_nifty_bars_do_not_raise():
    df = _stock_with_pullback(+1)
    nifty = _nifty(len(df))
    messy = pd.concat([nifty.iloc[[5]], nifty, nifty.iloc[[3]]]).reset_index(drop=True)
    assert len(evaluate_relative_strength("RELIANCE", df, messy, stock_bias="BULLISH")) == 1
