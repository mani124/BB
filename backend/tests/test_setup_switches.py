"""Per-setup switches and the entry liquidity snapshot (2026-10-15 trade review)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import setup_switches
from app.services.paper_trader import PaperTradingEngine, paper_trader
from app.services.strategy_engine import SetupType
from tests.test_p0_session_guard import make_signal


@pytest.fixture(autouse=True)
def _no_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)


def test_defaults_limit_setups_1_and_2_to_indices():
    d = setup_switches.DEFAULT_MODES
    assert d["1"] == "index" and d["2"] == "index" and "5" not in d


def test_block_reason_modes():
    s1 = SetupType.SETUP_1_SQUEEZE
    assert setup_switches.block_reason({"1": "index"}, s1, "HDFCBANK")
    assert setup_switches.block_reason({"1": "index"}, s1, "NIFTY BANK") is None
    assert setup_switches.block_reason({"1": "stocks"}, s1, "SENSEX")
    assert setup_switches.block_reason({"1": "stocks"}, s1, "HDFCBANK") is None
    assert setup_switches.block_reason({"1": "off"}, s1, "NIFTY 50")
    assert setup_switches.block_reason({"1": "all"}, s1, "HDFCBANK") is None


def test_normalize_drops_unknown_entries():
    out = setup_switches.normalize_modes({"1": "bogus", "42": "off", "3": "off"})
    assert out["1"] == "index" and out["3"] == "off" and "42" not in out


def test_auto_entry_respects_switch_but_manual_does_not(tmp_path):
    eng = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    eng._portfolio.setup_modes = setup_switches.normalize_modes(None)
    stock_s1 = make_signal("SW_1", symbol="IRFC", setup=SetupType.SETUP_1_SQUEEZE)
    eng.on_signals_cycle([stock_s1], feed_mode="demo")
    assert eng.get_portfolio().active_positions == []
    # switching it to "all" does not resurrect the already-skipped signal id
    eng.set_setup_modes({"1": "all"})
    eng.on_signals_cycle([stock_s1], feed_mode="demo")
    assert eng.get_portfolio().active_positions == []
    s1b = make_signal("SW_2", symbol="IRFC", sec_id="55002", setup=SetupType.SETUP_1_SQUEEZE)
    eng.on_signals_cycle([s1b], feed_mode="demo")
    assert len(eng.get_portfolio().active_positions) == 1
    # a manual trade ignores the switch
    eng.set_setup_modes({"1": "off"})
    manual = make_signal("SW_3", symbol="SBIN", sec_id="55003", setup=SetupType.SETUP_1_SQUEEZE)
    assert eng.open_position_from_signal(manual, feed_mode="demo") is not None


def test_modes_persist_and_survive_reset(tmp_path):
    db = str(tmp_path / "t.db")
    eng = PaperTradingEngine(db_path=db)
    eng.set_setup_modes({"6": "off", "2": "all"})
    eng.reset_sync()
    assert eng.get_portfolio().setup_modes["6"] == "off"
    eng2 = PaperTradingEngine(db_path=db)
    eng2.storage.save_setting("setup_modes", '{"6": "stocks"}')
    eng3 = PaperTradingEngine(db_path=db)
    assert eng3.get_portfolio().setup_modes["6"] == "stocks"
    assert eng3.get_portfolio().setup_modes["1"] == "index"


def test_entry_logs_liquidity_snapshot(tmp_path):
    eng = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    sig = make_signal("LQ_1", symbol="IRFC", entry=40.0)
    rec = sig.strike_recommendation
    rec.real_ask_price, rec.real_bid_price = 40.0, 39.0
    rec.real_volume, rec.real_oi, rec.real_bid_qty, rec.real_ask_qty = 12000, 90000, 500, 700
    pos = eng.open_position_from_signal(sig, feed_mode="demo")
    assert pos.entry_bid == 39.0 and pos.entry_spread_pct == 2.5
    assert (pos.option_volume, pos.option_oi, pos.bid_qty, pos.ask_qty) == (12000, 90000, 500, 700)
    eng2 = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    loaded = eng2.get_portfolio().active_positions[0]
    assert loaded.entry_spread_pct == 2.5 and loaded.option_oi == 90000


def test_entry_without_bid_leaves_liquidity_empty(tmp_path):
    eng = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = eng.open_position_from_signal(make_signal("LQ_2", symbol="IRFC"), feed_mode="demo")
    assert pos.entry_bid is None and pos.entry_spread_pct is None and pos.option_volume is None


def test_settings_endpoint_updates_and_validates_modes():
    client = TestClient(app)
    before = dict(paper_trader.get_portfolio().setup_modes)
    try:
        r = client.post("/api/paper/settings", json={"setup_modes": {"6": "stocks"}})
        assert r.status_code == 200 and r.json()["setup_modes"]["6"] == "stocks"
        bad = client.post("/api/paper/settings", json={"setup_modes": {"6": "sometimes"}})
        assert bad.status_code == 422
        bad2 = client.post("/api/paper/settings", json={"setup_modes": {"99": "off"}})
        assert bad2.status_code == 422
    finally:
        paper_trader.set_setup_modes(before)
