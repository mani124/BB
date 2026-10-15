from datetime import datetime

import pytest
from starlette.testclient import TestClient

from app.services import market_hours
from app.services.paper_trader import PaperTradingEngine
from tests.test_paper_reentry_gate import make_test_signal

IST = market_hours.IST
MORNING = datetime(2026, 10, 14, 10, 30, tzinfo=IST)  # a Wednesday
NEXT_DAY = datetime(2026, 10, 15, 10, 30, tzinfo=IST)


@pytest.fixture(autouse=True)
def _clock():
    with market_hours.override_clock(MORNING):
        yield


def _engine(tmp_path, limit=1000.0, name="t.db"):
    e = PaperTradingEngine(db_path=str(tmp_path / name))
    e.set_daily_loss_limit(limit)
    return e


def _lose(e, sig_id, symbol="FINNIFTY", points=-30.0):
    """Open a position and close it at a loss of ~`points` option points."""
    pos = e.open_position_from_signal(make_test_signal(sig_id, symbol=symbol))
    assert pos is not None
    e.close_position(pos.id, reason="x", exit_price=pos.option_entry + points)
    return pos


def test_loss_cap_blocks_entries_after_realised_loss(tmp_path):
    e = _engine(tmp_path, limit=500)
    _lose(e, "S1")
    assert e.day_pnl() <= -500
    assert e.open_position_from_signal(make_test_signal("S2", symbol="NIFTY")) is None
    st = e.risk_status("demo")
    assert st.loss_cap_tripped and st.entries_blocked and "loss cap" in st.block_reason


def test_loss_below_limit_still_allows_entries(tmp_path):
    e = _engine(tmp_path, limit=10_000_000)
    _lose(e, "S1")
    assert e.open_position_from_signal(make_test_signal("S2", symbol="NIFTY")) is not None
    assert not e.risk_status("demo").entries_blocked


def test_unrealised_loss_counts_and_trip_is_latched(tmp_path):
    e = _engine(tmp_path, limit=500)
    pos = e.open_position_from_signal(make_test_signal("S1"))
    pos.pnl_points = -40.0
    assert e.day_pnl() <= -500
    assert e.risk_block_reason("demo")
    pos.pnl_points = 40.0  # recovers, but the cap stays on for the day
    assert e.risk_block_reason("demo")


def test_cap_disabled_with_zero(tmp_path):
    e = _engine(tmp_path, limit=0)
    _lose(e, "S1")
    assert e.risk_block_reason("demo") is None


def test_cap_resets_next_ist_day_and_survives_restart(tmp_path):
    e = _engine(tmp_path, limit=500)
    _lose(e, "S1")
    assert e.risk_block_reason("demo")
    e2 = PaperTradingEngine(db_path=str(tmp_path / "t.db"))  # restart, same day
    assert e2.risk_block_reason("demo")
    with market_hours.override_clock(NEXT_DAY):
        assert e2.risk_block_reason("demo") is None
        assert e2.day_pnl() == 0.0


def test_reset_clears_stored_trip_so_restart_does_not_resurrect_it(tmp_path):
    e = _engine(tmp_path, limit=500)
    _lose(e, "S1")
    assert e.risk_block_reason("demo")
    e.reset_sync()
    assert e.risk_block_reason("demo") is None
    e2 = PaperTradingEngine(db_path=str(tmp_path / "t.db"))  # restart, same day
    assert e2.risk_block_reason("demo") is None


def test_cap_is_per_book(tmp_path):
    e = _engine(tmp_path, limit=500)
    _lose(e, "S1")  # demo book
    assert e.risk_block_reason("demo")
    assert e.risk_block_reason("live") is None


def test_kill_switch_blocks_and_persists_until_released(tmp_path):
    e = _engine(tmp_path)
    events = []
    e.on_risk_event = lambda kind, d: events.append(kind)
    assert e.set_kill_switch(True) is True
    assert e.set_kill_switch(True) is False
    assert e.open_position_from_signal(make_test_signal("S1")) is None
    e2 = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    assert e2.risk_status(None).kill_switch_active
    with market_hours.override_clock(NEXT_DAY):  # no daily reset for the manual switch
        assert e2.risk_block_reason("demo") == "kill switch is engaged"
    e2.set_kill_switch(False)
    assert e2.open_position_from_signal(make_test_signal("S2")) is not None
    assert events == ["kill_switch_engaged"]


def test_portfolio_carries_risk_state(tmp_path):
    e = _engine(tmp_path)
    assert e.get_portfolio("demo").risk["daily_loss_limit"] == 1000.0
    assert e.get_portfolio_summary("live").risk["entries_blocked"] is False
    assert e.get_portfolio().risk is not None


def test_api_kill_switch_needs_confirm_and_squares_off():
    from app.main import app
    from app.services.paper_trader import paper_trader
    client = TestClient(app)
    paper_trader.set_kill_switch(False)
    pos = paper_trader.open_position_from_signal(make_test_signal("API_S1", symbol="BANKNIFTY"))
    try:
        assert client.post("/api/paper/kill-switch", json={}).status_code == 400
        assert client.post("/api/paper/kill-switch", json={"confirm": False}).status_code == 400
        assert client.post("/api/paper/kill-switch", headers={"X-Omit-Capability": "1"}, json={"confirm": True}).status_code == 401
        r = client.post("/api/paper/kill-switch", json={"confirm": True})
        assert r.status_code == 200 and r.json()["risk"]["kill_switch_active"]
        if pos:
            assert r.json()["closed"] >= 1
            assert not paper_trader.get_portfolio().active_positions
            assert paper_trader.get_portfolio().closed_trades[-1].exit_reason == "KILL_SWITCH"
        assert client.post("/api/paper/kill-switch/release", json={}).status_code == 400
        r = client.post("/api/paper/kill-switch/release", json={"confirm": True})
        assert r.json()["risk"]["kill_switch_active"] is False
    finally:
        paper_trader.set_kill_switch(False)


def test_api_settings_updates_limit():
    from app.main import app
    from app.services.paper_trader import paper_trader
    client = TestClient(app)
    old = paper_trader._daily_loss_limit
    try:
        r = client.post("/api/paper/settings", json={"daily_loss_limit": 12345})
        assert r.status_code == 200 and r.json()["risk"]["daily_loss_limit"] == 12345
        assert client.post("/api/paper/settings", json={"daily_loss_limit": -1}).status_code == 422
    finally:
        paper_trader.set_daily_loss_limit(old)
