"""T315 version F: replay on 3 minute or 5 minute index candles built from Dhan 1 minute files.

Usage (from backend/), after `python -m scripts.fetch_dhan_index_candles --out ../notes_tmp/dhan_candles`:
    python -m scripts.replay_t315_f ../notes_tmp/dhan_candles --minutes 3
    python -m scripts.replay_t315_f ../notes_tmp/dhan_candles --minutes 5 --scale 1.29 --cost 2

Rules (F), all in index points; the option is assumed to move DELTA x the index:
  Entry   completed-bar close when the 3 EMA crosses the 15 EMA, on the correct side of the 50 EMA, bar start 09:30 to the
          last bar that confirms before 15:15, same session as the previous bar, at least 50 bars of history.
  Stop    the extreme of the last 5 bars (low for a CE, high for a PE), clamped to 25..30 points (x --scale).
  Target  T1 at 45 points (x --scale): book 60% there and move the stop to the entry price.
  Runner  the rest exits at the close of the first candle that closes back across the 15 EMA, at the entry price if it is
          touched first, or at the 15:15 cutoff.
Fills are exact at the level, the stop holds inside the bar that hit T1, and no time decay or spread is modelled: the cost
argument (rupees per share, round trip) is the only cost. This is analysis, not part of the app.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import time as dtime
from typing import Optional

import pandas as pd

FAST, SLOW, TREND = 3, 15, 50
START, CUTOFF = dtime(9, 30), dtime(15, 15)
LAST_START = {3: dtime(15, 9), 5: dtime(15, 5)}  # the last bar start that still confirms before the cutoff
MIN_HISTORY = 50
DELTA = 0.5


@dataclass(frozen=True)
class Params:
    stop_min: float = 25.0
    stop_max: float = 30.0
    t1: float = 45.0
    book: float = 0.6
    swing_bars: int = 5

    def scaled(self, k: float) -> "Params":
        return Params(self.stop_min * k, self.stop_max * k, self.t1 * k, self.book, self.swing_bars)


def load_bars(directory: str, symbol: str, minutes: int) -> pd.DataFrame:
    one = pd.read_csv(os.path.join(directory, symbol.replace(" ", "_") + "_1m.csv"), parse_dates=["timestamp"])
    one = one.set_index("timestamp").sort_index()
    one = one[~one.index.duplicated()].between_time("09:15", "15:29")
    agg = one.resample(f"{minutes}min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return agg.dropna(subset=["open"]).reset_index()


def emas(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    close = df["close"].astype(float)
    return tuple(close.ewm(span=n, adjust=False).mean() for n in (FAST, SLOW, TREND))  # type: ignore[return-value]


def signals(df: pd.DataFrame, minutes: int) -> list[tuple[int, str]]:
    """Bar indexes and sides where the 3 EMA crosses the 15 EMA with the 50 EMA on the trade side."""
    fast, slow, trend = emas(df)
    close = df["close"].astype(float)
    out = []
    for i in range(MIN_HISTORY, len(df)):
        ts, prev = df.timestamp.iloc[i], df.timestamp.iloc[i - 1]
        if not (START <= ts.time() <= LAST_START[minutes]) or ts.date() != prev.date():
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i] and close[i] > trend[i]:
            out.append((i, "CE"))
        elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i] and close[i] < trend[i]:
            out.append((i, "PE"))
    return out


def stop_distance(df: pd.DataFrame, i: int, side: str, p: Params) -> float:
    entry = float(df.close.iloc[i])
    window = df.iloc[max(0, i - p.swing_bars + 1): i + 1]
    extreme = float(window.low.min()) if side == "CE" else float(window.high.max())
    return min(max(abs(entry - extreme), p.stop_min), p.stop_max)


def simulate(df: pd.DataFrame, slow: pd.Series, i: int, side: str, p: Params) -> Optional[tuple[float, str]]:
    """Index points gained on one unit, and how the trade ended; None if the data ends before it resolves."""
    sgn = 1 if side == "CE" else -1
    entry = float(df.close.iloc[i])
    risk = stop_distance(df, i, side, p)
    stop, t1_px = entry - sgn * risk, entry + sgn * p.t1
    day, t1_hit = df.timestamp.iloc[i].date(), False
    for j in range(i + 1, len(df)):
        bar = df.iloc[j]
        if bar.timestamp.date() != day or bar.timestamp.time() >= CUTOFF:
            gone = sgn * (float(df.close.iloc[j - 1]) - entry)
            return (p.book * p.t1 + (1 - p.book) * gone, "T1 then cutoff") if t1_hit else (gone, "cutoff")
        stop_hit = bar.low <= stop if sgn > 0 else bar.high >= stop
        if not t1_hit:
            if stop_hit:
                return -risk, "stopped"
            if (bar.high >= t1_px) if sgn > 0 else (bar.low <= t1_px):
                t1_hit, stop = True, entry
            continue
        if stop_hit:
            return p.book * p.t1, "T1 then back to cost"
        if (sgn > 0 and bar.close < slow.iloc[j]) or (sgn < 0 and bar.close > slow.iloc[j]):
            return p.book * p.t1 + (1 - p.book) * sgn * (float(bar.close) - entry), "T1 then 15 EMA trail"
    return None


def replay(df: pd.DataFrame, minutes: int, p: Params) -> pd.DataFrame:
    _, slow, _ = emas(df)
    rows = []
    for i, side in signals(df, minutes):
        res = simulate(df, slow, i, side, p)
        if res is not None:
            rows.append({"time": df.timestamp.iloc[i], "day": df.timestamp.iloc[i].date(), "side": side, "points": res[0], "how": res[1]})
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame, lot: int, cost: float) -> dict:
    if trades.empty:
        return {"trades": 0}
    days = sorted(trades.day.unique())
    half = set(sorted(trades.day.unique())[: len(days) // 2])
    first = trades[trades.day.isin(half)].points.sum()
    return {
        "trades": len(trades), "win%": round(100 * (trades.points > 0).mean()),
        "T1 hit%": round(100 * trades.how.str.startswith("T1").mean()), "stopped%": round(100 * (trades.how == "stopped").mean()),
        "avg_pts": round(trades.points.mean(), 1), "total_pts": round(trades.points.sum()),
        "first_half_pts": round(first), "second_half_pts": round(trades.points.sum() - first),
        "rupees_per_lot_gross": round(trades.points.sum() * DELTA * lot),
        "rupees_per_lot_after_cost": round((trades.points.sum() * DELTA - cost * len(trades)) * lot),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("directory")
    ap.add_argument("--minutes", type=int, choices=(3, 5), default=3)
    ap.add_argument("--scale", type=float, default=1.0, help="multiply the point distances (e.g. 1.29 for 5m)")
    ap.add_argument("--cost", type=float, default=2.0, help="rupees per share, round trip (charges, spread, slippage)")
    ap.add_argument("--symbol", default="NIFTY 50")
    ap.add_argument("--since", help="only count trades on or after this date (YYYY-MM-DD); earlier bars still warm up the EMAs")
    ap.add_argument("--until", help="only count trades before this date (YYYY-MM-DD)")
    args = ap.parse_args()
    from app.services.strike_selector import get_lot_size
    lot = get_lot_size(args.symbol)
    trades = replay(load_bars(args.directory, args.symbol, args.minutes), args.minutes, Params().scaled(args.scale))
    if args.since:
        trades = trades[trades.day >= pd.Timestamp(args.since).date()]
    if args.until:
        trades = trades[trades.day < pd.Timestamp(args.until).date()]
    span = f", trades {args.since or 'start'} to {args.until or 'end'}" if (args.since or args.until) else ""
    print(f"{args.symbol} {args.minutes}m, point scale {args.scale}, lot {lot}, cost {args.cost} per share{span}")
    for k, v in summarize(trades, lot, args.cost).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
