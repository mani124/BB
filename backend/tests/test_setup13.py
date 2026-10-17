from datetime import timedelta

import pandas as pd

from app.services import market_hours, setup_switches
from app.services.indicators import calculate_indicators
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.setup13 import evaluate_option_vwap_reclaim
from app.services.strategy_engine import SetupType, is_setup5


def _start():
    return market_hours.now_ist().replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(hours=3)


def _opt(n=30, dip=2, last_volume=5000, volume_known=True):
    """Premium ~100 for n-dip-1 bars, ``dip`` bars well under VWAP, then a reclaim bar closing above it."""
    start = _start()
    rows = []
    for i in range(n):
        if i < n - 1 - dip:
            c = 100.0 + 0.2 * i  # steady up-leg, so the premium holds above its VWAP
        elif i < n - 1:
            c = 92.0 - 0.3 * (i - (n - 1 - dip))
        else:
            c = 112.0
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": c - 0.2, "high": c + 0.3,
                     "low": c - 0.4, "close": c, "volume": 3000, "volume_known": True})
    rows[-1]["volume"] = last_volume
    rows[-1]["volume_known"] = volume_known
    return calculate_indicators(pd.DataFrame(rows))


def _spot(opt_df, side="up"):
    rows = []
    for i, ts in enumerate(opt_df["timestamp"]):
        base = 22500.0
        c = base + (30.0 if side == "up" else -30.0) if i == len(opt_df) - 1 else base
        rows.append({"timestamp": ts, "open": base, "high": c + 5, "low": c - 5, "close": c, "volume": 0})
    df = pd.DataFrame(rows)
    df["vwap"] = 22500.0 + (0.0)  # spot VWAP pinned at the day's base
    return df


def _eval(opt, spot, side="CE", **kw):
    return evaluate_option_vwap_reclaim(
        "NIFTY 50", f"NIFTY 22500 {side}", side, opt, spot, underlying_price=22500.0, strike_price=22500.0,
        expiry_date="2026-10-29", lot_size=75, option_security_id="111", **kw)


def test_reclaim_after_dip_fires_ce():
    opt = _opt()
    assert opt["close"].iloc[-2] < opt["vwap"].iloc[-2] and opt["close"].iloc[-1] > opt["vwap"].iloc[-1]
    sig = _eval(opt, _spot(opt, "up"))
    assert sig is not None
    assert sig.setup_type == SetupType.SETUP_13_OPTION_VWAP_RECLAIM and is_setup5(sig.setup_type)
    assert "_S13_CE_" in sig.id
    assert sig.stop_loss < sig.entry_price < sig.target_1 < sig.target_2
    risk = sig.entry_price - sig.stop_loss
    assert abs((sig.target_1 - sig.entry_price) - 1.5 * risk) < 0.2
    assert abs((sig.target_2 - sig.entry_price) - 2.5 * risk) < 0.2
    assert risk >= 0.04 * sig.entry_price - 0.1
    assert sig.indicators_snapshot["dip_bars"] == 2


def test_pe_uses_option_vwap_with_spot_below_vwap():
    opt = _opt()
    assert _eval(opt, _spot(opt, "down"), side="PE") is not None
    assert _eval(opt, _spot(opt, "up"), side="PE") is None


def test_spot_on_wrong_side_blocks_ce():
    opt = _opt()
    assert _eval(opt, _spot(opt, "down")) is None


def test_missing_or_misaligned_spot_blocks():
    opt = _opt()
    assert _eval(opt, None) is None
    spot = _spot(opt)
    spot["timestamp"] = pd.to_datetime(spot["timestamp"]) + timedelta(minutes=5)
    assert _eval(opt, spot) is None


def test_dip_longer_than_five_bars_blocks():
    opt = _opt(n=34, dip=6)
    assert _eval(opt, _spot(opt)) is None
    opt = _opt(n=34, dip=5)
    assert _eval(opt, _spot(opt)) is not None


def test_no_dip_means_no_signal():
    opt = _opt(dip=0)  # steady above VWAP, no pullback
    assert _eval(opt, _spot(opt)) is None


def test_volume_lift_required():
    opt = _opt(last_volume=2000)  # below the prior-3 average
    assert _eval(opt, _spot(opt)) is None
    opt = _opt(last_volume=500)   # below the 1,000 floor
    assert _eval(opt, _spot(opt)) is None


def test_unknown_volume_blocks():
    opt = _opt(volume_known=False)
    assert _eval(opt, _spot(opt)) is None


def test_session_warmup_20_bars():
    opt = _opt(n=19)
    assert _eval(opt, _spot(opt)) is None


def test_no_entries_after_1430():
    start = market_hours.now_ist().replace(tzinfo=None, hour=14, minute=30, second=0, microsecond=0)
    opt = _opt()
    shift = start - pd.to_datetime(opt["timestamp"].iloc[-1])
    opt["timestamp"] = pd.to_datetime(opt["timestamp"]) + shift
    spot = _spot(opt)
    assert _eval(opt, spot) is None


def test_setup5_logic_unchanged_by_stop_override():
    # Setup 5 does not pass a stop price, so its stop formula is the original one.
    from tests.test_option_chart_strategy import _now, create_option_candles
    df = create_option_candles(n=30, base_premium=100.0)
    df.loc[29] = {"timestamp": _now(), "open": 101.0, "high": 115.0, "low": 100.5, "close": 114.0, "volume": 45000}
    ind = calculate_indicators(df)
    sig = evaluate_option_chart_signal(
        symbol="NIFTY 50", strike_symbol="NIFTY 22500 CE", option_type="CE", option_df=ind,
        underlying_price=22500.0, strike_price=22500.0, expiry_date="2026-10-29", lot_size=75,
        option_security_id="1", timeframe="5m")
    last = ind.iloc[-1]
    close, ema9 = float(last["close"]), float(last["ema_9"])
    rng = max(float(last["high"] - last["low"]), close * 0.04)
    expected = round(max(close - ema9, rng * 0.5, close * 0.04), 1)
    assert sig is not None and abs((sig.entry_price - sig.stop_loss) - expected) < 0.11


def test_default_switch_is_index_only():
    assert setup_switches.DEFAULT_MODES["13"] == "index"
    assert setup_switches.block_reason(setup_switches.DEFAULT_MODES, SetupType.SETUP_13_OPTION_VWAP_RECLAIM, "RELIANCE")
    assert setup_switches.block_reason(setup_switches.DEFAULT_MODES, SetupType.SETUP_13_OPTION_VWAP_RECLAIM, "NIFTY 50") is None
