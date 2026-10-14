"""RSI / ATR / ADX must match a plain-Python textbook Wilder implementation."""
import numpy as np
import pandas as pd
import pytest

from app.services.indicators import calculate_indicators


def _bars(n=90, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.8, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-10-08 09:15", periods=n, freq="5min"),
        "open": open_, "high": high, "low": low, "close": close, "volume": 1000,
    })


def _ref_rsi(close, p=14):
    out = [np.nan] * len(close)
    d = np.diff(close)
    g = np.where(d > 0, d, 0.0)
    l = np.where(d < 0, -d, 0.0)
    ag, al = g[:p].mean(), l[:p].mean()
    out[p] = 100 * ag / (ag + al)
    for i in range(p, len(d)):
        ag = (ag * (p - 1) + g[i]) / p
        al = (al * (p - 1) + l[i]) / p
        out[i + 1] = 100 * ag / (ag + al)
    return np.array(out)


def _ref_adx(high, low, close, p=14):
    n = len(close)
    tr = np.zeros(n); pdm = np.zeros(n); mdm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        up, dn = high[i] - high[i - 1], low[i - 1] - low[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    atr, ap, am = tr[1:p + 1].mean(), pdm[1:p + 1].mean(), mdm[1:p + 1].mean()
    dx = {}
    plus_di = np.full(n, np.nan); minus_di = np.full(n, np.nan)
    for i in range(p, n):
        if i > p:
            atr = (atr * (p - 1) + tr[i]) / p
            ap = (ap * (p - 1) + pdm[i]) / p
            am = (am * (p - 1) + mdm[i]) / p
        plus_di[i], minus_di[i] = 100 * ap / atr, 100 * am / atr
        dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i])
    adx = np.full(n, np.nan)
    seed = p + p - 1
    adx[seed] = np.mean([dx[i] for i in range(p, seed + 1)])
    for i in range(seed + 1, n):
        adx[i] = (adx[i - 1] * (p - 1) + dx[i]) / p
    return adx, plus_di, minus_di


def test_rsi_matches_textbook_wilder():
    df = _bars()
    got = calculate_indicators(df)["rsi"].to_numpy()
    ref = _ref_rsi(df["close"].to_numpy())
    mask = ~np.isnan(ref)
    np.testing.assert_allclose(got[mask], ref[mask], atol=1e-9)
    assert (got[~mask] == 50.0).all()          # undefined warm-up stays neutral


def test_adx_and_di_match_textbook_wilder():
    df = _bars()
    res = calculate_indicators(df)
    adx, pdi, mdi = _ref_adx(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy())
    ok = ~np.isnan(adx)
    np.testing.assert_allclose(res["adx"].to_numpy()[ok], adx[ok], atol=1e-9)
    ok_di = ~np.isnan(pdi)
    np.testing.assert_allclose(res["plus_di"].to_numpy()[ok_di], pdi[ok_di], atol=1e-9)
    np.testing.assert_allclose(res["minus_di"].to_numpy()[ok_di], mdi[ok_di], atol=1e-9)


def test_short_series_is_safe():
    df = _bars(n=10)
    res = calculate_indicators(df)
    assert (res["rsi"] == 50.0).all() and (res["adx"] == 20.0).all()
