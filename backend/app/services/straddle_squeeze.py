"""Setup 10: ATM straddle premium squeeze.

Builds a synthetic straddle chart (ATM CE + ATM PE premium, bar by bar) and looks for a
Bollinger BandWidth squeeze followed by an upside expansion of the combined premium. The
trade is the ATM leg that is driving the expansion, managed on the option chart exactly like
Setup 5 (the shared signal builder handles risk, targets and time guards).
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.services import market_hours
from app.services.indicators import calculate_indicators
from app.services.option_chart_strategy import build_option_chart_signal
from app.services.strategy_engine import Signal, SetupType

logger = logging.getLogger(__name__)

MIN_BARS = 20
SQUEEZE_LOOKBACK = 3        # squeeze must have been present in one of the last 3 bars before the trigger
SQUEEZE_BW_FACTOR = 1.30    # same factor as Setup 1, applied to the straddle's own BandWidth
MIN_LEG_GAIN = 0.03         # winning leg's trigger bar must gain at least 3%
MIN_LEG_VOLUME = 1000.0
VOLUME_SURGE = 1.2


@dataclass
class StraddleLeg:
    """One ATM leg: its indicator frame (completed bars only) and the contract details."""
    df: pd.DataFrame
    strike_symbol: str
    security_id: Optional[str]
    quote: Optional[dict] = None


def build_straddle_frame(ce_df: pd.DataFrame, pe_df: pd.DataFrame) -> pd.DataFrame:
    """Synthetic straddle bars (sum of the two legs' OHLC) on the timestamps both legs share."""
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    ce = ce_df[cols + (["volume_known"] if "volume_known" in ce_df.columns else [])].copy()
    pe = pe_df[cols + (["volume_known"] if "volume_known" in pe_df.columns else [])].copy()
    ce["timestamp"] = pd.to_datetime(ce["timestamp"])
    pe["timestamp"] = pd.to_datetime(pe["timestamp"])
    m = ce.merge(pe, on="timestamp", suffixes=("_ce", "_pe")).sort_values("timestamp")
    if m.empty:
        return pd.DataFrame()
    out = pd.DataFrame({"timestamp": m["timestamp"]})
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = m[f"{c}_ce"].astype(float) + m[f"{c}_pe"].astype(float)
    return calculate_indicators(out.reset_index(drop=True))


def _leg_gain(df: pd.DataFrame) -> float:
    last = df.iloc[-1]
    o = float(last["open"])
    return (float(last["close"]) - o) / o if o > 0 else 0.0


def _volume_ok(df: pd.DataFrame) -> bool:
    """Real per-bar volume, at least 1,000 contracts and 1.2x the prior 20-bar average."""
    last_idx = len(df) - 1
    if "volume_known" in df.columns:
        flag = df["volume_known"].iloc[last_idx]
        if not pd.isna(flag) and not bool(flag):
            return False
    vol = df["volume"].iloc[last_idx]
    if pd.isna(vol):
        return False
    hist = df["volume"].iloc[max(0, last_idx - 20):last_idx]
    if "volume_known" in df.columns:
        hist = hist.where(df["volume_known"].iloc[max(0, last_idx - 20):last_idx] != False)  # noqa: E712
    avg = float(hist.mean()) if len(hist) else float(vol)
    if math.isnan(avg):
        return False
    return float(vol) >= max(MIN_LEG_VOLUME, avg * VOLUME_SURGE)


def evaluate_straddle_squeeze(
    symbol: str,
    legs: dict[str, StraddleLeg],
    underlying_price: float,
    strike_price: float,
    expiry_date: Optional[str] = None,
    lot_size: int = 50,
    timeframe: str = "5m",
) -> Optional[Signal]:
    ce, pe = legs.get("CE"), legs.get("PE")
    if ce is None or pe is None or len(ce.df) < MIN_BARS or len(pe.df) < MIN_BARS:
        return None
    if not market_hours.is_entry_allowed():
        return None

    sd = build_straddle_frame(ce.df, pe.df)
    if len(sd) < MIN_BARS:
        return None
    # Both legs must have closed the same latest bar, or the straddle bar is stale/misaligned.
    last_ts = sd["timestamp"].iloc[-1]
    if pd.to_datetime(ce.df["timestamp"].iloc[-1]) != last_ts or pd.to_datetime(pe.df["timestamp"].iloc[-1]) != last_ts:
        return None

    n = len(sd)
    cur, prev = sd.iloc[n - 1], sd.iloc[n - 2]
    if pd.isna(cur["bb_upper"]) or pd.isna(cur["bandwidth"]):
        return None

    # 1. Expansion: combined premium closes above its upper band and above the prior close.
    if not (cur["close"] > cur["bb_upper"] and cur["close"] > prev["close"]):
        return None

    # 2. Squeeze: BandWidth was within 1.30x of its 20-bar minimum in one of the 3 bars before.
    window = sd.iloc[max(0, n - 1 - SQUEEZE_LOOKBACK):n - 1]
    squeezed = window[(window["bandwidth"].notna()) & (window["bandwidth_20_min"].notna())
                      & (window["bandwidth"] <= window["bandwidth_20_min"] * SQUEEZE_BW_FACTOR)]
    if squeezed.empty:
        return None

    # 3. Direction: one leg leads (>= 3% on the bar) while the other does not gain.
    gains = {k: _leg_gain(leg.df) for k, leg in (("CE", ce), ("PE", pe))}
    side = "CE" if gains["CE"] >= gains["PE"] else "PE"
    other = "PE" if side == "CE" else "CE"
    if gains[side] < MIN_LEG_GAIN or gains[other] > 0:
        return None

    win = legs[side]
    wl = win.df.iloc[-1]
    if not (float(wl["close"]) > float(wl["vwap"]) and float(wl["close"]) > float(wl["ema_9"])):
        return None
    if not _volume_ok(win.df):
        return None

    return build_option_chart_signal(
        setup_type=SetupType.SETUP_10_STRADDLE_SQUEEZE,
        rationale="ATM straddle premium squeeze, expansion led by the " + side + " leg",
        tag="S10",
        curr=wl,
        last_idx=len(win.df) - 1,
        symbol=symbol,
        strike_symbol=win.strike_symbol,
        option_type=side,
        underlying_price=underlying_price,
        strike_price=strike_price,
        expiry_date=expiry_date,
        lot_size=lot_size,
        option_security_id=win.security_id,
        timeframe=timeframe,
        current_quote=win.quote,
        extra_snapshot={
            "straddle_close": round(float(cur["close"]), 2),
            "straddle_bb_upper": round(float(cur["bb_upper"]), 2),
            "straddle_bandwidth": round(float(cur["bandwidth"]), 2),
            "straddle_bandwidth_20_min": round(float(cur["bandwidth_20_min"]), 2),
            "ce_bar_gain_pct": round(gains["CE"] * 100, 2),
            "pe_bar_gain_pct": round(gains["PE"] * 100, 2),
        },
    )
