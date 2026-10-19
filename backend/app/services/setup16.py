"""Setup 16: Option Squeeze Breakout.

Buys the ATM option when a completed 5m bar closes above its own upper Bollinger Band right after a squeeze
of that premium chart (low BandWidth), instead of chasing a band that has already expanded. The stop is the
nearer of the lower band and a fixed percentage below the close, so the risk stays inside the per-trade cap.
Bands here are built from the current session's closes only (the option's previous day is a different
price level). Evaluated on completed option bars only. See docs/SETUPS_SPECIFICATION.md section 21.
"""
import logging
from datetime import time as dtime
from typing import Literal, Optional

import pandas as pd

from app.services.option_chart_strategy import build_option_chart_signal
from app.services.strategy_engine import Signal, SetupType

logger = logging.getLogger(__name__)

MIN_SESSION_BARS = 12        # bands need at least this many of today's closes (first entry about 10:00 IST)
BB_WINDOW = 20
SQUEEZE_LOOKBACK = 6         # a squeeze bar must be among the 6 bars before the breakout bar
SQUEEZE_BW_FACTOR = 1.30     # same factor as Setups 1 and 10: BandWidth within 1.3x of the session's tightest
MIN_VOLUME = 1000.0
STOP_PCT = 12.0              # runtime setting setup16_stop_pct: max distance of the stop below the close, in %
WINDOW_START = dtime(9, 30)  # runtime setting setup16_window_start (bar start)
WINDOW_END = dtime(14, 25)   # runtime setting setup16_window_end (bar start)

REQUIRED = {"timestamp", "open", "high", "low", "close", "volume"}


def session_bands(close: pd.Series) -> pd.DataFrame:
    """Upper / lower band and BandWidth % (2 sigma, 20 bars, at least MIN_SESSION_BARS closes) of one session's closes."""
    mid = close.rolling(BB_WINDOW, min_periods=MIN_SESSION_BARS).mean()
    sd = close.rolling(BB_WINDOW, min_periods=MIN_SESSION_BARS).std(ddof=0)
    upper, lower = mid + 2.0 * sd, mid - 2.0 * sd
    bw = (upper - lower) / mid.where(mid > 0) * 100.0
    return pd.DataFrame({"upper": upper, "lower": lower, "bw": bw})


def _parse_time(value, default: dtime) -> dtime:
    try:
        h, m = str(value).split(":")
        return dtime(int(h), int(m))
    except Exception:
        return default


def evaluate_option_squeeze_breakout(
    symbol: str,
    strike_symbol: str,
    option_type: Literal["CE", "PE"],
    option_df: pd.DataFrame,
    underlying_price: float,
    strike_price: float,
    expiry_date: Optional[str] = None,
    lot_size: int = 50,
    option_security_id: Optional[str] = None,
    timeframe: str = "5m",
    current_quote: Optional[dict] = None,
    stop_pct: float = STOP_PCT,
    window_start=WINDOW_START,
    window_end=WINDOW_END,
    diag: Optional[dict] = None,
) -> Optional[Signal]:
    """`option_df` is completed option bars (per-bar volume; bars flagged volume_known=False never pass).

    ``diag``, when given, is filled with where the contract stands (``stage`` and the numbers behind it) so the
    dashboard can show why there was no signal: NO_DATA, WARMUP, OUT_OF_WINDOW, NO_BREAKOUT, RED_BAR, NO_SQUEEZE,
    LOW_VOLUME or SIGNAL."""
    d = diag if diag is not None else {}

    def stop(stage: str, **kv):
        d["stage"] = stage
        d.update({k: v for k, v in kv.items() if v is not None})
        return None

    if timeframe != "5m" or option_df is None or option_df.empty or not REQUIRED.issubset(option_df.columns):
        return stop("NO_DATA")
    df = option_df.reset_index(drop=True)
    dates = pd.to_datetime(df["timestamp"]).dt.date
    t_all = len(df) - 1
    sess = df.iloc[int((dates != dates.iloc[t_all]).sum()):].reset_index(drop=True)
    if len(sess) < MIN_SESSION_BARS + 1:
        return stop("WARMUP", session_bars=len(sess), needed_bars=MIN_SESSION_BARS + 1)

    t = len(sess) - 1
    curr = sess.iloc[t]
    start = window_start if isinstance(window_start, dtime) else _parse_time(window_start, WINDOW_START)
    end = window_end if isinstance(window_end, dtime) else _parse_time(window_end, WINDOW_END)
    ts = pd.to_datetime(curr["timestamp"])
    close, open_ = float(curr["close"]), float(curr["open"])
    d.update({"bar_time": ts.strftime("%H:%M"), "close": round(close, 2)})
    if ts.time() < start or ts.time() > end:
        return stop("OUT_OF_WINDOW")
    if pd.isna(close) or close <= 0:
        return stop("NO_DATA")

    bands = session_bands(sess["close"].astype(float))
    upper, lower, bw = bands["upper"].iloc[t], bands["lower"].iloc[t], bands["bw"].iloc[t]
    if pd.isna(upper) or pd.isna(lower):
        return stop("WARMUP", session_bars=len(sess), needed_bars=MIN_SESSION_BARS + 1)
    d.update({"upper_bb": round(float(upper), 2), "lower_bb": round(float(lower), 2),
              "pct_to_upper": round((float(upper) / close - 1.0) * 100.0, 2), "bandwidth": round(float(bw), 2)})
    prior_all = bands["bw"].iloc[:t].dropna()
    if not prior_all.empty:
        d["session_bw_min"] = round(float(prior_all.min()), 2)
        d["recent_bw_min"] = round(float(prior_all.iloc[-SQUEEZE_LOOKBACK:].min()), 2)
        d["squeeze_limit"] = round(float(prior_all.min()) * SQUEEZE_BW_FACTOR, 2)
        d["in_squeeze"] = bool(d["recent_bw_min"] <= d["squeeze_limit"])
    if close <= upper:
        return stop("NO_BREAKOUT")
    if close <= open_:
        return stop("RED_BAR")

    # Squeeze just before the breakout: a bar among the last SQUEEZE_LOOKBACK before this one had BandWidth
    # within 1.3x of the tightest BandWidth the session has shown, and the breakout bar widened it.
    prior = prior_all
    if prior.empty:
        return stop("NO_SQUEEZE")
    recent_min = float(prior.iloc[-SQUEEZE_LOOKBACK:].min())
    if recent_min > float(prior.min()) * SQUEEZE_BW_FACTOR or not bw > float(prior.iloc[-1]):
        return stop("NO_SQUEEZE")

    if "volume_known" in sess.columns:
        flag = sess["volume_known"].iloc[t]
        if not pd.isna(flag) and not bool(flag):
            return stop("LOW_VOLUME", volume=None)
    vol = sess["volume"].iloc[t]
    if pd.isna(vol) or float(vol) < MIN_VOLUME:
        return stop("LOW_VOLUME", volume=None if pd.isna(vol) else float(vol))

    floor_stop = close * (1.0 - stop_pct / 100.0)
    stop_price = max(float(lower), floor_stop)   # the nearer (higher) of the lower band and the percentage stop
    stop_kind = "lower_bb" if lower >= floor_stop else "pct"

    # builder wants the full indicator columns of the bar; supply the ones this setup does not compute itself
    bar = curr.copy()
    bar["bb_upper"] = float(upper)
    bar["bb_lower"] = float(lower)
    bar["bb_middle"] = (float(upper) + float(lower)) / 2.0
    bar["vwap"] = float(bar["vwap"]) if "vwap" in bar and not pd.isna(bar["vwap"]) else close
    bar["rsi"] = float(bar["rsi"]) if "rsi" in bar and not pd.isna(bar["rsi"]) else 50.0
    bar["ema_9"] = float(bar["ema_9"]) if "ema_9" in bar and not pd.isna(bar["ema_9"]) else close
    bar["percent_b"] = (close - float(lower)) / max(float(upper) - float(lower), 1e-9)

    sig = build_option_chart_signal(
        setup_type=SetupType.SETUP_16_OPTION_SQUEEZE_BREAK,
        rationale="Option premium closed above its upper Bollinger Band after a BandWidth squeeze",
        tag="S16",
        curr=bar,
        last_idx=len(df) - 1,
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
            "squeeze_bw_min": round(recent_min, 2),
            "session_bw_min": round(float(prior.min()), 2),
            "breakout_bw": round(float(bw), 2),
            "lower_bb": round(float(lower), 2),
            "stop_is_lower_bb": 1.0 if stop_kind == "lower_bb" else 0.0,
        },
        stop_price=round(stop_price, 2),
    )
    if sig is None:
        return stop("OUT_OF_WINDOW")  # the shared builder's time guards (prior-day bar, entry cutoff, expiry-day cutoff)
    d["stage"] = "SIGNAL"
    d["stop"] = sig.stop_loss
    return sig
