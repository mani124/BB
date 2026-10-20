"""Setups 21-23: T315 version F, the 3/15 EMA cross with fixed-point exits, on NIFTY 50 and NIFTY BANK.

Three independent versions, each evaluated per index on completed index (spot) bars:
  Setup 21  3 minute bars, Nifty distances
  Setup 22  5 minute bars, Nifty distances
  Setup 23  5 minute bars, Nifty distances x 1.29 (a 5m candle moves about 1.3x a 3m candle)
BANKNIFTY uses the same rules with every distance multiplied by BANKNIFTY_SCALE (the price ratio to Nifty).

Rules (all distances in index points; see docs/SETUPS_SPECIFICATION.md section 18):
  Entry   close of the bar on which the 3 EMA crosses the 15 EMA, on the correct side of the 50 EMA, bar start 09:30 to the
          last bar that confirms before 15:15, same session as the previous bar, at least 50 bars of history.
  Stop    extreme of the last 5 bars (low for a CE, high for a PE), clamped to 25..30 points.
  Target  T1 at 45 points. The engine books part there and moves the stop to the entry price.
  Runner  has no fixed target (T2 is set far away); it is closed when a completed bar closes back across the 15 EMA
          (`runner_should_close`) or at the 15:15 cutoff (`market_hours.is_t315_cutoff_due`).
This file also holds the pure functions the replay script (scripts/replay_t315_f.py) uses, so the replay and the scanner
cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import Optional

import pandas as pd

from app.services.strategy_engine import SetupType, Signal
from app.services.strike_selector import recommend_strike

FAST, SLOW, TREND = 3, 15, 50
START = dtime(9, 30)
MIN_HISTORY = 50
LAST_START = {3: dtime(15, 9), 5: dtime(15, 5)}   # the last bar start that still confirms before the 15:15 cutoff
BANKNIFTY_SCALE = 2.41                            # BANKNIFTY / NIFTY median price over the replay period
RUNNER_TARGET_MULT = 10.0                         # T2 far enough away that only the trail or the cutoff closes the runner

NIFTY, BANKNIFTY = "NIFTY 50", "NIFTY BANK"
INDEX_SCALE = {NIFTY: 1.0, BANKNIFTY: BANKNIFTY_SCALE}


@dataclass(frozen=True)
class Params:
    stop_min: float = 25.0
    stop_max: float = 30.0
    t1: float = 45.0
    book: float = 0.6          # share booked at T1 in the replay; the paper engine books half the lots
    swing_bars: int = 5

    def scaled(self, k: float) -> "Params":
        return Params(self.stop_min * k, self.stop_max * k, self.t1 * k, self.book, self.swing_bars)


@dataclass(frozen=True)
class Version:
    number: int
    setup_type: SetupType
    minutes: int
    scale: float
    code: str


VERSIONS: dict[int, Version] = {
    21: Version(21, SetupType.SETUP_21_T315F_3M, 3, 1.0, "T315F3"),
    22: Version(22, SetupType.SETUP_22_T315F_5M, 5, 1.0, "T315F5"),
    23: Version(23, SetupType.SETUP_23_T315F_5M_WIDE, 5, 1.29, "T315F5W"),
}
SETUP_NUMBERS = tuple(VERSIONS)


def is_t315f(setup_type) -> bool:
    text = str(getattr(setup_type, "value", setup_type) or "")
    return any(text.startswith(f"Setup {n}:") for n in SETUP_NUMBERS)


def params_for(version: Version, symbol: str) -> Params:
    return Params().scaled(version.scale * INDEX_SCALE.get(symbol, 1.0))


def emas(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    close = df["close"].astype(float)
    return tuple(close.ewm(span=n, adjust=False).mean() for n in (FAST, SLOW, TREND))  # type: ignore[return-value]


def cross_side_at(df: pd.DataFrame, i: int, minutes: int, ema: Optional[tuple] = None) -> Optional[str]:
    """'CE' / 'PE' when bar i is a qualifying 3/15 cross with the 50 EMA on the trade side, else None."""
    if i < MIN_HISTORY or i >= len(df) or minutes not in LAST_START:
        return None
    ts, prev = df.timestamp.iloc[i], df.timestamp.iloc[i - 1]
    if not (START <= ts.time() <= LAST_START[minutes]) or ts.date() != prev.date():
        return None
    fast, slow, trend = ema or emas(df)
    close = float(df["close"].iloc[i])
    if fast.iloc[i - 1] <= slow.iloc[i - 1] and fast.iloc[i] > slow.iloc[i] and close > trend.iloc[i]:
        return "CE"
    if fast.iloc[i - 1] >= slow.iloc[i - 1] and fast.iloc[i] < slow.iloc[i] and close < trend.iloc[i]:
        return "PE"
    return None


def stop_distance(df: pd.DataFrame, i: int, side: str, p: Params) -> float:
    entry = float(df.close.iloc[i])
    window = df.iloc[max(0, i - p.swing_bars + 1): i + 1]
    extreme = float(window.low.min()) if side == "CE" else float(window.high.max())
    return min(max(abs(entry - extreme), p.stop_min), p.stop_max)


def runner_should_close(side: str, bar_close: float, ema15: float) -> bool:
    """The runner exits when a completed bar closes back across the 15 EMA (below it for a CE, above it for a PE)."""
    return bar_close < ema15 if side == "CE" else bar_close > ema15


def evaluate_t315f(version_number: int, symbol: str, df: pd.DataFrame) -> list[Signal]:
    """`df` is completed bars of this version's timeframe. At most one signal, on the last bar."""
    version = VERSIONS[version_number]
    if symbol not in INDEX_SCALE or df is None or df.empty or len(df) <= MIN_HISTORY:
        return []
    if not {"timestamp", "open", "high", "low", "close"}.issubset(df.columns):
        return []
    df = df.reset_index(drop=True)
    i = len(df) - 1
    side = cross_side_at(df, i, version.minutes)
    if side is None:
        return []
    p = params_for(version, symbol)
    close = float(df.close.iloc[i])
    sgn = 1 if side == "CE" else -1
    risk = stop_distance(df, i, side, p)
    stop = round(close - sgn * risk, 2)
    t1 = round(close + sgn * p.t1, 2)
    t2 = round(close + sgn * p.t1 * RUNNER_TARGET_MULT, 2)
    rec = recommend_strike(symbol, close, side, stop, target_1=t1, target_2=t2)
    fast, slow, trend = emas(df)
    ts_str = str(df.timestamp.iloc[i])
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    word = "above" if side == "CE" else "below"
    return [Signal(
        id=f"{symbol}_{version.minutes}m_{version.code}_{side}_{ts_clean}",
        symbol=symbol,
        timeframe=f"{version.minutes}m",
        setup_type=version.setup_type,
        option_type=side,
        timestamp=ts_str,
        entry_price=round(close, 2),
        stop_loss=rec.stop_loss,
        target_1=rec.target_1,
        target_2=rec.target_2,
        strike_recommendation=rec,
        indicators_snapshot={"close": round(close, 2), "ema_3": round(float(fast.iloc[i]), 2), "ema_15": round(float(slow.iloc[i]), 2),
                             "ema_50": round(float(trend.iloc[i]), 2), "stop_points": round(risk, 1), "t1_points": round(p.t1, 1)},
        rationale=f"3 EMA crossed {word} the 15 EMA on the {version.minutes}m index chart, {word} the 50 EMA; stop {risk:.0f} pts, first target {p.t1:.0f} pts",
        is_confirmed=True,
    )]
