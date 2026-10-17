"""Setup 13: Option VWAP Reclaim.

Buys a pullback inside an existing option trend. The ATM option premium (its own session VWAP, from the
option chart) dips below VWAP for 1 to 5 completed 5m bars after trading above it, then a bar closes back
above VWAP on a volume lift. The underlying must sit on the same side of its own VWAP (above for calls,
below for puts). Evaluated on completed option bars only. See docs/SETUPS_SPECIFICATION.md section 16.
"""
import logging
from datetime import time as dtime
from typing import Literal, Optional

import pandas as pd

from app.services.option_chart_strategy import build_option_chart_signal
from app.services.strategy_engine import Signal, SetupType, _session_bars

logger = logging.getLogger(__name__)

MIN_SESSION_BARS = 20        # first entry about 10:55 IST
MIN_DIP_BARS = 1             # consecutive closes below VWAP before the reclaim bar
MAX_DIP_BARS = 5
VOLUME_LOOKBACK = 3          # reclaim bar volume must beat the average of this many prior bars
MIN_VOLUME = 1000.0
STOP_BUFFER_PCT = 0.01       # stop sits 1% of premium under the anchor (never tighter than 4%, see builder)
MAX_STOP_PCT = 0.30          # skip if the stop would be more than 30% below the close
WINDOW_END = dtime(14, 25)   # bar start; a 14:25 bar confirms at 14:30

REQUIRED = {"timestamp", "open", "high", "low", "close", "vwap", "volume"}


def _spot_side_ok(option_type: str, option_ts: pd.Timestamp, spot_df: Optional[pd.DataFrame]):
    """(ok, spot_close, spot_vwap): the spot bar closed at the option bar's time sits on the trade's side of VWAP."""
    if spot_df is None or spot_df.empty or not {"timestamp", "close", "vwap"}.issubset(spot_df.columns):
        return False, None, None
    ts = pd.to_datetime(spot_df["timestamp"])
    rows = spot_df[ts == option_ts]
    if rows.empty:
        return False, None, None
    row = rows.iloc[-1]
    close, vwap = float(row["close"]), float(row["vwap"])
    if pd.isna(close) or pd.isna(vwap):
        return False, None, None
    ok = close > vwap if option_type == "CE" else close < vwap
    return ok, close, vwap


def evaluate_option_vwap_reclaim(
    symbol: str,
    strike_symbol: str,
    option_type: Literal["CE", "PE"],
    option_df: pd.DataFrame,
    spot_df: Optional[pd.DataFrame],
    underlying_price: float,
    strike_price: float,
    expiry_date: Optional[str] = None,
    lot_size: int = 50,
    option_security_id: Optional[str] = None,
    timeframe: str = "5m",
    current_quote: Optional[dict] = None,
) -> Optional[Signal]:
    """`option_df` is completed option bars with indicators (needs vwap); `spot_df` is completed underlying
    bars with indicators. Option `volume` must be per-bar (the scanner derives it from cumulative day volume);
    bars flagged volume_known=False never pass the volume lift."""
    if timeframe != "5m" or option_df is None or option_df.empty or not REQUIRED.issubset(option_df.columns):
        return None
    if _session_bars(option_df) < MIN_SESSION_BARS:
        return None

    df = option_df.reset_index(drop=True)
    t = len(df) - 1
    curr = df.iloc[t]
    ts = pd.to_datetime(curr["timestamp"])
    if ts.time() > WINDOW_END:
        return None

    close, vwap = float(curr["close"]), float(curr["vwap"])
    if pd.isna(close) or pd.isna(vwap) or close <= 0 or close <= vwap:
        return None

    # Today's bars only: the dip and the prior up-leg must belong to the signal bar's session.
    dates = pd.to_datetime(df["timestamp"]).dt.date
    session_start = int((dates != dates.iloc[t]).sum())

    # Dip: consecutive closes below VWAP immediately before the reclaim bar, preceded by a close above it.
    k = 0
    i = t - 1
    while i >= session_start and float(df["close"].iloc[i]) < float(df["vwap"].iloc[i]):
        k += 1
        i -= 1
    if not (MIN_DIP_BARS <= k <= MAX_DIP_BARS):
        return None
    if i < session_start or not float(df["close"].iloc[i]) > float(df["vwap"].iloc[i]):
        return None  # no prior trade above VWAP: a dead or newly listed option, not a pullback

    # Volume lift on a real per-bar figure.
    if "volume_known" in df.columns:
        flag = df["volume_known"].iloc[t]
        if not pd.isna(flag) and not bool(flag):
            return None
    vol = df["volume"].iloc[t]
    if pd.isna(vol) or float(vol) < MIN_VOLUME:
        return None
    hist = df["volume"].iloc[max(session_start, t - VOLUME_LOOKBACK):t]
    if "volume_known" in df.columns:
        hist = hist.where(df["volume_known"].iloc[max(session_start, t - VOLUME_LOOKBACK):t] != False)  # noqa: E712
    avg = float(hist.mean()) if len(hist) else float("nan")
    if pd.isna(avg) or float(vol) <= avg:
        return None

    spot_ok, spot_close, spot_vwap = _spot_side_ok(option_type, ts, spot_df)
    if not spot_ok:
        return None

    pullback_low = float(df["low"].iloc[t - k:t].min())
    anchor = max(pullback_low, vwap)   # the tighter (higher) of the pullback low and VWAP
    stop_price = anchor - close * STOP_BUFFER_PCT
    if close - stop_price > close * MAX_STOP_PCT:
        return None

    return build_option_chart_signal(
        setup_type=SetupType.SETUP_13_OPTION_VWAP_RECLAIM,
        rationale=f"Option premium reclaimed VWAP after {k} bar(s) below it, volume lift, spot on the same side of VWAP",
        tag="S13",
        curr=curr,
        last_idx=t,
        symbol=symbol,
        strike_symbol=strike_symbol,
        option_type=option_type,
        underlying_price=underlying_price,
        strike_price=strike_price,
        expiry_date=expiry_date,
        lot_size=lot_size,
        option_security_id=option_security_id,
        timeframe=timeframe,
        current_quote=current_quote,
        extra_snapshot={
            "dip_bars": k,
            "pullback_low": round(pullback_low, 2),
            "volume_avg_prior_3": round(avg, 1),
            "spot_close": round(spot_close, 2),
            "spot_vwap": round(spot_vwap, 2),
        },
        stop_price=round(stop_price, 2),
    )
