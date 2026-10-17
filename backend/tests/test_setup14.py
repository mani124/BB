from datetime import datetime, timedelta

import pandas as pd

from app.services.setup14 import (
    OIWalls, compute_oi_walls, evaluate_oi_wall_bounce, MAX_CHAIN_AGE_S,
)
from app.services.setup_switches import block_reason, DEFAULT_MODES
from app.services.strategy_engine import SetupType

START = datetime(2026, 10, 15, 9, 15)


def _chain(put_oi=None, call_oi=None, strikes=range(22000, 23001, 50)):
    put_oi, call_oi = put_oi or {}, call_oi or {}
    return {str(float(k)): {"ce": {"oi": call_oi.get(k, 1000)}, "pe": {"oi": put_oi.get(k, 1000)}} for k in strikes}


def _walls(**kw):
    base = dict(spot=22500.0, pcr=1.4, support_strike=22400.0, support_oi=9000.0, support_ratio=3.0,
                resistance_strike=22600.0, resistance_oi=8000.0, resistance_ratio=2.5)
    base.update(kw)
    return OIWalls(**base)


def _bars(last, n=8, atr=40.0, start=START):
    """n-1 quiet bars around 22500 (far from either wall) followed by `last` = (open, high, low, close)."""
    rows = []
    for i in range(n - 1):
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": 22500.0, "high": 22510.0,
                     "low": 22490.0, "close": 22500.0, "atr": atr})
    o, h, l, c = last
    rows.append({"timestamp": start + timedelta(minutes=5 * (n - 1)), "open": o, "high": h, "low": l, "close": c, "atr": atr})
    return pd.DataFrame(rows)


SUPPORT_BAR = (22405.0, 22412.0, 22380.0, 22410.0)    # wicks through 22400, closes back above, wick 25 > body 5
RESIST_BAR = (22595.0, 22620.0, 22588.0, 22590.0)     # wicks through 22600, closes back below


def test_wall_needs_dominance_over_both_neighbours():
    oc = _chain(put_oi={22400: 9000, 22350: 5000, 22450: 4000}, call_oi={22600: 8000, 22550: 2000, 22650: 7000})
    w = compute_oi_walls(oc, 22500.0)
    assert w.support_strike == 22400.0 and w.support_ratio == 1.8
    assert w.resistance_strike is None  # 8000 vs neighbour 7000 is below 1.5x


def test_wall_uses_correct_side_of_spot():
    oc = _chain(put_oi={22400: 9000, 22600: 20000}, call_oi={22600: 8000, 22400: 20000})
    w = compute_oi_walls(oc, 22500.0)
    assert w.support_strike == 22400.0 and w.resistance_strike == 22600.0


def test_pcr_is_total_put_over_call_oi_and_missing_oi_gives_none():
    oc = _chain(put_oi={22400: 9000}, call_oi={22600: 4000})
    w = compute_oi_walls(oc, 22500.0)
    n = len(oc)
    assert w.pcr == round((9000 + 1000 * (n - 1)) / (4000 + 1000 * (n - 1)), 3)
    assert compute_oi_walls({"22500.0": {"ce": {}, "pe": {}}}, 22500.0) is None
    assert compute_oi_walls({}, 22500.0) is None


def test_support_bounce_fires_ce():
    sigs = evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(), chain_age_s=10.0)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_type == SetupType.SETUP_14_OI_WALL_BOUNCE and s.option_type == "CE" and s.is_confirmed
    assert "_S14_CE_" in s.id
    assert s.stop_loss < 22400.0 and s.stop_loss < s.entry_price < s.target_1 < s.target_2  # candle low is below the wall
    assert s.indicators_snapshot["wall_strike"] == 22400.0 and s.indicators_snapshot["opposite_wall"] == 22600.0


def test_stop_uses_tighter_of_wall_and_candle_low():
    bar = (22405.0, 22412.0, 22404.0, 22410.0)  # low above the wall but within 0.1 ATR; no lower wick -> no signal
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(bar), _walls(), chain_age_s=5.0) == []
    bar = (22408.0, 22412.0, 22402.0, 22404.0)  # touches within 0.1 ATR, wick 2 < body 4: no
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(bar), _walls(), chain_age_s=5.0) == []
    bar = (22406.0, 22412.0, 22402.0, 22405.0)  # wick 3 >= body 1, low 22402 above wall -> stop under the low, not the wall
    s = evaluate_oi_wall_bounce("NIFTY 50", _bars(bar), _walls(), chain_age_s=5.0)[0]
    assert s.stop_loss < 22402.0 and s.stop_loss > 22385.0  # under the candle low (22402), not 25 points under the wall


def test_resistance_rejection_fires_pe_when_pcr_low():
    sigs = evaluate_oi_wall_bounce("NIFTY 50", _bars(RESIST_BAR), _walls(pcr=0.7), chain_age_s=10.0)
    assert len(sigs) == 1 and sigs[0].option_type == "PE"
    assert 22600.0 < sigs[0].stop_loss < 22620.0 and sigs[0].target_1 < sigs[0].entry_price


def test_pcr_between_bounds_skips():
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(pcr=1.0), chain_age_s=5.0) == []
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(RESIST_BAR), _walls(pcr=1.0), chain_age_s=5.0) == []


def test_pcr_bias_must_match_side():
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(pcr=0.7), chain_age_s=5.0) == []
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(RESIST_BAR), _walls(pcr=1.4), chain_age_s=5.0) == []


def test_close_must_be_back_across_wall():
    bar = (22405.0, 22412.0, 22380.0, 22395.0)  # closes below support: a break, not a rejection
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(bar), _walls(), chain_age_s=5.0) == []


def test_wick_must_be_at_least_body():
    bar = (22380.0, 22440.0, 22379.0, 22430.0)  # big body, tiny lower wick
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(bar), _walls(), chain_age_s=5.0) == []


def test_only_first_touch_of_wall():
    df = _bars(SUPPORT_BAR)
    df.loc[3, ["low"]] = 22395.0  # an earlier bar already tested the wall
    assert evaluate_oi_wall_bounce("NIFTY 50", df, _walls(), chain_age_s=5.0) == []


def test_stale_or_unknown_chain_age_blocks():
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(), chain_age_s=MAX_CHAIN_AGE_S + 1) == []
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(), chain_age_s=None) == []
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), None, chain_age_s=5.0) == []


def test_window_and_warmup():
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR, n=2), _walls(), chain_age_s=5.0) == []
    late = datetime(2026, 10, 15, 14, 0)  # last bar starts at 14:35 -> after 14:25
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR, n=8, start=late), _walls(), chain_age_s=5.0) == []
    ok = datetime(2026, 10, 15, 13, 50)   # last bar starts at 14:25 -> allowed
    assert len(evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR, n=8, start=ok), _walls(), chain_age_s=5.0)) == 1


def test_wrong_timeframe_blocks():
    assert evaluate_oi_wall_bounce("NIFTY 50", _bars(SUPPORT_BAR), _walls(), timeframe="15m", chain_age_s=5.0) == []


def test_default_switch_is_index_only():
    assert DEFAULT_MODES["14"] == "index"
    assert block_reason(DEFAULT_MODES, SetupType.SETUP_14_OI_WALL_BOUNCE, "RELIANCE")
    assert block_reason(DEFAULT_MODES, SetupType.SETUP_14_OI_WALL_BOUNCE, "NIFTY 50") is None
    assert DEFAULT_MODES["1"] == "index" and DEFAULT_MODES["5"] == "all"
