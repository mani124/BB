"""Setup 5 stock quality filters: a moderate-volatility band and a minimum option open interest.

Why: on the stored Setup 5 stock trades (15-21 Oct 2026), the quietest and the most volatile stocks lost money while the middle of the
range made it, and thin-open-interest contracts lost while liquid ones made money (see the 2026-10-21 review). The numbers are
defaults you can change, or switch off, in Settings; a skip is logged as S5_VOLATILITY_BAND or S5_LOW_OI so the effect can be measured.

The gate applies to Setup 5 on stocks only. Indices are left to the per-setup mode (Setup 5 index options lost heavily in the same review).
A stock without enough candle history, or an option without an open-interest reading, passes: missing data never blocks an entry.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.services.setup_switches import setup_number
from app.services.strategy_engine import INDEX_SYMBOLS

LOOKBACK_BARS = 100     # completed 5m bars (about a day and a quarter of session)
MIN_BARS = 20           # fewer than this and the stock's volatility is not measured


def stock_range_pct(candles: Optional[Iterable[dict]]) -> Optional[float]:
    """Mean (high - low) / close of the last LOOKBACK_BARS completed 5m bars, in percent; None when there is too little history."""
    rows = list(candles or [])[-LOOKBACK_BARS:]
    vals = []
    for c in rows:
        try:
            close = float(c["close"])
            if close > 0:
                vals.append((float(c["high"]) - float(c["low"])) / close * 100.0)
        except (KeyError, TypeError, ValueError):
            continue
    if len(vals) < MIN_BARS:
        return None
    return round(sum(vals) / len(vals), 4)


def block_reason(signal, rec, *, enabled: bool, range_min: float, range_max: float, min_oi: float) -> Optional[tuple[str, str]]:
    """(code, detail) when a Setup 5 stock entry must be skipped, else None. A threshold of 0 switches that check off."""
    if not enabled or setup_number(signal.setup_type) != "5" or str(signal.symbol).upper() in INDEX_SYMBOLS:
        return None
    rng = (getattr(signal, "indicators_snapshot", None) or {}).get("stock_range_pct")
    if rng is not None:
        if range_min > 0 and rng < range_min:
            return "S5_VOLATILITY_BAND", f"{signal.symbol} moves {rng:.3f}% per 5m bar on average, below the {range_min:.3f}% floor"
        if range_max > 0 and rng > range_max:
            return "S5_VOLATILITY_BAND", f"{signal.symbol} moves {rng:.3f}% per 5m bar on average, above the {range_max:.3f}% ceiling"
    oi = getattr(rec, "real_oi", None)
    if min_oi > 0 and oi is not None and float(oi) < min_oi:
        return "S5_LOW_OI", f"open interest {float(oi):,.0f} is below {min_oi:,.0f}"
    return None
