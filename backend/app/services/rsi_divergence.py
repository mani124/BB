"""Bullish RSI divergence detector (research setup, NOT wired into live entries).

Pure functions over an indicator frame (output of ``calculate_indicators``). The caller must pass
CLOSED bars only: the last row is treated as the confirming candle, so never include the forming bar.

Pattern (see docs/SETUPS_SPECIFICATION.md, section 12):
  * two swing lows L1 (older) and L2 (newer), ``min_gap``..``max_gap`` bars apart, same session;
  * price makes a lower low (low2 < low1) while Wilder RSI makes a higher low (rsi2 >= rsi1 + margin);
  * RSI at the first low is oversold-ish (<= ``rsi_first_max``);
  * optionally L1 pierced the lower Bollinger Band (the snap-back context of setups 6-8);
  * a swing low is only known ``pivot_k`` bars after it printed, so there is no look-ahead;
  * trigger = the first bullish candle that closes above the previous bar's high, within
    ``max_confirm_wait`` bars of the L2 pivot being confirmed. Stop sits below L2.
"""
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.core.config import settings

RSI_WARMUP_BARS = 15  # Wilder RSI is NaN->50 filler before this; never trust a pivot earlier than it


@dataclass(frozen=True)
class DivergenceHit:
    index: int            # row of the confirming candle (last row of the frame passed in)
    timestamp: object
    l1_index: int
    l2_index: int
    low1: float
    low2: float
    rsi1: float
    rsi2: float
    entry_ref: float      # close of the confirming candle (reference only; a real entry fills later)
    stop_loss: float      # below the second low
    target_mid: float     # 20 SMA at the confirming candle


def swing_low_indices(low: pd.Series, k: int = 2) -> list[int]:
    """Positions whose low is strictly below the k bars before and <= the k bars after.
    Only bars with k full bars after them are returned (i.e. confirmed pivots)."""
    vals = low.to_numpy(dtype="float64")
    out = []
    for i in range(k, len(vals) - k):
        if vals[i] < vals[i - k:i].min() and vals[i] <= vals[i + 1:i + k + 1].min():
            out.append(i)
    return out


def _same_session(df: pd.DataFrame, a: int, b: int) -> bool:
    if "timestamp" not in df.columns:
        return True
    ts = pd.to_datetime(df["timestamp"])
    return ts.iloc[a].date() == ts.iloc[b].date()


def _is_trigger(df: pd.DataFrame, j: int) -> bool:
    row, prev = df.iloc[j], df.iloc[j - 1]
    return bool(row["close"] > row["open"] and row["close"] > prev["high"])


def detect_bullish_rsi_divergence(
    df: pd.DataFrame,
    *,
    pivot_k: int = 2,
    min_gap: int = 4,
    max_gap: int = 20,
    rsi_first_max: float = 40.0,
    min_rsi_diff: float = 2.0,
    require_lower_band: bool = True,
    max_confirm_wait: int = 3,
) -> Optional[DivergenceHit]:
    """Return a hit if the LAST row of ``df`` is the confirming candle of a bullish divergence."""
    n = len(df)
    t = n - 1
    if n < RSI_WARMUP_BARS + min_gap + 2 * pivot_k + 2:
        return None
    pivots = [p for p in swing_low_indices(df["low"], pivot_k) if p >= RSI_WARMUP_BARS]
    if len(pivots) < 2:
        return None

    low = df["low"].to_numpy(dtype="float64")
    rsi = df["rsi"].to_numpy(dtype="float64")
    for p2 in reversed(pivots):
        first_confirm_bar = p2 + pivot_k + 1
        if t < first_confirm_bar:
            continue
        if t - first_confirm_bar + 1 > max_confirm_wait:
            break  # older pivots are even staler
        if not _is_trigger(df, t):
            return None
        # fire only on the FIRST trigger candle after the pivot is confirmed
        if any(_is_trigger(df, j) for j in range(first_confirm_bar, t)):
            return None
        for p1 in reversed([p for p in pivots if p < p2]):
            gap = p2 - p1
            if gap > max_gap:
                break
            if gap < min_gap:
                continue
            if not (low[p2] < low[p1]):
                continue
            if low[p1 + 1:p2].size and low[p1 + 1:p2].min() <= low[p2]:
                continue  # L2 must be the lowest print since L1
            if not (rsi[p2] >= rsi[p1] + min_rsi_diff and rsi[p1] <= rsi_first_max):
                continue
            if require_lower_band and not (low[p1] <= float(df["bb_lower"].iloc[p1])):
                continue
            if not _same_session(df, p1, t):
                continue
            close = float(df["close"].iloc[t])
            buf = max(0.5, 0.0005 * close)
            return DivergenceHit(
                index=t, timestamp=df["timestamp"].iloc[t] if "timestamp" in df.columns else t,
                l1_index=p1, l2_index=p2, low1=float(low[p1]), low2=float(low[p2]),
                rsi1=float(rsi[p1]), rsi2=float(rsi[p2]), entry_ref=close,
                stop_loss=round(float(low[p2]) - buf, 2), target_mid=float(df["bb_middle"].iloc[t]),
            )
        return None
    return None


def detect_if_enabled(df: pd.DataFrame, **kwargs) -> Optional[DivergenceHit]:
    """Config-gated entry point. Returns None unless RSI_DIVERGENCE_ENABLED=1 (default off)."""
    if not settings.RSI_DIVERGENCE_ENABLED:
        return None
    return detect_bullish_rsi_divergence(df, **kwargs)
