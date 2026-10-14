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
