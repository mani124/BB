"""Regression tests for the Codex review findings (stop persistence, entry rollback, lots validation, notional cap)."""
import pytest
from pydantic import ValidationError

from app.api.paper import ManualTradeRequest
from app.core.config import settings
from app.services.paper_storage import PaperStorage
from app.services.paper_trader import PaperTradingEngine
from tests.test_p0_session_guard import make_signal


@pytest.fixture(autouse=True)
def _no_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)


def test_breakeven_stops_persist_across_restart(tmp_path):
    db = str(tmp_path / "be.db")
    eng = PaperTradingEngine(db_path=db)
    pos = eng.open_position_from_signal(make_signal("BE_1"), feed_mode="demo")
    pos.status = "TARGET_1"
    pos.underlying_sl = pos.underlying_entry
    pos.option_sl = pos.option_entry
    eng.storage.upsert_position(pos)

    active, closed = PaperStorage(db).load_all_positions()
    loaded = active + closed
    row = next(p for p in loaded if p.id == pos.id)
    assert row.option_sl == pos.option_entry
    assert row.underlying_sl == pos.underlying_entry


def test_failed_entry_persistence_is_not_reported_as_a_trade(tmp_path, monkeypatch):
    eng = PaperTradingEngine(db_path=str(tmp_path / "f.db"))

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(eng.storage, "record_entry", boom)
    assert eng.open_position_from_signal(make_signal("F_1"), feed_mode="demo") is None
    assert eng.get_portfolio().active_positions == []


def test_manual_lots_must_be_positive():
    sig = make_signal("L_1")
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            ManualTradeRequest(signal=sig, lots=bad)
    assert ManualTradeRequest(signal=sig, lots=3).lots == 3


def test_notional_cap_uses_requested_lots(monkeypatch):
    eng = PaperTradingEngine()
    sig = make_signal("N_1")
    rec = sig.strike_recommendation
    per_lot = rec.estimated_option_entry * rec.lot_size
    monkeypatch.setattr(settings, "MAX_OPEN_NOTIONAL", per_lot * 2)
    assert eng._exposure_block_reason(sig, lots=1) is None
    assert eng._exposure_block_reason(sig, lots=10) is not None


# ---------------------------------------------------------------- second review round

def test_stale_quote_age_is_rechecked_at_entry(monkeypatch):
    import time as _t
    sig = make_signal("Q_1")
    rec = sig.strike_recommendation
    rec.quote_age_s = 1.0
    rec.quote_as_of = _t.time() - 120  # signal built long ago, scan since stalled
    assert PaperTradingEngine._quote_block_reason(rec) is not None
    rec.quote_as_of = _t.time() - 2
    assert PaperTradingEngine._quote_block_reason(rec) is None


def test_failed_save_releases_signal_id_for_retry(tmp_path, monkeypatch):
    eng = PaperTradingEngine(db_path=str(tmp_path / "r.db"))
    real = eng.storage.record_entry
    monkeypatch.setattr(eng.storage, "record_entry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    sig = make_signal("R_1")
    assert eng.open_position_from_signal(sig, feed_mode="demo") is None
    monkeypatch.setattr(eng.storage, "record_entry", real)
    assert eng.open_position_from_signal(sig, feed_mode="demo") is not None


def test_risk_cap_sizes_from_actual_fill_price():
    eng = PaperTradingEngine()
    eng._portfolio.max_risk_per_trade = 100000.0
    sig = make_signal("S_1")
    rec = sig.strike_recommendation
    rec.real_ask_price = rec.estimated_option_entry * 3  # fill far above the signal price
    rec.real_bid_price = rec.real_ask_price
    risk_per_lot = (rec.real_ask_price - rec.option_sl_price) * rec.lot_size
    eng._portfolio.max_risk_per_trade = risk_per_lot * 1.5  # only 1 lot fits at the real fill
    pos = eng.open_position_from_signal(sig, lots=5, feed_mode="demo")
    assert pos is not None and pos.lots == 1


def test_daily_pnl_includes_booked_partial_on_open_runner():
    eng = PaperTradingEngine()
    pos = eng.open_position_from_signal(make_signal("D_1"), lots=2, feed_mode="demo")
    pos.booked_pnl_rupees = 500.0
    assert eng.get_daily_pnl("demo")[0].gross_pnl == 500.0


def test_win_rate_uses_net_pnl():
    eng = PaperTradingEngine()
    pos = eng.open_position_from_signal(make_signal("W_1"), feed_mode="demo")
    eng._portfolio.active_positions.remove(pos)
    pos.status, pos.pnl_rupees, pos.net_pnl, pos.total_charges = "STOPPED_OUT", 10.0, -35.0, 45.0
    eng._portfolio.closed_trades.append(pos)
    assert eng.get_portfolio("demo").winning_trades_count == 0
