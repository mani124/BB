"""P1 fixes: IST clock everywhere, quote freshness/spread guard, atomic entry persistence,
signed exit slippage and gap labelling, live/demo views, exposure caps and daily P&L."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import market_hours
from app.services.market_hours import IST
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.paper_storage import PaperStorage
from app.services.paper_trader import PaperTradingEngine
from tests.test_p0_session_guard import _breakout_df, at, make_signal


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    return PaperTradingEngine(db_path=str(tmp_path / "t.db"))


@pytest.fixture
def mem_engine(monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    return PaperTradingEngine()


# ------------------------------------------------------------------ P1-2: IST clock

def test_no_host_clock_reads_outside_market_hours_module():
    """All 'now' reads must go through market_hours so a UTC host cannot skew sessions."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name == "market_hours.py":
            continue
        text = path.read_text()
        if re.search(r"datetime\.(now|utcnow|today)\(", text):
            offenders.append(path.name)
    assert offenders == []


def test_position_timestamps_follow_the_ist_clock_not_the_host(mem_engine):
    with market_hours.override_clock(at(10, 30, 15)):
        pos = mem_engine.open_position_from_signal(make_signal("S1"), feed_mode="demo")
    assert pos.entry_time == "10:30:15"
    assert pos.entry_datetime == "2026-10-14T10:30:15+05:30"


# ------------------------------------------------------------------ P1-3: quote guard

def _live_signal(sig_id, **rec_overrides):
    sig = make_signal(sig_id)
    for k, v in rec_overrides.items():
        setattr(sig.strike_recommendation, k, v)
    return sig


def test_live_entry_rejected_when_quote_is_stale(mem_engine):
    stale = _live_signal("Q1", quote_age_s=settings.MAX_QUOTE_AGE_SECONDS + 5)
    assert mem_engine.open_position_from_signal(stale, feed_mode="live") is None
    assert mem_engine.get_portfolio().active_positions == []


def test_live_entry_accepts_fresh_quote(mem_engine):
    fresh = _live_signal("Q2", quote_age_s=4.0, real_bid_price=43.0)
    assert mem_engine.open_position_from_signal(fresh, feed_mode="live") is not None


def test_live_entry_rejected_on_wide_or_crossed_market(mem_engine):
    wide = _live_signal("Q3", quote_age_s=1.0, real_bid_price=20.0)       # (43.6-20)/43.6 = 54%
    crossed = _live_signal("Q4", quote_age_s=1.0, real_bid_price=50.0)
    assert mem_engine.open_position_from_signal(wide, feed_mode="live") is None
    assert mem_engine.open_position_from_signal(crossed, feed_mode="live") is None


def test_unknown_quote_age_does_not_block(mem_engine):
    """Manual / legacy paths without a quote age keep working (age None = unknown)."""
    assert mem_engine.open_position_from_signal(_live_signal("Q5"), feed_mode="live") is not None


def test_setup5_carries_quote_age_and_contract_scoped_id():
    df = _breakout_df(True)
    kwargs = dict(
        symbol="NESTLEIND", strike_symbol="NESTLEIND 1330 CE", option_type="CE", option_df=df,
        underlying_price=1330.0, strike_price=1330.0,
    )
    with market_hours.override_clock(at(11, 0)):
        a = evaluate_option_chart_signal(**kwargs, option_security_id="111",
                                         current_quote={"last_price": 45.0, "ask_price": 45.5,
                                                        "quote_age_s": 7.5, "is_live_quote": True})
        b = evaluate_option_chart_signal(**kwargs, option_security_id="111",
                                         current_quote={"last_price": 45.0, "quote_age_s": 9.0})
        c = evaluate_option_chart_signal(**kwargs, option_security_id="222",
                                         current_quote={"last_price": 45.0})
    assert a is not None and b is not None and c is not None
    assert a.strike_recommendation.quote_age_s == 7.5
    assert a.id == b.id                      # same bar + same contract -> same id
    assert a.id != c.id                      # different contract -> different id
    assert "_111_" in a.id


# ------------------------------------------------------------------ P1-4: atomic persistence

def test_entry_and_processed_signal_are_persisted_together(tmp_path, monkeypatch):
    """Simulates a hard kill right after entry: no queue flush ever happens, yet the
    reloaded engine has both the position and the processed-signal marker."""
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    db = str(tmp_path / "crash.db")
    first = PaperTradingEngine(db_path=db)
    pos = first.open_position_from_signal(make_signal("CRASH_1"), feed_mode="demo")
    assert pos is not None
    # (no flush / no stop_persistence_worker: process 'dies' here)

    second = PaperTradingEngine(db_path=db)
    assert "CRASH_1" in second._processed_signal_ids
    assert [p.id for p in second.get_portfolio().active_positions] == [pos.id]
    # The same signal must not open another position after the restart
    assert second.open_position_from_signal(make_signal("CRASH_1"), feed_mode="demo") is None


def test_record_entry_is_a_single_transaction(tmp_path):
    storage = PaperStorage(str(tmp_path / "tx.db"))
    eng = PaperTradingEngine()
    pos = eng.open_position_from_signal(make_signal("TX_1"), feed_mode="demo")
    storage.record_entry(pos, "TX_1", "2026-10-14 11:00:00")
    storage.record_entry(pos, "TX_1", "2026-10-14 11:00:00")      # idempotent
    with sqlite3.connect(str(tmp_path / "tx.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM processed_signals").fetchone()[0] == 1


def test_positions_load_in_chronological_order_across_days(tmp_path):
    db = str(tmp_path / "order.db")
    storage = PaperStorage(db)
    eng = PaperTradingEngine()
    with market_hours.override_clock(at(21, 1, day=13)):
        late_yesterday = eng.open_position_from_signal(make_signal("D1", symbol="AAA", sec_id="1"), feed_mode="demo")
    with market_hours.override_clock(at(9, 20, day=14)):
        early_today = eng.open_position_from_signal(make_signal("D2", symbol="BBB", sec_id="2"), feed_mode="demo")
    storage.batch_upsert_positions([early_today, late_yesterday])
    active, _ = storage.load_all_positions()
    assert [p.symbol for p in active] == ["AAA", "BBB"]     # text order of HH:MM:SS would flip these


# ------------------------------------------------------------------ P1-5: signed slippage, gaps

def _closed_with_fill(engine, target, bid, status_reason="Target 2 (1:2.5) Hit"):
    pos = engine.open_position_from_signal(make_signal("G1", entry=43.6), feed_mode="demo")
    engine._finalize_closed_position(
        pos, theoretical_exit=target, status="TARGET_2", reason=status_reason,
        exit_time="09:56:31", real_bid_price=bid,
    )
    return pos


def test_improved_fill_gives_negative_slippage(mem_engine):
    pos = _closed_with_fill(mem_engine, target=48.6, bid=49.1)
    assert pos.exit_slippage == -0.5
    assert pos.exit_reason == "Target 2 (1:2.5) Hit"        # small improvement: not a gap


def test_worse_fill_gives_positive_slippage(mem_engine):
    pos = _closed_with_fill(mem_engine, target=48.6, bid=48.0)
    assert pos.exit_slippage == 0.6


def test_gap_through_target_is_labelled_and_costs_negative(mem_engine):
    pos = _closed_with_fill(mem_engine, target=48.6, bid=59.3)      # +22% gap fill
    assert "Gap Exit" in pos.exit_reason and "59.30" in pos.exit_reason
    assert pos.exit_slippage == pytest.approx(-10.7)
    assert pos.total_slippage_cost < 0
    assert pos.current_option_price == 59.3                          # P&L uses the real fill


def test_gap_label_is_not_duplicated(mem_engine):
    pos = _closed_with_fill(mem_engine, target=48.6, bid=59.3)
    first = pos.exit_reason
    mem_engine._finalize_closed_position(pos, 48.6, "TARGET_2", first, "09:56:31", real_bid_price=59.3)
    assert pos.exit_reason.count("Gap Exit") == 1


# ------------------------------------------------------------------ P1-6: live / demo views

def test_closed_stale_error_modes_still_show_the_live_book(mem_engine):
    live = mem_engine.open_position_from_signal(make_signal("L1", symbol="LIVEONE", sec_id="10"), feed_mode="live")
    for mode in ("live", "stale", "error", "closed"):
        view = mem_engine.get_portfolio(mode=mode)
        assert [p.id for p in view.active_positions] == [live.id], mode


def test_demo_rows_do_not_leak_into_live_totals(mem_engine):
    live = mem_engine.open_position_from_signal(make_signal("L2", symbol="LIVETWO", sec_id="11"), feed_mode="live")
    demo = mem_engine.open_position_from_signal(make_signal("D3", symbol="DEMOTWO", sec_id="12"), feed_mode="demo")
    mem_engine.close_position(demo.id, reason="MANUAL_EXIT", exit_price=60.0)
    live_view = mem_engine.get_portfolio(mode="closed")
    assert live_view.total_trades_count == 0
    assert [p.id for p in live_view.active_positions] == [live.id]
    demo_view = mem_engine.get_portfolio(mode="demo")
    assert demo_view.total_trades_count == 1 and demo_view.active_positions == []


def test_modelled_entry_price_is_flagged_estimated(mem_engine):
    sig = make_signal("E1")
    sig.strike_recommendation.real_ask_price = None
    sig.strike_recommendation.real_ltp = None
    pos = mem_engine.open_position_from_signal(sig, feed_mode="demo")
    assert pos.entry_estimated is True
    real = mem_engine.open_position_from_signal(make_signal("E2", symbol="OTHER", sec_id="9"), feed_mode="demo")
    assert real.entry_estimated is False


def test_entry_estimated_survives_persistence(tmp_path):
    db = str(tmp_path / "est.db")
    eng = PaperTradingEngine(db_path=db)
    sig = make_signal("E3")
    sig.strike_recommendation.real_ask_price = None
    eng.open_position_from_signal(sig, feed_mode="demo")
    again = PaperTradingEngine(db_path=db)
    assert again.get_portfolio().active_positions[0].entry_estimated is True


def test_portfolio_api_defaults_to_the_current_book(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.paper_trader import paper_trader

    client = TestClient(app)
    client.post("/api/paper/reset")
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    demo = paper_trader.open_position_from_signal(make_signal("API_D", symbol="APID", sec_id="21"), feed_mode="demo")
    live = paper_trader.open_position_from_signal(make_signal("API_L", symbol="APIL", sec_id="22"), feed_mode="live")
    assert demo and live
    everything = client.get("/api/paper/portfolio?mode=all").json()
    assert len(everything["active_positions"]) == 2
    only_live = client.get("/api/paper/portfolio?mode=live").json()
    assert [p["symbol"] for p in only_live["active_positions"]] == ["APIL"]
    only_demo = client.get("/api/paper/portfolio?mode=demo").json()
    assert [p["symbol"] for p in only_demo["active_positions"]] == ["APID"]
    client.post("/api/paper/reset")


# ------------------------------------------------------------------ P1-7: caps and daily P&L

def test_max_open_positions_cap(mem_engine, monkeypatch):
    monkeypatch.setattr(settings, "MAX_OPEN_POSITIONS", 2)
    a = mem_engine.open_position_from_signal(make_signal("C1", symbol="AAA", sec_id="1"), feed_mode="demo")
    b = mem_engine.open_position_from_signal(make_signal("C2", symbol="BBB", sec_id="2"), feed_mode="demo")
    c = mem_engine.open_position_from_signal(make_signal("C3", symbol="CCC", sec_id="3"), feed_mode="demo")
    assert a and b and c is None


def test_max_entries_per_symbol_per_day_counts_closed_trades_too(mem_engine, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ENTRIES_PER_SYMBOL_PER_DAY", 2)
    for i in range(2):
        p = mem_engine.open_position_from_signal(make_signal(f"N{i}", symbol="NESTLEIND", sec_id=str(100 + i)), feed_mode="demo")
        assert p is not None
        mem_engine.close_position(p.id, reason="MANUAL_EXIT", exit_price=44.0)
    third = mem_engine.open_position_from_signal(make_signal("N2", symbol="NESTLEIND", sec_id="102"), feed_mode="demo")
    assert third is None
    # a different stock is unaffected
    assert mem_engine.open_position_from_signal(make_signal("N3", symbol="MARUTI", sec_id="500"), feed_mode="demo")


def test_per_symbol_daily_cap_resets_on_a_new_day(mem_engine, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ENTRIES_PER_SYMBOL_PER_DAY", 1)
    with market_hours.override_clock(at(10, 0, day=13)):
        p = mem_engine.open_position_from_signal(make_signal("Y1", symbol="NESTLEIND", sec_id="7"), feed_mode="demo")
        mem_engine.close_position(p.id, reason="MANUAL_EXIT", exit_price=44.0)
    with market_hours.override_clock(at(10, 0, day=14)):
        assert mem_engine.open_position_from_signal(make_signal("Y2", symbol="NESTLEIND", sec_id="7"), feed_mode="demo")


def test_open_notional_cap(mem_engine, monkeypatch):
    # one default-lots entry of entry 43.6 * lot 100 * 2 lots = 8,720
    monkeypatch.setattr(settings, "MAX_OPEN_NOTIONAL", 10_000)
    a = mem_engine.open_position_from_signal(make_signal("M1", symbol="AAA", sec_id="1"), feed_mode="demo")
    b = mem_engine.open_position_from_signal(make_signal("M2", symbol="BBB", sec_id="2"), feed_mode="demo")
    assert a is not None and b is None


def test_zero_disables_each_cap(mem_engine, monkeypatch):
    for name in ("MAX_OPEN_POSITIONS", "MAX_ENTRIES_PER_SYMBOL_PER_DAY", "MAX_OPEN_NOTIONAL"):
        monkeypatch.setattr(settings, name, 0)
    for i in range(10):
        assert mem_engine.open_position_from_signal(
            make_signal(f"Z{i}", symbol=f"S{i}", sec_id=str(i)), feed_mode="demo")


def test_daily_pnl_groups_by_exit_date_and_excludes_quarantine(mem_engine):
    with market_hours.override_clock(at(10, 0, day=13)):
        a = mem_engine.open_position_from_signal(make_signal("P1", symbol="AAA", sec_id="1"), feed_mode="demo")
        mem_engine.close_position(a.id, reason="MANUAL_EXIT", exit_price=50.0)        # win
    with market_hours.override_clock(at(10, 0, day=14)):
        b = mem_engine.open_position_from_signal(make_signal("P2", symbol="BBB", sec_id="2"), feed_mode="demo")
        mem_engine.close_position(b.id, reason="MANUAL_EXIT", exit_price=40.0)        # loss
        c = mem_engine.open_position_from_signal(make_signal("P3", symbol="CCC", sec_id="3"), feed_mode="demo")
        mem_engine.close_position(c.id, reason="MANUAL_EXIT", exit_price=60.0)
        c.quarantine_reason = "STACKED_DUPLICATE"

    days = mem_engine.get_daily_pnl("demo")
    assert [d.date for d in days] == ["2026-10-14", "2026-10-13"]            # newest first
    today, yesterday = days
    assert (today.trades, today.wins, today.losses, today.quarantined_excluded) == (1, 0, 1, 1)
    assert (yesterday.trades, yesterday.wins) == (1, 1)
    assert yesterday.net_pnl == pytest.approx(yesterday.gross_pnl - yesterday.total_charges)
    assert today.gross_pnl < 0 < yesterday.gross_pnl


def test_daily_pnl_api(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.paper_trader import paper_trader

    client = TestClient(app)
    client.post("/api/paper/reset")
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    p = paper_trader.open_position_from_signal(make_signal("API_P", symbol="APIP", sec_id="31"), feed_mode="demo")
    paper_trader.close_position(p.id, reason="MANUAL_EXIT", exit_price=50.0)
    rows = client.get("/api/paper/daily?mode=demo").json()
    assert rows and rows[0]["date"] == "2026-10-14" and rows[0]["trades"] == 1
    client.post("/api/paper/reset")
