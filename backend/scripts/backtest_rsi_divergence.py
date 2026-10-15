"""Replay the bullish RSI divergence detector over recorded 5m candles and report outcomes.

Usage: python -m scripts.backtest_rsi_divergence candles.csv [--no-band]
       python -m scripts.backtest_rsi_divergence --synthetic        (harness smoke test ONLY, not evidence)
CSV columns: timestamp,open,high,low,close,volume (one symbol, 5m bars, oldest first; a `symbol`
column is optional and, if present, each symbol is replayed separately).

Outcome model (spot, long only, deliberately pessimistic): enter at the OPEN of the bar after the
confirming candle, stop = detector stop, target = entry + R x risk, stop wins if both hit in one bar,
forced exit at the session's last bar close or after MAX_HOLD bars. Baseline = the same exit rule
applied to every bullish-trigger candle that has no divergence, so the edge (if any) is visible.
"""
import sys

import numpy as np
import pandas as pd

from app.services.indicators import calculate_indicators
from app.services.rsi_divergence import detect_bullish_rsi_divergence, _is_trigger

MAX_HOLD = 24
TAIL = 80
RS = (1.0, 1.5)


def simulate(ind: pd.DataFrame, t: int, stop: float, r_mult: float):
    """Return R multiple realised (+r_mult, -1, or fractional at timed exit), or None if no next bar."""
    if t + 1 >= len(ind):
        return None
    entry = float(ind["open"].iloc[t + 1])
    risk = entry - stop
    if risk <= 0:
        return None
    target = entry + r_mult * risk
    day = ind["timestamp"].iloc[t + 1].date()
    for j in range(t + 1, min(len(ind), t + 1 + MAX_HOLD)):
        row = ind.iloc[j]
        if row["timestamp"].date() != day:
            return (float(ind["close"].iloc[j - 1]) - entry) / risk
        if row["low"] <= stop:
            return -1.0
        if row["high"] >= target:
            return r_mult
        if j + 1 >= len(ind) or ind["timestamp"].iloc[j + 1].date() != day:
            return (float(row["close"]) - entry) / risk
    return (float(ind["close"].iloc[min(len(ind), t + 1 + MAX_HOLD) - 1]) - entry) / risk


def scan(df: pd.DataFrame, require_band: bool = True):
    ind = calculate_indicators(df)
    hits, base = [], []
    for t in range(40, len(ind)):
        w = ind.iloc[max(0, t + 1 - TAIL):t + 1].reset_index(drop=True)
        hit = detect_bullish_rsi_divergence(w, require_lower_band=require_band)
        if hit:
            hits.append((t, hit.stop_loss))
        elif _is_trigger(w, len(w) - 1) and w["low"].iloc[-1] <= w["bb_lower"].iloc[-3:].max():
            # baseline: bullish trigger candle that follows a lower-band touch, no divergence required
            base.append((t, round(float(w["low"].iloc[-6:].min()) - max(0.5, 0.0005 * float(w["close"].iloc[-1])), 2)))
    return ind, hits, base


def synthetic(days: int = 40, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows, price = [], 1000.0
    for d in range(days):
        day = pd.Timestamp("2026-01-05", tz="Asia/Kolkata") + pd.Timedelta(days=d)
        if day.weekday() >= 5:
            continue
        ts = day + pd.Timedelta(hours=9, minutes=15)
        for i in range(75):
            o = price
            c = o * (1 + rng.normal(0, 0.0012))
            h, l = max(o, c) * (1 + abs(rng.normal(0, 0.0004))), min(o, c) * (1 - abs(rng.normal(0, 0.0004)))
            rows.append((ts + pd.Timedelta(minutes=5 * i), o, h, l, c, 1000))
            price = c
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    args = sys.argv[1:]
    band = "--no-band" not in args
    if "--synthetic" in args:
        frames = {"SYNTHETIC": synthetic()}
        print("SYNTHETIC random walk: harness smoke test only, says nothing about the setup.")
    else:
        raw = pd.read_csv([a for a in args if not a.startswith("--")][0], parse_dates=["timestamp"])
        frames = dict(tuple(raw.groupby("symbol"))) if "symbol" in raw.columns else {"X": raw}
    tot_h, tot_b = [], []
    for name, f in frames.items():
        ind, hits, base = scan(f.drop(columns=["symbol"], errors="ignore").reset_index(drop=True), band)
        tot_h.append((ind, hits)); tot_b.append((ind, base))
        print(f"{name}: {len(ind)} bars, {len(hits)} divergence signals, {len(base)} baseline triggers")
    for lbl, tot in (("DIVERGENCE", tot_h), ("BASELINE  ", tot_b)):
        for r in RS:
            res = [x for ind, sig in tot for x in (simulate(ind, t, sl, r) for t, sl in sig) if x is not None]
            if res:
                a = np.array(res)
                print(f"{lbl} @ {r}R: n={len(a)} win={(a > 0).mean()*100:.1f}% avg_R={a.mean():+.3f}")
            else:
                print(f"{lbl} @ {r}R: 0 trades")
