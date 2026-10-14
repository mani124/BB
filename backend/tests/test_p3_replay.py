"""P3 replay harness: stream a whole simulated day of repeated signals (the NESTLEIND/IRFC
incident shape) through the paper engine on a stepping exchange clock and diff the journal
against the invariants a hand-kept trade list would show."""
from datetime import timedelta

import pytest

from app.core.config import settings
from app.services import market_hours
from app.services.strategy_engine import SetupType, is_setup5
from tests.test_p0_session_guard import at, make_signal
from app.services.paper_trader import PaperTradingEngine


def _replay(engine, start, end, step_s=65, symbol="NESTLEIND", sec_id="77001"):
    t, n, entries = start, 0, []
    while t <= end:
        with market_hours.override_clock(t):
            pos = engine.open_position_from_signal(make_signal(f"{symbol}_S5_{n}", symbol=symbol, sec_id=sec_id),
                                                   lots=1, feed_mode="live")
            if pos is not None:
                entries.append(t)
            engine.square_off_if_due()
        t += timedelta(seconds=step_s)
        n += 1
    return entries


def test_full_day_replay_has_no_after_hours_entries_and_flat_at_close(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    engine = PaperTradingEngine(db_path=str(tmp_path / "r.db"))
    entries = _replay(engine, at(9, 0), at(18, 0))
    assert entries, "the in-session signal should have been taken at least once"
    assert all(at(9, 15) <= e < at(15, 15) for e in entries)       # nothing before open / after cutoff
    assert len(entries) <= settings.MAX_ENTRIES_PER_SYMBOL_PER_DAY  # no stacking on the same stock
    with market_hours.override_clock(at(18, 0)):
        engine.square_off_if_due()
    assert engine.get_portfolio().active_positions == []            # flat after square-off


def test_frozen_after_hours_session_opens_nothing(tmp_path):
    engine = PaperTradingEngine(db_path=str(tmp_path / "r2.db"))
    assert _replay(engine, at(15, 31), at(17, 59)) == []
    assert engine.get_portfolio().active_positions == []


def test_is_setup5_accepts_enum_value_and_legacy_labels():
    assert is_setup5(SetupType.SETUP_5_OPTION_BB)
    assert is_setup5("Setup 5: Option Chart BB Scalp")
    assert is_setup5("SETUP_5_OPTION_BB") and is_setup5("BB_EXPANSION_SCALP")
    assert not is_setup5(SetupType.SETUP_1_SQUEEZE)
