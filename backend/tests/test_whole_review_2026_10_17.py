"""Fixes from the 2026-10-17 whole-project review (notes/whole_project_review_2026-10-17.md)."""
import sqlite3
import warnings
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services import db, market_hours, notifier as notifier_mod, scanner_worker
from app.services.broker_definedge import MasterIndex
from app.services.paper_trader import PaperTradingEngine
from tests.test_paper_reentry_gate import make_test_signal

IST = market_hours.IST


# ---- H3: reset is refused while something real is open, and keeps today's loss cap
def test_reset_block_reason_counts_live_and_routed_positions(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    assert e.reset_block_reason() is None
    assert "routed" in e.reset_block_reason(routed_open=1)
    pos = e.open_position_from_signal(make_test_signal("R1"))
    assert e.reset_block_reason() is None  # a demo position does not block
    pos.feed_mode = "live"
    assert "live position" in e.reset_block_reason()


def test_reset_endpoint_refuses_with_an_open_live_position(monkeypatch):
    from app.main import app
    from app.services.paper_trader import paper_trader
    client = TestClient(app)
    fake = SimpleNamespace(feed_mode="live")
    monkeypatch.setattr(paper_trader._portfolio, "active_positions", [fake])
    res = client.post("/api/paper/reset")
    assert res.status_code == 409 and "live position" in res.json()["detail"]


def test_reset_keeps_processed_signal_ids(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    sig = make_test_signal("KEEP1")
    pos = e.open_position_from_signal(sig)
    e.close_position(pos.id, exit_price=pos.option_entry)
    e.reset_sync()
    assert e.open_position_from_signal(sig) is None  # an already-handled signal cannot open again
    e2 = PaperTradingEngine(db_path=str(tmp_path / "t.db"))  # also after a restart
    assert e2.open_position_from_signal(sig) is None


# ---- H1: live positions without a live feed are reported
def test_unmanaged_live_positions_alert(monkeypatch, tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("U1"))
    sent = []
    monkeypatch.setattr(scanner_worker, "paper_trader", e)
    monkeypatch.setattr(notifier_mod, "notify", lambda *a, **k: sent.append(a) or True)
    w = SimpleNamespace(_state=SimpleNamespace(active_mode="demo"))
    check = scanner_worker.ScannerWorker.check_unmanaged_live_positions
    assert check(w) == 0  # demo position only
    pos.feed_mode = "live"
    assert check(w) == 1 and sent and sent[0][0] == "live_positions_unmanaged"
    w._state.active_mode = "live"
    assert check(w) == 0
    w._state.active_mode = "demo"
    with market_hours.override_clock(datetime(2026, 10, 14, 16, 0, tzinfo=IST)):
        assert check(w) == 0  # market closed: nothing to manage until tomorrow


# ---- M4: a pending Target 2 that fills below the target is not a Target 2 trade
def test_late_target_2_fill_below_target_is_recorded_as_close(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("T2LATE"))
    pos.feed_mode = "live"
    pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
    below = round(pos.option_target_2 - 5, 2)
    e.update_market_prices({}, option_price_map={pos.id: below}, feed_mode="live")
    closed = e._portfolio.closed_trades[-1]
    assert closed.id == pos.id and closed.status == "CLOSED" and "Late Fill" in closed.exit_reason


def test_pending_target_2_at_or_above_target_stays_target_2(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("T2OK"))
    pos.feed_mode = "live"
    pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
    e.update_market_prices({}, option_price_map={pos.id: pos.option_target_2 + 1}, feed_mode="live")
    assert e._portfolio.closed_trades[-1].status == "TARGET_2"


# ---- L1: half-rupee strikes keep their own contract
def test_master_index_keeps_half_rupee_strikes_apart():
    rows = [
        "NFO,1,IDEA,IDEA27OCT2613.5CE,OPTSTK,27102026,5,1000,CE,1350,2,1,,1",
        "NFO,2,IDEA,IDEA27OCT2614CE,OPTSTK,27102026,5,1000,CE,1400,2,1,,1",
    ]
    m = MasterIndex()
    assert m.load_csv("\n".join(rows)) == 2
    assert m.find("NFO", "IDEA", date(2026, 10, 27), 13.5, "CE").trading_symbol == "IDEA27OCT2613.5CE"
    assert m.find("NFO", "IDEA", date(2026, 10, 27), 14, "CE").trading_symbol == "IDEA27OCT2614CE"


# ---- L3: a failed delivery does not suppress the retry
def test_failed_alert_delivery_does_not_block_the_next_one():
    class Broken:
        calls = 0

        def send(self, text):
            Broken.calls += 1
            raise RuntimeError("down")

    n = notifier_mod.Notifier(channels=[Broken()])
    assert n.notify("x", "one", min_interval=600)
    n._pool.shutdown(wait=True)
    n._pool = notifier_mod.ThreadPoolExecutor(max_workers=1)
    assert n.notify("x", "two", min_interval=600)  # not deduped: the first never arrived
    n._pool.shutdown(wait=True)
    assert Broken.calls == 2


# ---- L2: connections opened through db.connect close at the end of their `with` block
def test_db_connect_closes_at_the_end_of_with(tmp_path):
    with db.connect(str(tmp_path / "c.db")) as conn:
        conn.execute("CREATE TABLE t (x)")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        with db.connect(str(tmp_path / "c.db")) as c2:
            assert c2.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


# ---- a pending stop must not close a position whose price has recovered above the stop
def test_pending_stop_is_dropped_when_price_recovered(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("PSTOP"))
    pos.feed_mode = "live"
    pos.pending_spot_exit = "Stop-Loss Hit"
    recovered = round(pos.option_sl + 10, 2)
    spot = (pos.underlying_sl + 20) if pos.option_type == "CE" else (pos.underlying_sl - 20)
    e.update_market_prices({pos.symbol: spot}, option_price_map={pos.id: recovered}, feed_mode="live")
    assert pos in e._portfolio.active_positions and pos.pending_spot_exit is None


def test_pending_stop_still_closes_when_the_stop_is_still_breached(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("PSTOP2"))
    pos.feed_mode = "live"
    pos.pending_spot_exit = "Stop-Loss Hit"
    e.update_market_prices({}, option_price_map={pos.id: round(pos.option_sl - 2, 2)}, feed_mode="live")
    assert e._portfolio.closed_trades[-1].id == pos.id and e._portfolio.closed_trades[-1].status == "STOPPED_OUT"


# ---- a capped T315-F pool shows up in the risk status without claiming every entry is blocked
def test_risk_status_reports_a_capped_pool(tmp_path):
    from app.services.setup_t315f import VERSIONS
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    e.set_daily_loss_limit(1000)
    sig = make_test_signal("POOL22")
    sig.setup_type = VERSIONS[22].setup_type
    pos = e.open_position_from_signal(sig, feed_mode="live") if False else None
    e.day_pnl = lambda book=None, pool="main": -5000.0 if pool == "f22" else 0.0
    st = e.risk_status("live")
    assert st.capped_pools == ["Setup 22"] and not st.loss_cap_tripped and not st.entries_blocked


# ---- 2026-10-20 review: index-governed setups (20-23) exit on the index, not the option premium
def _t315f_position(tmp_path, number=22):
    from app.services.setup_t315f import VERSIONS
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    sig = make_test_signal("SG")
    sig.setup_type = VERSIONS[number].setup_type
    pos = e.open_position_from_signal(sig, lots=2)
    return e, pos


def test_index_governed_position_ignores_option_premium_when_spot_is_known(tmp_path):
    e, pos = _t315f_position(tmp_path)
    spot = (pos.underlying_sl + 15) if pos.option_type == "CE" else (pos.underlying_sl - 15)   # still on the safe side
    e.update_market_prices({pos.symbol: spot}, option_price_map={pos.id: round(pos.option_sl - 3, 2)})
    assert pos in e._portfolio.active_positions and pos.status == "OPEN"
    # spot through the stop does exit it
    breach = (pos.underlying_sl - 1) if pos.option_type == "CE" else (pos.underlying_sl + 1)
    e.update_market_prices({pos.symbol: breach}, option_price_map={pos.id: round(pos.option_sl - 3, 2)})
    assert e._portfolio.closed_trades[-1].id == pos.id and e._portfolio.closed_trades[-1].status == "STOPPED_OUT"


def test_other_setups_still_stop_on_option_premium(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("PREM"))
    spot = (pos.underlying_sl + 15) if pos.option_type == "CE" else (pos.underlying_sl - 15)
    e.update_market_prices({pos.symbol: spot}, option_price_map={pos.id: round(pos.option_sl - 3, 2)})
    assert e._portfolio.closed_trades[-1].id == pos.id


# ---- 2026-10-20 review: an unquoted / bid-only cycle must not keep a recovered pending stop alive
def test_pending_stop_clears_on_a_bid_only_update_above_the_stop(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("BIDONLY"))
    pos.feed_mode = "live"
    pos.pending_spot_exit = "Stop-Loss Hit"
    pos.current_option_price = round(pos.option_sl - 5, 2)       # stale, below the stop
    spot = (pos.underlying_sl + 20) if pos.option_type == "CE" else (pos.underlying_sl - 20)
    e.update_market_prices({pos.symbol: spot}, option_bid_map={pos.id: round(pos.option_sl + 8, 2)}, feed_mode="live")
    assert pos in e._portfolio.active_positions and pos.pending_spot_exit is None


def test_zero_option_price_is_not_a_stop_breach():
    from app.services.paper_exits import _level_hit
    pos = SimpleNamespace(option_type="CE", current_option_price=0.0, option_sl=80.0, underlying_sl=100.0, setup_type="Setup 1")
    assert _level_hit(pos, 120.0, "sl") is False
    assert _level_hit(pos, 120.0, "sl", fresh_opt=70.0) is True


# ---- 2026-10-20 whole-codebase review
def test_unquoted_option_price_does_not_stop_out_a_new_position(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("ZERO"))
    pos.current_option_price = 0.0
    spot = (pos.underlying_sl + 15) if pos.option_type == "CE" else (pos.underlying_sl - 15)
    e.update_market_prices({pos.symbol: spot})
    assert pos in e._portfolio.active_positions


def test_stale_carryover_notifies_the_order_router(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("STALE"))
    pos.entry_datetime = "2026-10-01T10:00:00+05:30"
    seen = []
    e.on_position_update = seen.append
    assert [p.id for p in e.flag_stale_carryover()] == [pos.id]
    assert [p.id for p in seen] == [pos.id]


def test_manual_live_close_with_ltp_and_bid_books_no_artificial_slippage(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("LTPBID"))
    pos.feed_mode = "live"
    closed = e.close_position(pos.id, real_opt_price=150.0, real_bid_price=145.0)
    assert closed.theoretical_exit == 145.0


def test_single_lot_stop_after_target_1_locks_a_fee_buffer(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("ONELOT"), lots=1)
    entry = pos.option_entry
    t1_spot = pos.underlying_target_1
    e.update_market_prices({pos.symbol: t1_spot + (1 if pos.option_type == "CE" else -1)}, option_price_map={pos.id: pos.option_target_1 + 1})
    assert pos.status == "TARGET_1" and pos.lots == 1
    assert pos.option_sl > entry and pos.option_sl < pos.option_target_1


def test_two_lot_stop_after_target_1_is_plain_breakeven(tmp_path):
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    pos = e.open_position_from_signal(make_test_signal("TWOLOT"), lots=2)
    entry = pos.option_entry
    e.update_market_prices({pos.symbol: pos.underlying_target_1 + (1 if pos.option_type == "CE" else -1)}, option_price_map={pos.id: pos.option_target_1 + 1})
    assert pos.status == "TARGET_1" and pos.option_sl == entry


def test_weekday_fallback_is_opt_in(monkeypatch):
    from datetime import date
    from app.core.config import settings
    monkeypatch.setattr(settings, "ASSUME_WEEKDAYS_WITHOUT_HOLIDAY_LIST", True)
    assert market_hours.is_trading_day(date(2099, 1, 5)) and not market_hours.is_trading_day(date(2099, 1, 3))
    monkeypatch.setattr(settings, "ASSUME_WEEKDAYS_WITHOUT_HOLIDAY_LIST", False)
    assert not market_hours.is_trading_day(date(2099, 1, 5))
