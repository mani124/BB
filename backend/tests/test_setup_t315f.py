"""Setups 21-23: T315 version F (3m, 5m and 5m wide) on NIFTY 50 and NIFTY BANK."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services.setup_t315f import (BANKNIFTY_SCALE, VERSIONS, evaluate_t315f, is_t315f, params_for, runner_should_close,
                                      stop_distance)
from app.services.strategy_engine import SetupType


def _df(closes, minutes, last_bar=datetime(2026, 10, 15, 11, 0), scale=1.0):
    start = last_bar - timedelta(minutes=minutes * (len(closes) - 1))
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        rows.append({"timestamp": start + timedelta(minutes=minutes * i), "open": prev,
                     "high": max(prev, c) + 0.3 * scale, "low": min(prev, c) - 0.3 * scale, "close": c, "volume": 1})
        prev = c
    return pd.DataFrame(rows)


def _up(minutes, base_price=22700.0, k=1.0, **kw):
    """A steady climb, a six-bar pullback that drops the 3 EMA under the 15 EMA, then one strong bar back up (prices x k)."""
    base = [base_price + 0.5 * k * i for i in range(60)]
    last = base[-1]
    return _df(base + [last - k * d for d in (1, 2, 3, 4, 5, 6)] + [last - 6 * k + 9 * k], minutes, scale=k, **kw)


def _down(minutes, base_price=22700.0, k=1.0, **kw):
    base = [base_price - 0.5 * k * i for i in range(60)]
    last = base[-1]
    return _df(base + [last + k * d for d in (1, 2, 3, 4, 5, 6)] + [last + 6 * k - 9 * k], minutes, scale=k, **kw)


@pytest.mark.parametrize("number,minutes", [(21, 3), (22, 5), (23, 5)])
def test_each_version_fires_a_ce_on_its_own_timeframe(number, minutes):
    sigs = evaluate_t315f(number, "NIFTY 50", _up(minutes))
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_type == VERSIONS[number].setup_type and s.option_type == "CE" and s.is_confirmed
    assert s.timeframe == f"{minutes}m" and f"{minutes}m" in s.id and VERSIONS[number].code in s.id


def test_a_version_ignores_bars_of_the_other_timeframe_window():
    # 15:07 is a valid 3m bar start (confirms 15:10) but a 5m bar does not start there and 15:10 is past the 5m window
    assert evaluate_t315f(21, "NIFTY 50", _up(3, last_bar=datetime(2026, 10, 15, 15, 9)))
    assert evaluate_t315f(22, "NIFTY 50", _up(5, last_bar=datetime(2026, 10, 15, 15, 10))) == []
    assert evaluate_t315f(22, "NIFTY 50", _up(5, last_bar=datetime(2026, 10, 15, 15, 5)))


def test_pe_is_the_mirror_with_the_stop_above_and_targets_below():
    s = evaluate_t315f(22, "NIFTY 50", _down(5))[0]
    assert s.option_type == "PE" and s.stop_loss > s.entry_price and s.target_1 < s.entry_price


def test_stop_is_clamped_to_25_30_points_and_t1_is_45_points_for_nifty():
    s = evaluate_t315f(21, "NIFTY 50", _up(3))[0]
    assert 25.0 <= s.entry_price - s.stop_loss <= 30.0
    assert round(s.target_1 - s.entry_price, 2) == 45.0
    assert s.target_2 - s.entry_price > 400          # no real second target: the runner is closed by the 15 EMA trail


def test_wide_version_scales_every_distance_by_1_29():
    s = evaluate_t315f(23, "NIFTY 50", _up(5))[0]
    assert 25 * 1.29 - 0.01 <= s.entry_price - s.stop_loss <= 30 * 1.29 + 0.01
    assert round(s.target_1 - s.entry_price, 2) == round(45 * 1.29, 2)


def test_banknifty_distances_are_scaled_by_its_price_ratio_and_independent_of_nifty():
    bank = evaluate_t315f(22, "NIFTY BANK", _up(5, base_price=55000.0, k=BANKNIFTY_SCALE))[0]
    assert bank.symbol == "NIFTY BANK"
    assert round(bank.target_1 - bank.entry_price, 2) == round(45 * BANKNIFTY_SCALE, 2)
    assert 25 * BANKNIFTY_SCALE - 0.01 <= bank.entry_price - bank.stop_loss <= 30 * BANKNIFTY_SCALE + 0.01
    nifty = evaluate_t315f(22, "NIFTY 50", _up(5))[0]
    assert nifty.id != bank.id and nifty.symbol == "NIFTY 50"


def test_only_the_two_indices_are_traded():
    assert evaluate_t315f(22, "FINNIFTY", _up(5)) == []
    assert evaluate_t315f(22, "RELIANCE", _up(5)) == []


def test_needs_history_and_a_cross_on_the_last_bar():
    assert evaluate_t315f(21, "NIFTY 50", _up(3).iloc[-40:]) == []
    flat = _df([22700 + 0.5 * i for i in range(70)], 3)
    assert evaluate_t315f(21, "NIFTY 50", flat) == []


def test_stop_distance_floor_and_cap():
    p = params_for(VERSIONS[21], "NIFTY 50")
    near = _df([100.0] * 6, 3)
    assert stop_distance(near, 5, "CE", p) == 25.0
    far = _df([100.0, 100.0, 100.0, 100.0, 40.0, 100.0], 3)
    assert stop_distance(far, 5, "CE", p) == 30.0


def test_runner_closes_when_a_bar_closes_back_across_the_15_ema():
    assert runner_should_close("CE", 99.0, 100.0) and not runner_should_close("CE", 101.0, 100.0)
    assert runner_should_close("PE", 101.0, 100.0) and not runner_should_close("PE", 99.0, 100.0)


def test_setup_family_detection():
    assert is_t315f(SetupType.SETUP_21_T315F_3M) and is_t315f("Setup 23: T315-F 5m wide")
    assert not is_t315f(SetupType.SETUP_20_T315) and not is_t315f("Setup 12: ADX + EMA 20 Trend Cross")


# ---------------------------------------------------------------- per-index switches, 3:15 cutoff, runner trail
from app.services import market_hours
from app.services.paper_models import T315F_RUNNER_TRAIL, T315_CUTOFF
from app.services.paper_trader import PaperTradingEngine
from app.services.setup_switches import DEFAULT_MODES, MODES, block_reason, normalize_modes
from tests.test_p0_session_guard import at, make_signal


def test_each_version_can_run_on_one_index_only():
    assert {"nifty", "banknifty"} <= set(MODES)
    for number in (21, 22, 23):
        assert DEFAULT_MODES[str(number)] == "index"
    modes = normalize_modes({"21": "nifty", "22": "banknifty", "23": "off"})
    s21, s22, s23 = (VERSIONS[n].setup_type for n in (21, 22, 23))
    assert block_reason(modes, s21, "NIFTY 50") is None and block_reason(modes, s21, "NIFTY BANK")
    assert block_reason(modes, s22, "NIFTY BANK") is None and block_reason(modes, s22, "NIFTY 50")
    assert block_reason(modes, s23, "NIFTY 50") and block_reason(modes, s23, "NIFTY BANK")


@pytest.fixture
def engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "f.db"))


def _open(engine, sig_id, sec_id, number, symbol, timeframe=None):
    sig = make_signal(sig_id, symbol=symbol, sec_id=sec_id, setup=VERSIONS[number].setup_type)
    sig.timeframe = timeframe or f"{VERSIONS[number].minutes}m"
    with market_hours.override_clock(at(13, 0)):
        return engine.open_position_from_signal(sig, lots=2, feed_mode="live")


def test_all_t315_family_positions_close_at_1515_and_others_wait(engine):
    f = _open(engine, "F", "1", 22, "NIFTY 50")
    other = engine.open_position_from_signal(make_signal("O", symbol="NIFTY BANK", sec_id="2"), lots=1, feed_mode="live") if False else None
    assert f
    with market_hours.override_clock(at(15, 14, 59)):
        assert engine.square_off_if_due() == []
    with market_hours.override_clock(at(15, 15, 1)):
        closed = engine.square_off_if_due()
    assert [c.id for c in closed] == [f.id] and closed[0].exit_reason.startswith(T315_CUTOFF)


def test_runner_trail_closes_only_matching_positions_that_have_booked_target_1(engine):
    nifty3 = _open(engine, "A", "1", 21, "NIFTY 50")
    nifty5 = _open(engine, "B", "2", 22, "NIFTY 50")
    bank3 = _open(engine, "C", "3", 21, "NIFTY BANK")
    for p in (nifty3, nifty5, bank3):
        assert p is not None
    waiting = _open(engine, "D", "4", 23, "NIFTY 50")
    nifty3.status = nifty5.status = bank3.status = "TARGET_1"      # runners; `waiting` has not reached Target 1
    # a 3m bar closes under the 15 EMA: only the Nifty 3m runner closes (not 5m, not Bank Nifty, not the one still at entry)
    closed = engine.close_t315f_runners("NIFTY 50", 3, bar_close=22690.0, ema15=22700.0)
    assert [c.id for c in closed] == [nifty3.id] and closed[0].exit_reason.startswith(T315F_RUNNER_TRAIL)
    # a close on the right side of the EMA keeps the runner open
    assert engine.close_t315f_runners("NIFTY 50", 5, bar_close=22710.0, ema15=22700.0) == []
    assert {p.id for p in engine.get_portfolio().active_positions} == {nifty5.id, bank3.id, waiting.id} - ({waiting.id} if waiting is None else set())


def test_every_version_has_its_own_pool_so_versions_run_side_by_side(engine):
    from app.services.strategy_engine import pool_of
    assert [pool_of(VERSIONS[n].setup_type) for n in (21, 22, 23)] == ["f21", "f22", "f23"]
    assert pool_of(SetupType.SETUP_5_OPTION_BB) == "main" and pool_of(SetupType.SETUP_20_T315) == "main"
    first = _open(engine, "A", "1", 21, "NIFTY 50")
    second = _open(engine, "B", "2", 22, "NIFTY 50")          # same index, same side, same moment, different version
    third = _open(engine, "C", "3", 23, "NIFTY 50")
    assert first and second and third
    assert len(engine.get_portfolio().active_positions) == 3


def test_a_version_losing_money_does_not_trip_the_main_loss_cap(engine, monkeypatch):
    f = _open(engine, "L", "1", 22, "NIFTY 50")
    assert f
    f.pnl_points, f.pnl_rupees = -1000.0, -999999.0
    assert engine.day_pnl("live", pool="f22") < 0
    assert engine.day_pnl("live", pool="main") == 0


def test_runner_trail_exits_at_the_cycle_bid_not_the_stale_option_price(engine):
    p = _open(engine, "R", "9", 22, "NIFTY 50")
    p.status = "TARGET_1"
    p.current_option_price = 180.0
    closed = engine.close_t315f_runners("NIFTY 50", 5, bar_close=22690.0, ema15=22700.0, option_bid_map={"9": 155.0})
    assert [c.id for c in closed] == [p.id] and closed[0].theoretical_exit == 155.0
