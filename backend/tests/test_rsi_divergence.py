"""Bullish RSI divergence detector: swing rules, no look-ahead, one-shot trigger, config gate."""
import numpy as np
import pandas as pd

from app.core.config import settings
from app.services import rsi_divergence as rd
from app.services.rsi_divergence import detect_bullish_rsi_divergence, swing_low_indices

N = 40
L1, L2 = 22, 29


def make_frame(n=N, low2=94.0, rsi1=25.0, rsi2=33.0, band_touch=True, trigger=True):
    """Flat ~100 market with a pivot low at L1 (low 95) and L2 (low2), confirming candle last."""
    ts = pd.date_range("2026-10-14 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    low = np.full(n, 99.0)
    low[L1], low[L2] = 95.0, low2
    low[L1 - 2:L1] = [97.0, 96.0]; low[L1 + 1:L1 + 3] = [96.0, 97.0]
    low[L2 - 2:L2] = [97.0, 96.0]; low[L2 + 1:L2 + 3] = [95.5, 96.5]
    low[L1 + 3:L2 - 2] = 98.0
    rsi = np.full(n, 50.0); rsi[L1], rsi[L2] = rsi1, rsi2
    df = pd.DataFrame({
        "timestamp": ts, "open": low + 1.0, "close": low + 1.2, "high": low + 2.0, "low": low,
        "rsi": rsi, "bb_lower": np.where(np.arange(n) == L1, 95.5 if band_touch else 90.0, 90.0),
        "bb_middle": 100.0,
    })
    # quiet bars (bearish) except the confirming candle at the end
    df["close"] = df["open"] - 0.1
    if trigger:
        last = n - 1
        prev_high = df["high"].iloc[last - 1]
        df.loc[last, "open"] = prev_high - 0.5
        df.loc[last, "low"] = prev_high - 0.6
        df.loc[last, "close"] = prev_high + 0.3
        df.loc[last, "high"] = prev_high + 0.4
    return df


def test_swing_low_needs_k_bars_on_both_sides():
    s = pd.Series([5, 4, 3, 4, 5, 4.5, 4.4])
    assert swing_low_indices(s, k=2) == [2]
    assert swing_low_indices(s.iloc[:4], k=2) == []  # not confirmed yet: no look-ahead


def test_hit_on_clean_bullish_divergence():
    hit = detect_bullish_rsi_divergence(make_frame(n=L2 + 4))
    assert hit is not None
    assert (hit.l1_index, hit.l2_index) == (L1, L2)
    assert hit.low2 < hit.low1 and hit.rsi2 > hit.rsi1
    assert hit.stop_loss < hit.low2 and hit.index == L2 + 3


def test_no_hit_without_confirming_candle():
    assert detect_bullish_rsi_divergence(make_frame(n=L2 + 4, trigger=False)) is None


def test_no_hit_when_price_not_lower_low():
    assert detect_bullish_rsi_divergence(make_frame(n=L2 + 4, low2=95.5)) is None


def test_no_hit_when_rsi_not_higher_enough():
    assert detect_bullish_rsi_divergence(make_frame(n=L2 + 4, rsi2=26.0)) is None


def test_no_hit_when_first_low_not_oversold():
    assert detect_bullish_rsi_divergence(make_frame(n=L2 + 4, rsi1=45.0, rsi2=55.0)) is None


def test_band_requirement_is_optional():
    df = make_frame(n=L2 + 4, band_touch=False)
    assert detect_bullish_rsi_divergence(df) is None
    assert detect_bullish_rsi_divergence(df, require_lower_band=False) is not None


def test_stale_pivot_is_ignored():
    assert detect_bullish_rsi_divergence(make_frame(n=L2 + 10)) is None  # beyond max_confirm_wait


def test_fires_only_once_per_pivot():
    df = make_frame(n=L2 + 5)
    # make the previous bar (first post-confirmation bar) also a trigger candle -> last one is not first
    j = len(df) - 2
    df.loc[j, "open"] = df["high"].iloc[j - 1] - 0.5
    df.loc[j, "close"] = df["high"].iloc[j - 1] + 0.2
    assert detect_bullish_rsi_divergence(df.iloc[:-1]) is not None
    assert detect_bullish_rsi_divergence(df) is None


def test_lows_on_different_sessions_do_not_pair():
    df = make_frame(n=L2 + 4)
    df.loc[:L1, "timestamp"] = df.loc[:L1, "timestamp"] - pd.Timedelta(days=1)
    assert detect_bullish_rsi_divergence(df) is None


def test_gate_is_off_by_default_and_opens_with_flag(monkeypatch):
    df = make_frame(n=L2 + 4)
    assert settings.RSI_DIVERGENCE_ENABLED is False
    assert rd.detect_if_enabled(df) is None
    monkeypatch.setattr(settings, "RSI_DIVERGENCE_ENABLED", True)
    assert rd.detect_if_enabled(df) is not None


def test_detector_is_not_referenced_by_live_paths():
    import pathlib
    app = pathlib.Path(rd.__file__).resolve().parents[1]
    users = [p.name for p in app.rglob("*.py") if p.name != "rsi_divergence.py" and "rsi_divergence" in p.read_text()]
    assert users == []
