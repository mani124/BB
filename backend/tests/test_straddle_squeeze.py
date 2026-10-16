from datetime import timedelta

import pandas as pd

from app.services import market_hours, setup_switches
from app.services.indicators import calculate_indicators
from app.services.straddle_squeeze import StraddleLeg, build_straddle_frame, evaluate_straddle_squeeze
from app.services.strategy_engine import SetupType, is_setup5


def _start():
    return market_hours.now_ist().replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(hours=3)


def _leg_df(base, n=30, wiggle=0.2, last=None, last_volume=40000, vols=10000, step_amp=None):
    """n flat-ish bars around ``base``; ``last`` = (open, high, low, close) replaces the final bar."""
    start = _start()
    rows = []
    for i in range(n):
        d = (wiggle if i % 2 == 0 else -wiggle) * (step_amp or 1.0)
        c = base + d
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": c - 0.05, "high": c + 0.1,
                     "low": c - 0.1, "close": c, "volume": vols})
    if last:
        o, h, l, c = last
        rows[-1] = {**rows[-1], "open": o, "high": h, "low": l, "close": c, "volume": last_volume}
    return calculate_indicators(pd.DataFrame(rows))


def _legs(ce_last=(100, 112.5, 99.9, 112), pe_last=(100, 100.1, 93.9, 94), **kw):
    ce = _leg_df(100.0, last=ce_last, **kw)
    pe = _leg_df(100.0, last=pe_last, **{**kw, "last_volume": 20000})
    return {
        "CE": StraddleLeg(ce, "NIFTY 22500 CE", "111", {"last_price": 112.0, "is_live_quote": True}),
        "PE": StraddleLeg(pe, "NIFTY 22500 PE", "222", {"last_price": 94.0, "is_live_quote": True}),
    }


def _eval(legs):
    return evaluate_straddle_squeeze("NIFTY 50", legs, underlying_price=22500.0, strike_price=22500.0,
                                     expiry_date="2026-10-15", lot_size=75)


def test_ce_leg_leads_after_squeeze():
    sig = _eval(_legs())
    assert sig is not None
    assert sig.setup_type == SetupType.SETUP_10_STRADDLE_SQUEEZE
    assert sig.option_type == "CE"
    assert sig.strike_recommendation.strike_symbol == "NIFTY 22500 CE"
    assert sig.strike_recommendation.option_security_id == "111"
    assert sig.stop_loss < sig.entry_price < sig.target_1 < sig.target_2
    assert "_S10_CE_" in sig.id
    assert sig.indicators_snapshot["straddle_close"] > sig.indicators_snapshot["straddle_bb_upper"]


def test_pe_leg_leads_mirrored():
    sig = _eval(_legs(ce_last=(100, 100.1, 93.9, 94), pe_last=(100, 112.5, 99.9, 112)))
    assert sig is not None and sig.option_type == "PE"


def test_both_legs_rising_is_a_volatility_spike_not_a_direction():
    assert _eval(_legs(ce_last=(100, 108.5, 99.9, 108), pe_last=(100, 106.5, 99.9, 106))) is None


def _closes_leg(closes, last_volume=40000):
    start = _start()
    rows = [{"timestamp": start + timedelta(minutes=5 * i), "open": c - 0.05, "high": c + 0.1, "low": c - 0.1,
             "close": c, "volume": 10000} for i, c in enumerate(closes)]
    rows[-1]["open"] = closes[-2]
    rows[-1]["volume"] = last_volume
    return calculate_indicators(pd.DataFrame(rows))


def _wide_or_tight_legs(wide):
    tight = [100 + (0.2 if i % 2 == 0 else -0.2) for i in range(26)]
    # "wide": big swings in the 3 bars before the trigger (BandWidth far above its 20-bar minimum)
    mid = [106, 94, 106] if wide else [100.2, 99.8, 100.2]
    ce = tight + mid + [124]
    pe = tight + mid + [95]
    return {
        "CE": StraddleLeg(_closes_leg(ce), "NIFTY 22500 CE", "111", {"last_price": 124.0}),
        "PE": StraddleLeg(_closes_leg(pe, last_volume=20000), "NIFTY 22500 PE", "222", {"last_price": 95.0}),
    }


def test_squeeze_is_what_gates_the_signal():
    # Same trigger bar; the only difference is whether the straddle was squeezed beforehand.
    assert _eval(_wide_or_tight_legs(wide=False)) is not None
    assert _eval(_wide_or_tight_legs(wide=True)) is None


def test_small_leg_gain_is_rejected():
    assert _eval(_legs(ce_last=(100, 102.5, 99.9, 102), pe_last=(100, 100.1, 99.0, 99.2))) is None


def test_low_volume_is_rejected():
    assert _eval(_legs(last_volume=500)) is None


def test_misaligned_last_bar_is_rejected():
    legs = _legs()
    pe = legs["PE"].df.iloc[:-1].copy()
    legs["PE"].df = pe
    assert _eval(legs) is None


def test_needs_both_legs_and_enough_bars():
    legs = _legs()
    assert _eval({"CE": legs["CE"]}) is None
    short = {k: StraddleLeg(v.df.iloc[-19:].reset_index(drop=True), v.strike_symbol, v.security_id) for k, v in legs.items()}
    assert _eval(short) is None


def test_straddle_frame_is_leg_sum_on_shared_timestamps():
    legs = _legs()
    sd = build_straddle_frame(legs["CE"].df, legs["PE"].df)
    assert len(sd) == 30
    assert abs(sd["close"].iloc[-1] - (112 + 94)) < 1e-9


def test_setup10_is_option_chart_managed_and_index_only_by_default():
    assert is_setup5(SetupType.SETUP_10_STRADDLE_SQUEEZE)
    assert is_setup5("Setup 10: ATM Straddle Premium Squeeze")
    assert not is_setup5("Setup 1: BB Squeeze Breakout")
    modes = setup_switches.normalize_modes(None)
    assert modes["10"] == "index"
    assert setup_switches.setup_number(SetupType.SETUP_10_STRADDLE_SQUEEZE) == "10"
    assert setup_switches.block_reason(modes, SetupType.SETUP_10_STRADDLE_SQUEEZE, "RELIANCE")
    assert setup_switches.block_reason(modes, SetupType.SETUP_10_STRADDLE_SQUEEZE, "NIFTY 50") is None
