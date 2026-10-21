"""Setup 5 stock quality gate: volatility band and open-interest floor."""
from types import SimpleNamespace

import pytest

from app.services import setup5_quality as q
from app.services.paper_trader import PaperTradingEngine
from app.services.strategy_engine import SetupType
from tests.test_paper_reentry_gate import make_test_signal


def _bars(n, range_pct):
    return [{"high": 100 * (1 + range_pct / 200), "low": 100 * (1 - range_pct / 200), "close": 100.0} for _ in range(n)]


def test_stock_range_is_the_mean_bar_range_in_percent():
    assert q.stock_range_pct(_bars(60, 0.25)) == pytest.approx(0.25, abs=1e-3)


def test_too_little_history_means_unmeasured_not_blocked():
    assert q.stock_range_pct(_bars(10, 0.25)) is None
    assert q.stock_range_pct(None) is None


def _signal(symbol="TCS", rng=0.25, setup=SetupType.SETUP_5_OPTION_BB):
    sig = make_test_signal("Q1", symbol=symbol)
    sig.setup_type = setup
    sig.indicators_snapshot["stock_range_pct"] = rng
    return sig


def _rec(oi):
    return SimpleNamespace(real_oi=oi)


KW = dict(enabled=True, range_min=0.20, range_max=0.30, min_oi=300000)


def test_a_stock_inside_the_band_with_liquid_oi_passes():
    assert q.block_reason(_signal(rng=0.25), _rec(500000), **KW) is None


def test_quiet_and_volatile_stocks_are_skipped():
    assert q.block_reason(_signal(rng=0.15), _rec(500000), **KW)[0] == "S5_VOLATILITY_BAND"
    assert q.block_reason(_signal(rng=0.35), _rec(500000), **KW)[0] == "S5_VOLATILITY_BAND"


def test_thin_open_interest_is_skipped():
    assert q.block_reason(_signal(rng=0.25), _rec(100000), **KW)[0] == "S5_LOW_OI"


def test_missing_data_never_blocks():
    assert q.block_reason(_signal(rng=None), _rec(None), **KW) is None


def test_zero_switches_a_check_off_and_the_gate_can_be_disabled():
    assert q.block_reason(_signal(rng=0.15), _rec(100000), **{**KW, "range_min": 0, "min_oi": 0}) is None
    assert q.block_reason(_signal(rng=0.15), _rec(100000), **{**KW, "enabled": False}) is None


def test_indices_and_other_setups_are_untouched():
    assert q.block_reason(_signal(symbol="NIFTY 50", rng=0.05), _rec(10), **KW) is None
    assert q.block_reason(_signal(rng=0.05, setup=SetupType.SETUP_1_SQUEEZE), _rec(10), **KW) is None


def test_the_engine_skips_and_logs_a_quiet_stock_entry(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    sig = _signal(rng=0.12)
    assert e.open_position_from_signal(sig) is None
    assert sig.id in e._processed_signal_ids


def test_the_engine_still_opens_an_in_band_stock_entry(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    sig = _signal(rng=0.25)
    sig.strike_recommendation.real_oi = 900000
    assert e.open_position_from_signal(sig) is not None


def test_the_settings_exist_with_the_agreed_defaults(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    r = e.runtime
    assert r.get("setup5_quality_gate_enabled") is True
    assert (r.get("setup5_range_min_pct"), r.get("setup5_range_max_pct"), r.get("setup5_min_oi")) == (0.20, 0.30, 300000.0)
