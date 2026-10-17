"""Setup 11: Setup 5 with extra option-chart quality filters.

Setup 11 is a shadow of Setup 5. It sees only the signals Setup 5 raises and keeps those that also pass three
filters read from the same option premium chart:

1. Option trend strength: RSI and Bollinger BandWidth both higher than on the previous bar.
2. Candle quality: a green signal bar that closes in the top 60% of its range (no long upper wick).
3. Stop-width cap: the stop is at most 30% below the price we would pay (live ask when known, else the close).

A passing signal becomes its own Setup 11 position, so it runs next to Setup 5 on the same contract.
Setup 11 has separate exposure and loss caps (see paper_guards / paper_risk), which makes the two comparable.
"""
import logging
from typing import Optional

import pandas as pd

from app.services.strategy_engine import Signal, SetupType

logger = logging.getLogger(__name__)

MIN_CLOSE_POSITION = 0.60   # (close - low) / (high - low) must be at least this
MAX_STOP_WIDTH = 0.30       # (fill - stop) / fill must be at most this


def setup11_filter_reason(option_df: pd.DataFrame, s5_signal: Signal) -> Optional[str]:
    """Why a Setup 5 signal fails the Setup 11 filters, or None when it passes."""
    if len(option_df) < 2:
        return "not enough bars for trend strength"
    last, prev = option_df.iloc[-1], option_df.iloc[-2]

    # 1. Option trend strength
    try:
        rsi_now, rsi_prev = float(last["rsi"]), float(prev["rsi"])
        bw_now, bw_prev = float(last["bandwidth"]), float(prev["bandwidth"])
    except (KeyError, TypeError, ValueError):
        return "trend strength inputs missing"
    if pd.isna(rsi_now) or pd.isna(rsi_prev) or pd.isna(bw_now) or pd.isna(bw_prev):
        return "trend strength inputs missing"
    if rsi_now <= rsi_prev:
        return f"RSI not rising ({rsi_prev:.1f} -> {rsi_now:.1f})"
    if bw_now <= bw_prev:
        return f"BandWidth not rising ({bw_prev:.2f} -> {bw_now:.2f})"

    # 2. Candle quality
    o, h, l, c = (float(last.get(k, float("nan"))) for k in ("open", "high", "low", "close"))
    if pd.isna(o) or pd.isna(h) or pd.isna(l) or pd.isna(c):
        return "candle inputs missing"
    if c <= o:
        return "signal candle is not green"
    rng = h - l
    if rng > 0 and (c - l) / rng < MIN_CLOSE_POSITION:
        return f"long upper wick (close at {(c - l) / rng * 100:.0f}% of the bar range)"

    # 3. Stop-width cap, measured against the price we would actually pay
    rec = s5_signal.strike_recommendation
    ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
    fill = max(ask, s5_signal.entry_price) if ask > 0 else s5_signal.entry_price
    if fill > 0:
        width = (fill - s5_signal.stop_loss) / fill
        if width > MAX_STOP_WIDTH:
            return f"stop is {width * 100:.0f}% below the fill {fill:g} (cap {MAX_STOP_WIDTH * 100:.0f}%)"
    return None


def evaluate_setup11(option_df: pd.DataFrame, s5_signal: Optional[Signal]) -> Optional[Signal]:
    """Setup 11 signal for a Setup 5 signal that passes the filters, else None (the reason is logged)."""
    if s5_signal is None:
        return None
    reason = setup11_filter_reason(option_df, s5_signal)
    if reason:
        logger.info("Setup 11 skipped %s %s: %s", s5_signal.symbol, s5_signal.option_type, reason)
        return None
    s11 = s5_signal.model_copy(deep=True)
    s11.id = s5_signal.id.replace("_S5_", "_S11_", 1) if "_S5_" in s5_signal.id else f"{s5_signal.id}_S11"
    s11.setup_type = SetupType.SETUP_11_FILTERED_OPTION_BB
    s11.rationale = "Setup 5 signal with rising RSI/BandWidth, clean candle and capped stop width"
    return s11
