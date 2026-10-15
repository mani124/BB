"""Read-only candle + indicator payload for the position chart popup."""
import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.services.indicators import calculate_indicators
from app.services.paper_trader import paper_trader, PaperPosition

router = APIRouter(prefix="/paper", tags=["paper"])

OPTION_BAR_MINUTES = 5  # option bars are built on 5m IST slots (scanner_candles._get_or_update_option_candles)

_BAND_COLS = ["bb_upper", "bb_middle", "bb_lower", "bb_upper_25", "bb_lower_25", "ema_9", "vwap"]


def _find_position(position_id: str) -> Optional[PaperPosition]:
    # Read the portfolio directly: get_portfolio() recalculates every metric over all closed trades.
    pf = paper_trader._portfolio
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


def _series_payload(df: pd.DataFrame, day: Optional[str] = None) -> dict:
    """Indicators are computed on the full held history (as the scanner does), then cut to `day`
    for display, so the bands match the ones the setup was evaluated on. VWAP already resets per session."""
    if df.empty:
        return {"candles": [], "indicators": {}, "opening_range": None}
    ind = calculate_indicators(df)
    if day:
        ind = ind[ind["timestamp"].dt.strftime("%Y-%m-%d") == day].reset_index(drop=True)
        if ind.empty:
            return {"candles": [], "indicators": {}, "opening_range": None}
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
    # Opening range of the shown session (calculate_indicators only knows the latest held session's).
    orng = None
    session = ind[ind["timestamp"].dt.date == ind["timestamp"].dt.date.iloc[-1]]
    hhmm = session["timestamp"].dt.strftime("%H:%M")
    or_bars = session[(hhmm >= "09:15") & (hhmm < "09:30")]
    if not or_bars.empty:
        hi, lo = _num(or_bars["high"].max()), _num(or_bars["low"].min())
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


def position_bars(worker, pos: PaperPosition):
    """(option, underlying) bars for a position: saved snapshot first, then the scanner's live memory on top."""
    storage = paper_trader.storage
    saved_opt = storage.load_trade_candles(pos.id, "option") if storage else []
    saved_und = storage.load_trade_candles(pos.id, "underlying") if storage else []
    sec = str(pos.option_security_id) if pos.option_security_id else None
    cached = forming = None
    opt_hist = []
    if sec:
        cached = worker._option_chart_cache.get(sec)
        forming = worker._option_forming_candle.get(sec)
        opt_hist = worker._option_candle_history.get(sec, [])
    opt_df = _merge_bars(saved_opt, cached[1] if cached else None, opt_hist, [forming] if forming else None)
    und_forming = worker._current_forming_candle.get(pos.symbol)
    und_df = _merge_bars(saved_und, worker._candle_history.get(pos.symbol, []), [und_forming] if und_forming else None)
    return opt_df, und_df


@router.get("/positions/{position_id}/chart")
def get_position_chart(position_id: str):
    """Candles and setup indicators for a position's option contract and its underlying.
    Built from the saved per-trade candles plus whatever the scanner holds in memory; nothing is fetched."""
    from app.main import worker

    pos = _find_position(position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found")

    opt_df, und_df = position_bars(worker, pos)
    # Show only the entry's trading day (indicators still warm up on the earlier bars).
    day = (pos.entry_datetime or "")[:10] or None

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
            **_series_payload(opt_df, day),
            "interval": f"{OPTION_BAR_MINUTES}m",
            "levels": {
                "entry": pos.option_entry, "stop": pos.option_sl,
                "target_1": pos.option_target_1, "target_2": pos.option_target_2,
            },
        },
        "underlying": {
            **_series_payload(und_df, day),
            "interval": pos.timeframe,
            "levels": {
                "entry": pos.underlying_entry, "stop": pos.underlying_sl,
                "target_1": pos.underlying_target_1, "target_2": pos.underlying_target_2,
            },
        },
    }
