import pandas as pd

from app.services import setup_switches
from app.services.indicators import calculate_indicators
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.paper_trader import PaperTradingEngine
from app.services.setup11 import evaluate_setup11, setup11_filter_reason
from app.services.strategy_engine import SetupType, is_setup5, is_setup11
from app.services.strike_selector import recommend_strike
from tests.test_option_chart_strategy import _now, create_option_candles


def _s5(last=None):
    df = create_option_candles(n=30, base_premium=100.0)
    df.loc[29] = last or {"timestamp": _now(), "open": 101.0, "high": 115.0, "low": 100.5, "close": 114.0,
                          "volume": 45000}
    ind = calculate_indicators(df)
    sig = evaluate_option_chart_signal(
        symbol="RELIANCE", strike_symbol="RELIANCE 3000 CE", option_type="CE", option_df=ind,
        underlying_price=2985.0, strike_price=3000.0, expiry_date="2026-10-29", lot_size=250,
        option_security_id="777", timeframe="5m",
    )
    return ind, sig


def test_clean_setup5_signal_becomes_setup11():
    ind, s5 = _s5()
    assert s5 is not None and setup11_filter_reason(ind, s5) is None
    s11 = evaluate_setup11(ind, s5)
    assert s11 is not None
    assert s11.setup_type == SetupType.SETUP_11_FILTERED_OPTION_BB
    assert "_S11_" in s11.id and "_S5_" in s5.id
    assert (s11.entry_price, s11.stop_loss, s11.target_1, s11.target_2) == (
        s5.entry_price, s5.stop_loss, s5.target_1, s5.target_2)
    assert s11.strike_recommendation is not s5.strike_recommendation  # separate copy, no aliasing
    assert is_setup5(s11.setup_type) and is_setup11(s11.setup_type) and not is_setup11(s5.setup_type)


def test_no_setup5_signal_means_no_setup11():
    ind, _ = _s5()
    assert evaluate_setup11(ind, None) is None


def test_rsi_not_rising_fails_trend_strength():
    ind, s5 = _s5()
    ind.loc[ind.index[-2], "rsi"] = float(ind.iloc[-1]["rsi"]) + 1.0
    assert "RSI not rising" in setup11_filter_reason(ind, s5)
    assert evaluate_setup11(ind, s5) is None


def test_bandwidth_not_rising_fails_trend_strength():
    ind, s5 = _s5()
    ind.loc[ind.index[-2], "bandwidth"] = float(ind.iloc[-1]["bandwidth"]) + 1.0
    assert "BandWidth not rising" in setup11_filter_reason(ind, s5)


def test_long_upper_wick_fails_candle_quality():
    ind, s5 = _s5()
    ind.loc[ind.index[-1], "high"] = 140.0  # close now sits near the bottom of a tall bar
    assert "upper wick" in setup11_filter_reason(ind, s5)


def test_red_signal_candle_fails_candle_quality():
    ind, s5 = _s5()
    ind.loc[ind.index[-1], "open"] = 114.5
    assert "not green" in setup11_filter_reason(ind, s5)


def test_wide_stop_fails_stop_width_cap():
    ind, s5 = _s5()
    wide = s5.model_copy(deep=True)
    wide.stop_loss = round(wide.entry_price * 0.6, 1)  # 40% below
    assert "below the fill" in setup11_filter_reason(ind, wide)


def test_stop_width_uses_live_ask_when_higher_than_signal_close():
    ind, s5 = _s5()
    s5.strike_recommendation.real_ask_price = s5.entry_price * 1.5  # chased fill: the stop is now far below it
    s5.stop_loss = round(s5.entry_price * 0.9, 1)  # only 10% below the signal close
    assert "below the fill" in setup11_filter_reason(ind, s5)


def test_setup11_has_a_switch_defaulting_to_all():
    assert setup_switches.DEFAULT_MODES["11"] == "all"
    assert setup_switches.setup_number(SetupType.SETUP_11_FILTERED_OPTION_BB) == "11"
    assert setup_switches.block_reason({"11": "off"}, SetupType.SETUP_11_FILTERED_OPTION_BB, "TCS")
    assert setup_switches.block_reason({"11": "off", "5": "all"}, SetupType.SETUP_5_OPTION_BB, "TCS") is None


def _engine(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    e.set_auto_trade(True)
    return e


def _rec_signal(sig_id, setup):
    rec = recommend_strike("FINNIFTY", 25000.0, "CE", 24980.0)
    from app.services.strategy_engine import Signal
    return Signal(id=sig_id, symbol="FINNIFTY", timeframe="5m", setup_type=setup, option_type="CE",
                  timestamp="10:20:00", entry_price=25000.0, stop_loss=24980.0, target_1=rec.target_1,
                  target_2=rec.target_2, strike_recommendation=rec, indicators_snapshot={}, rationale="t")


def test_setup11_runs_next_to_setup5_on_the_same_contract(tmp_path):
    e = _engine(tmp_path)
    p5 = e.open_position_from_signal(_rec_signal("A_S5_x", SetupType.SETUP_5_OPTION_BB))
    p11 = e.open_position_from_signal(_rec_signal("A_S11_x", SetupType.SETUP_11_FILTERED_OPTION_BB))
    assert p5 is not None and p11 is not None
    # but Setup 11 still gets one position per contract of its own
    again = e.open_position_from_signal(_rec_signal("B_S11_y", SetupType.SETUP_11_FILTERED_OPTION_BB))
    assert again is None


def test_setup11_has_its_own_loss_cap(tmp_path, monkeypatch):
    e = _engine(tmp_path)
    monkeypatch.setattr(e, "day_pnl", lambda book=None, pool="main": -30000.0 if pool == "s11" else 0.0)
    assert e.risk_block_reason("demo", pool="s11") is not None
    assert e.risk_block_reason("demo", pool="main") is None


def test_day_pnl_splits_setup11_from_the_rest(tmp_path):
    e = _engine(tmp_path)
    e.open_position_from_signal(_rec_signal("A_S5_x", SetupType.SETUP_5_OPTION_BB))
    e.open_position_from_signal(_rec_signal("A_S11_x", SetupType.SETUP_11_FILTERED_OPTION_BB))
    for p in e.get_portfolio().active_positions:
        p.pnl_points = -10.0 if is_setup11(p.setup_type) else 4.0
    main, s11, both = e.day_pnl(pool="main"), e.day_pnl(pool="s11"), e.day_pnl(pool=None)
    assert s11 < 0 < main
    assert abs(both - (main + s11)) < 0.01
