"""Setup 14: Put-call ratio / OI wall bounce (index options).

The Dhan option chain gives open interest (OI) at every strike. The strike with the largest put OI below spot
is the support wall and the strike with the largest call OI above spot is the resistance wall. A wall only
counts when its OI is at least 1.5x each neighbouring strike. The setup buys the first 5m rejection of a wall,
with the total put-call ratio (PCR) as the bias: >= 1.2 for support bounces (calls), <= 0.8 for resistance
rejections (puts). Evaluated on completed 5m spot bars. See docs/SETUPS_SPECIFICATION.md section 19.
"""
from dataclasses import dataclass
from datetime import time as dtime
from typing import Optional

import pandas as pd

from app.services.strategy_engine import Signal, SetupType, _session_bars
from app.services.strike_selector import recommend_strike

WALL_DOMINANCE = 1.5       # wall OI must be at least this multiple of each adjacent strike's OI
MAX_WALL_DIST_PCT = 0.05   # walls further than 5% from spot are not considered
PCR_LONG_MIN = 1.2
PCR_SHORT_MAX = 0.8
TOUCH_ATR = 0.1            # the bar must reach within this many ATRs of the wall strike
MAX_CLOSE_ATR = 1.0        # ...and close no further than this from it (no chasing)
WICK_BODY_RATIO = 1.0      # rejection wick at least as long as the body
MIN_SESSION_BARS = 3       # first entry about 09:30 IST
WINDOW_END = dtime(14, 25)  # bar start; a 14:25 bar confirms at 14:30
WALL_REFRESH_S = 900.0     # the scanner recomputes walls every 15 minutes
MAX_CHAIN_AGE_S = 120.0    # skip when the chain behind the walls is older than this

REQUIRED = {"timestamp", "open", "high", "low", "close", "atr"}


@dataclass(frozen=True)
class OIWalls:
    spot: float
    pcr: Optional[float]
    support_strike: Optional[float] = None
    support_oi: float = 0.0
    support_ratio: float = 0.0
    resistance_strike: Optional[float] = None
    resistance_oi: float = 0.0
    resistance_ratio: float = 0.0


def _oi(contract) -> float:
    if not isinstance(contract, dict):
        return 0.0
    try:
        v = float(contract.get("oi") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 and v == v else 0.0


def _rows(oc: dict) -> list[tuple[float, float, float]]:
    """(strike, call OI, put OI) sorted by strike."""
    out = []
    for k, v in (oc or {}).items():
        if not isinstance(v, dict):
            continue
        try:
            out.append((float(k), _oi(v.get("ce")), _oi(v.get("pe"))))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _wall(rows: list[tuple[float, float, float]], spot: float, put_side: bool) -> tuple[Optional[float], float, float]:
    """Largest-OI strike on one side of spot, if it dominates both neighbours: (strike, oi, ratio)."""
    col = 2 if put_side else 1
    best = None
    for i, r in enumerate(rows):
        strike, oi = r[0], r[col]
        if oi <= 0 or abs(strike - spot) > MAX_WALL_DIST_PCT * spot:
            continue
        if (put_side and strike > spot) or (not put_side and strike < spot):
            continue
        if best is None or oi > best[1]:
            best = (i, oi)
    if best is None:
        return None, 0.0, 0.0
    i, oi = best
    neighbours = [rows[j][col] for j in (i - 1, i + 1) if 0 <= j < len(rows)]
    top = max(neighbours) if neighbours else 0.0
    ratio = oi / top if top > 0 else float("inf")
    if ratio < WALL_DOMINANCE:
        return None, 0.0, 0.0
    return rows[i][0], oi, round(min(ratio, 99.0), 2)


def compute_oi_walls(oc: dict, spot: float) -> Optional[OIWalls]:
    """Walls and PCR from a Dhan option chain (`oc`: strike -> {"ce": {...,"oi"}, "pe": {...,"oi"}})."""
    rows = _rows(oc)
    if not rows or spot <= 0:
        return None
    call_total = sum(r[1] for r in rows)
    put_total = sum(r[2] for r in rows)
    if call_total <= 0 or put_total <= 0:
        return None  # a chain without OI (empty field or non-trading snapshot) gives no usable walls
    s, s_oi, s_ratio = _wall(rows, spot, put_side=True)
    r, r_oi, r_ratio = _wall(rows, spot, put_side=False)
    return OIWalls(spot=spot, pcr=round(put_total / call_total, 3), support_strike=s, support_oi=s_oi,
                   support_ratio=s_ratio, resistance_strike=r, resistance_oi=r_oi, resistance_ratio=r_ratio)


def _touched(row, wall: float, support: bool, atr_fallback: float) -> bool:
    atr = float(row["atr"]) if not pd.isna(row["atr"]) else atr_fallback
    tol = TOUCH_ATR * atr
    return float(row["low"]) <= wall + tol if support else float(row["high"]) >= wall - tol


def evaluate_oi_wall_bounce(
    symbol: str,
    df: pd.DataFrame,
    walls: Optional[OIWalls],
    timeframe: str = "5m",
    chain_age_s: Optional[float] = None,
) -> list[Signal]:
    """`df` is completed 5m spot bars with `atr`. At most one signal, only on the first touch of a wall today."""
    if walls is None or walls.pcr is None or df is None or df.empty or timeframe != "5m":
        return []
    if not REQUIRED.issubset(df.columns) or _session_bars(df) < MIN_SESSION_BARS:
        return []
    if chain_age_s is None or chain_age_s > MAX_CHAIN_AGE_S:
        return []
    df = df.reset_index(drop=True)
    t = len(df) - 1
    curr = df.iloc[t]
    ts = pd.to_datetime(curr["timestamp"])
    if ts.time() > WINDOW_END:
        return []
    o, h, l, c = (float(curr[k]) for k in ("open", "high", "low", "close"))
    atr = float(curr["atr"]) if not pd.isna(curr["atr"]) else 0.0
    if atr <= 0 or c <= 0:
        return []

    if walls.support_strike is not None and walls.pcr >= PCR_LONG_MIN:
        side, wall, support = "CE", walls.support_strike, True
        wick, body_ok_close = min(o, c) - l, c > wall
        opp, opp_oi = walls.resistance_strike, walls.resistance_oi
    elif walls.resistance_strike is not None and walls.pcr <= PCR_SHORT_MAX:
        side, wall, support = "PE", walls.resistance_strike, False
        wick, body_ok_close = h - max(o, c), c < wall
        opp, opp_oi = walls.support_strike, walls.support_oi
    else:
        return []
    body = abs(c - o)
    if not _touched(curr, wall, support, atr) or not body_ok_close:
        return []
    if abs(c - wall) > MAX_CLOSE_ATR * atr or wick < WICK_BODY_RATIO * body or wick <= 0:
        return []

    dates = pd.to_datetime(df["timestamp"]).dt.date
    today = df[dates == dates.iloc[t]].iloc[:-1]
    if any(_touched(r, wall, support, atr) for _, r in today.iterrows()):
        return []  # not the first touch of this wall today

    buf = max(0.1 * atr, c * 0.0003)
    sl = round(max(wall, l) - buf, 2) if support else round(min(wall, h) + buf, 2)
    strike_rec = recommend_strike(symbol, c, side, sl)
    ts_str = str(curr["timestamp"])
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    snap = {
        "close": round(c, 2),
        "wall_strike": wall,
        "wall_oi": walls.support_oi if support else walls.resistance_oi,
        "wall_oi_ratio": walls.support_ratio if support else walls.resistance_ratio,
        "pcr": walls.pcr,
        "opposite_wall": opp,
        "opposite_wall_oi": opp_oi,
        "wick": round(wick, 2),
        "body": round(body, 2),
        "chain_age_s": round(chain_age_s, 1),
    }
    # Signal.indicators_snapshot only holds numbers; a side with no wall must be omitted, not None.
    snap = {k: v for k, v in snap.items() if v is not None}
    kind = "support (put OI)" if support else "resistance (call OI)"
    return [Signal(
        id=f"{symbol}_{timeframe}_S14_{side}_{ts_clean}",
        symbol=symbol,
        timeframe=timeframe,
        setup_type=SetupType.SETUP_14_OI_WALL_BOUNCE,
        option_type=side,
        timestamp=ts_str,
        entry_price=round(c, 2),
        stop_loss=strike_rec.stop_loss,
        target_1=strike_rec.target_1,
        target_2=strike_rec.target_2,
        strike_recommendation=strike_rec,
        indicators_snapshot=snap,
        rationale=f"First rejection of the {wall:g} {kind} wall, PCR {walls.pcr:.2f}",
        is_confirmed=True,
    )]
