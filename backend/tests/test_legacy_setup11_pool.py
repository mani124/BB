"""Legacy Setup 11 pool handling: Setup 11 no longer generates signals (removed 2026-10-19), but its past
trades stay in the database and must keep their own loss pool."""
from app.services.paper_trader import PaperTradingEngine
from app.services.strategy_engine import SetupType, is_setup11
from app.services.strike_selector import recommend_strike


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
