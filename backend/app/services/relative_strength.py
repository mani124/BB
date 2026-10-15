"""Setup 9: Relative Strength vs NIFTY, first pullback to the 9 EMA.

Evaluated only on completed 5m bars (the caller passes closed history), so every signal
is a confirmed candle close. See docs/SETUPS_SPECIFICATION.md section 12.
"""
from datetime import time as dtime

import pandas as pd

from app.services.strategy_engine import Signal, SetupType, INDEX_SYMBOLS
from app.services.strike_selector import recommend_strike

NIFTY_SYMBOL = "NIFTY 50"

MIN_STOCK_MOVE_PCT = 0.75      # stock day move from today's open
FLAT_BAND_PCT = 0.15           # NIFTY counts as "flat" within +/- this
MIN_SPREAD_PCT = 0.75          # stock minus NIFTY day move
MIN_BARS_TODAY = 6             # 30 minutes of 5m bars
WINDOW_START = dtime(9, 45)
WINDOW_END = dtime(15, 10)     # bar start; a 15:10 bar confirms at 15:15, the fresh-entry cutoff


def _day_bars(df: pd.DataFrame, day) -> pd.DataFrame:
    """Today's bars in time order, one per timestamp (a duplicated bar keeps the latest copy)."""
    out = df.assign(timestamp=pd.to_datetime(df["timestamp"]))
    out = out[out["timestamp"].dt.date == day]
    return (
        out.drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def evaluate_relative_strength(
    symbol: str,
    df: pd.DataFrame,
    index_df: pd.DataFrame | None,
    timeframe: str = "5m",
    stock_bias: str | None = None,
) -> list[Signal]:
    """`df` is the stock's completed bars with indicators (needs ema_9, vwap); `index_df`
    is NIFTY's completed bars (needs timestamp, open, close). Returns at most one signal."""
    required = {"timestamp", "open", "high", "low", "close", "ema_9", "vwap"}
    if (
        df is None or df.empty or index_df is None or index_df.empty
        or symbol.upper() in INDEX_SYMBOLS
        or stock_bias not in ("BULLISH", "BEARISH")
        or not required.issubset(df.columns)
        or not {"timestamp", "open", "close"}.issubset(index_df.columns)
    ):
        return []

    last_ts = pd.to_datetime(df["timestamp"].iloc[-1])
    if not (WINDOW_START <= last_ts.time() <= WINDOW_END):
        return []

    day = _day_bars(df, last_ts.date())
    idx_day = _day_bars(index_df, last_ts.date())
    if len(day) < MIN_BARS_TODAY or idx_day.empty:
        return []
    # NIFTY must have closed the same bar; a lagging index would be forward-filled with a stale close
    if idx_day["timestamp"].iloc[-1] < day["timestamp"].iloc[-1]:
        return []

    # Day move of the stock and NIFTY from today's first open, per stock bar (NIFTY aligned by time)
    stock_open = float(day["open"].iloc[0])
    idx_open = float(idx_day["open"].iloc[0])
    if stock_open <= 0 or idx_open <= 0:
        return []
    idx_close = idx_day.set_index("timestamp")["close"]
    idx_aligned = idx_close.reindex(day["timestamp"].values, method="ffill")
    if idx_aligned.isna().any():
        return []
    stock_move = (day["close"].astype(float) / stock_open - 1.0) * 100.0
    idx_move = (idx_aligned.astype(float).reset_index(drop=True) / idx_open - 1.0) * 100.0

    ce_ok = (
        (stock_move >= MIN_STOCK_MOVE_PCT)
        & (idx_move <= FLAT_BAND_PCT)
        & ((stock_move - idx_move) >= MIN_SPREAD_PCT)
    )
    pe_ok = (
        (stock_move <= -MIN_STOCK_MOVE_PCT)
        & (idx_move >= -FLAT_BAND_PCT)
        & ((idx_move - stock_move) >= MIN_SPREAD_PCT)
    )

    n = len(day)
    t = n - 1
    curr, prev = day.iloc[t], day.iloc[t - 1]
    if bool(ce_ok.iloc[t]) and stock_bias == "BULLISH":
        side = "CE"
        qualified = ce_ok
    elif bool(pe_ok.iloc[t]) and stock_bias == "BEARISH":
        side = "PE"
        qualified = pe_ok
    else:
        return []

    close, high, low, open_ = (float(curr[c]) for c in ("close", "high", "low", "open"))
    ema = float(curr["ema_9"])
    vwap = float(curr["vwap"])
    if pd.isna(ema) or pd.isna(vwap) or close <= 0:
        return []

    # Index of the first bar where relative strength held, and the earlier EMA touches since
    # qualified.iloc[t] is True here, so argmax always finds a real first True
    q_first = int(qualified.values.argmax())
    touched_before = any(
        (float(day["low"].iloc[j]) <= float(day["ema_9"].iloc[j])) if side == "CE"
        else (float(day["high"].iloc[j]) >= float(day["ema_9"].iloc[j]))
        for j in range(q_first + 1, t)
    )
    if touched_before:
        return []  # only the first pullback

    ema_prev3 = float(day["ema_9"].iloc[t - 3]) if t >= 3 else ema
    tol = max(ema * 0.001, 0.05)
    if side == "CE":
        ok = (
            low <= ema + tol and close > ema and close > open_ and close > vwap
            and float(prev["low"]) > float(prev["ema_9"]) and ema > ema_prev3
        )
        sl = round(low - max(0.5, 0.0005 * close), 2)
    else:
        ok = (
            high >= ema - tol and close < ema and close < open_ and close < vwap
            and float(prev["high"]) < float(prev["ema_9"]) and ema < ema_prev3
        )
        sl = round(high + max(0.5, 0.0005 * close), 2)
    if not ok:
        return []

    strike_rec = recommend_strike(symbol, close, side, sl)
    ts_str = str(curr["timestamp"])
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    snap = {
        "close": round(close, 2),
        "ema_9": round(ema, 2),
        "vwap": round(vwap, 2),
        "stock_move_pct": round(float(stock_move.iloc[t]), 2),
        "nifty_move_pct": round(float(idx_move.iloc[t]), 2),
        "rs_spread_pct": round(float(stock_move.iloc[t] - idx_move.iloc[t]), 2),
    }
    word = "rising" if side == "CE" else "falling"
    return [Signal(
        id=f"{symbol}_{timeframe}_S9_{side}_{ts_clean}",
        symbol=symbol,
        timeframe=timeframe,
        setup_type=SetupType.SETUP_9_RELATIVE_STRENGTH,
        option_type=side,
        timestamp=ts_str,
        entry_price=round(close, 2),
        stop_loss=strike_rec.stop_loss,
        target_1=strike_rec.target_1,
        target_2=strike_rec.target_2,
        strike_recommendation=strike_rec,
        indicators_snapshot=snap,
        rationale=(
            f"Stock {word} {abs(snap['stock_move_pct']):.2f}% vs NIFTY {snap['nifty_move_pct']:+.2f}%: "
            "first pullback to the 9 EMA confirmed by a closed 5m candle"
        ),
        is_confirmed=True,
    )]
