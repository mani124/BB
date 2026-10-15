"""Read-only candle + indicator payload for the position chart popup."""
import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.services.indicators import calculate_indicators
from app.services.paper_trader import paper_trader, PaperPosition

router = APIRouter(prefix="/paper", tags=["paper"])

_BAND_COLS = ["bb_upper", "bb_middle", "bb_lower", "bb_upper_25", "bb_lower_25", "ema_9", "vwap"]


def _find_position(position_id: str) -> Optional[PaperPosition]:
    pf = paper_trader.get_portfolio(mode=None)
    for p in list(pf.active_positions) + list(pf.closed_trades):
        if p.id == position_id:
            return p
    return None


def _merge_bars(*sources) -> pd.DataFrame:
    """Merge candle sources (DataFrames or lists of dicts); later sources win on a shared timestamp."""
    frames = []
    for s in sources:
        if s is None:
            continue
        df = pd.DataFrame(s) if not isinstance(s, pd.DataFrame) else s
        if df.empty or "timestamp" not in df.columns:
            continue
        frames.append(df[[c for c in ("timestamp", "open", "high", "low", "close", "volume") if c in df.columns]])
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
    if "volume" not in df.columns:
        df["volume"] = 0
    return df


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, 2)


def _series_payload(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"candles": [], "indicators": {}, "opening_range": None}
    ind = calculate_indicators(df)
    # lightweight-charts wants UTC-based epoch seconds; encode IST wall-clock as if UTC so the axis reads IST.
    ts = pd.to_datetime(ind["timestamp"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    epoch = ((ts - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype(int).tolist()
    candles = [
        {"time": t, "open": _num(o), "high": _num(h), "low": _num(l), "close": _num(c)}
        for t, o, h, l, c in zip(epoch, ind["open"], ind["high"], ind["low"], ind["close"])
    ]
    indicators = {}
    for col in _BAND_COLS:
        if col in ind.columns:
            pts = [{"time": t, "value": _num(v)} for t, v in zip(epoch, ind[col])]
            indicators[col] = [p for p in pts if p["value"] is not None]
    orng = None
    if "or_high" in ind.columns and "or_low" in ind.columns and len(ind):
        hi, lo = _num(ind["or_high"].iloc[-1]), _num(ind["or_low"].iloc[-1])
        if hi is not None and lo is not None:
            orng = {"high": hi, "low": lo}
    return {"candles": candles, "indicators": indicators, "opening_range": orng}


def _epoch_ist(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        t = pd.Timestamp(iso)
    except Exception:
        return None
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Kolkata").tz_localize(None)
    return int((t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))


@router.get("/positions/{position_id}/chart")
def get_position_chart(position_id: str):
    """Candles and setup indicators for a position's option contract and its underlying.
    Built only from data the scanner already holds in memory; nothing is fetched or changed."""
    from app.main import worker

    pos = _find_position(position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found")

    sec = str(pos.option_security_id) if pos.option_security_id else None
    opt_df = pd.DataFrame()
    if sec:
        cached = worker._option_chart_cache.get(sec)
        forming = worker._option_forming_candle.get(sec)
        opt_df = _merge_bars(
            cached[1] if cached else None,
            worker._option_candle_history.get(sec, []),
            [forming] if forming else None,
        )
    und_forming = worker._current_forming_candle.get(pos.symbol)
    und_df = _merge_bars(
        worker._candle_history.get(pos.symbol, []),
        [und_forming] if und_forming else None,
    )
    # Only the entry's trading day, so the session VWAP and bands are not diluted by older sessions.
    day = (pos.entry_datetime or "")[:10]
    if day:
        opt_df = opt_df[opt_df["timestamp"].dt.strftime("%Y-%m-%d") == day] if not opt_df.empty else opt_df
        und_df = und_df[und_df["timestamp"].dt.strftime("%Y-%m-%d") == day] if not und_df.empty else und_df

    return {
        "id": pos.id,
        "symbol": pos.symbol,
        "strike_symbol": pos.strike_symbol,
        "option_type": pos.option_type,
        "setup_type": pos.setup_type,
        "timeframe": pos.timeframe,
        "status": pos.status,
        "entry_time": _epoch_ist(pos.entry_datetime),
        "exit_time": _epoch_ist(pos.exit_datetime),
        "option": {
            **_series_payload(opt_df),
            "interval": "5m",
            "levels": {
                "entry": pos.option_entry, "stop": pos.option_sl,
                "target_1": pos.option_target_1, "target_2": pos.option_target_2,
            },
        },
        "underlying": {
            **_series_payload(und_df),
            "interval": pos.timeframe,
            "levels": {
                "entry": pos.underlying_entry, "stop": pos.underlying_sl,
                "target_1": pos.underlying_target_1, "target_2": pos.underlying_target_2,
            },
        },
    }
