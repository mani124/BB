from datetime import timedelta

import pandas as pd

from app.services import market_hours, setup_switches
from app.services.indicators import calculate_indicators
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.runtime_settings import BY_KEY
from app.services.setup16 import evaluate_option_squeeze_breakout, session_bands
from app.services.strategy_engine import SetupType, is_setup5


def _start():
    return market_hours.now_ist().replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(hours=3)


def _opt(n=16, last_close=108.0, last_volume=5000, wide_early=False, volume_known=True):
    """Quiet premium around 100 (tight bands), then a breakout bar. ``wide_early`` makes the bars right before
    the breakout swing widely, so there is no squeeze just before it."""
    start = _start()
    rows = []
    for i in range(n):
        if i == n - 1:
            c = last_close
        elif wide_early and i >= n - 8:
            c = 100.0 + (9.0 if i % 2 else -9.0)
        else:
            c = 100.0 + (0.3 if i % 2 else -0.3)
        o = c - 0.2 if i == n - 1 else c
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": o, "high": c + 0.3, "low": c - 0.4,
                     "close": c, "volume": 3000, "volume_known": True})
    rows[-1]["volume"] = last_volume
    rows[-1]["volume_known"] = volume_known
    return calculate_indicators(pd.DataFrame(rows))


def _eval(df, side="CE", **kw):
    return evaluate_option_squeeze_breakout(
        "NIFTY 50", f"NIFTY 22500 {side}", side, df, underlying_price=22500.0, strike_price=22500.0,
        expiry_date="2026-10-29", lot_size=75, option_security_id="111", **kw)


def test_breakout_after_squeeze_fires():
    df = _opt()
    sig = _eval(df, window_start="00:00", window_end="23:59")
    assert sig is not None
    assert sig.setup_type == SetupType.SETUP_16_OPTION_SQUEEZE_BREAK and is_setup5(sig.setup_type)
    assert "_S16_CE_" in sig.id
    assert sig.stop_loss < sig.entry_price < sig.target_1 < sig.target_2
    assert sig.indicators_snapshot["breakout_bw"] > sig.indicators_snapshot["squeeze_bw_min"]


def test_stop_is_nearer_of_lower_band_and_percentage():
    df = _opt()
    # tight bands: the lower band is only a few percent below the close, tighter than a 12% stop
    sig = _eval(df, stop_pct=12.0, window_start="00:00", window_end="23:59")
    lower = sig.indicators_snapshot["lower_bb"]
    assert sig.indicators_snapshot["stop_is_lower_bb"] == 1.0
    # builder never goes tighter than 4% of the close
    assert sig.stop_loss <= sig.entry_price * 0.96 + 0.11 and sig.stop_loss >= min(lower, sig.entry_price * 0.96) - 0.11
    # a very tight percentage stop wins over a lower band that sits further away
    tight = _eval(df, stop_pct=5.0, window_start="00:00", window_end="23:59")
    assert tight.stop_loss >= sig.stop_loss - 0.11
    assert abs((tight.entry_price - tight.stop_loss) - tight.entry_price * 0.05) < 0.6


def test_no_squeeze_before_breakout_blocks():
    df = _opt(wide_early=True)
    assert _eval(df, window_start="00:00", window_end="23:59") is None


def test_close_inside_bands_blocks():
    df = _opt(last_close=100.2)
    assert _eval(df, window_start="00:00", window_end="23:59") is None


def test_volume_rules():
    assert _eval(_opt(last_volume=500), window_start="00:00", window_end="23:59") is None
    assert _eval(_opt(volume_known=False), window_start="00:00", window_end="23:59") is None


def test_needs_session_history():
    assert _eval(_opt(n=10), window_start="00:00", window_end="23:59") is None


def test_time_window_is_a_setting():
    df = _opt()
    ts = pd.to_datetime(df["timestamp"].iloc[-1]).time()
    before = (pd.Timestamp("2026-01-01") + pd.Timedelta(hours=ts.hour, minutes=ts.minute) - pd.Timedelta(minutes=1)).strftime("%H:%M")
    after = (pd.Timestamp("2026-01-01") + pd.Timedelta(hours=ts.hour, minutes=ts.minute) + pd.Timedelta(minutes=1)).strftime("%H:%M")
    assert _eval(df, window_start="00:00", window_end=before) is None
    assert _eval(df, window_start=after, window_end="23:59") is None
    assert _eval(df, window_start=ts.strftime("%H:%M"), window_end=ts.strftime("%H:%M")) is not None


def test_session_bands_ignore_previous_day():
    df = _opt()
    prev = df.iloc[:6].copy()
    prev["timestamp"] = pd.to_datetime(prev["timestamp"]) - pd.Timedelta(days=1)
    prev["close"] = 300.0
    both = calculate_indicators(pd.concat([prev, df], ignore_index=True))
    assert _eval(both, window_start="00:00", window_end="23:59") is not None
    assert session_bands(df["close"]).iloc[-1]["upper"] < 120


def test_wrong_timeframe_or_columns():
    assert _eval(_opt(), timeframe="15m") is None
    assert _eval(_opt().drop(columns=["volume"])) is None


def test_setup5_overlap_and_dedupe_inputs():
    # Setup 5 needs VWAP, RSI >= 58 and a volume surge on top of the band break; on this chart it can fire as well,
    # in which case the scanner keeps Setup 5 and drops Setup 16 (never two entries on one contract).
    df = _opt(last_close=110.0, last_volume=20000)
    s5 = evaluate_option_chart_signal(
        symbol="NIFTY 50", strike_symbol="NIFTY 22500 CE", option_type="CE", option_df=df,
        underlying_price=22500.0, strike_price=22500.0, expiry_date="2026-10-29", lot_size=75,
        option_security_id="111", timeframe="5m")
    s16 = _eval(df, window_start="00:00", window_end="23:59")
    assert s16 is not None
    if s5 is not None:
        assert s5.id.split("_S5_")[0] == s16.id.split("_S16_")[0]


def test_default_switch_is_off_and_settings_registered():
    assert setup_switches.DEFAULT_MODES["16"] == "off"
    assert setup_switches.block_reason(setup_switches.DEFAULT_MODES, SetupType.SETUP_16_OPTION_SQUEEZE_BREAK, "NIFTY 50")
    assert setup_switches.block_reason({**setup_switches.DEFAULT_MODES, "16": "index"},
                                       SetupType.SETUP_16_OPTION_SQUEEZE_BREAK, "NIFTY 50") is None
    for k in ("setup16_stop_pct", "setup16_window_start", "setup16_window_end"):
        assert k in BY_KEY
