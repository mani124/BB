"""P0 fixes: exchange-session guard, exposure guards, per-bar option volume,
completed-bar Setup 5, EOD square-off / stale carry-over, and row quarantine."""
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.core.config import settings
from app.services import market_hours
from app.services.market_hours import IST
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.indicators import calculate_indicators
from app.services.paper_storage import PaperStorage
from app.services.paper_trader import (
    EOD_SQUARE_OFF, STALE_CARRYOVER, PaperPosition, PaperTradingEngine,
)
from app.services.quarantine import (
    OFF_SESSION_ENTRY, STACKED_DUPLICATE, apply_quarantine, find_suspect_rows,
)
from app.services.scanner_worker import ScannerWorker
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation
from app.services.universe_manager import UniverseManager
from tests.test_option_chart_strategy import create_option_candles


def at(h, m, s=0, day=14):
    """IST datetime in Oct 2026 (the 14th, a Wednesday, unless another day is given)."""
    return datetime(2026, 10, day, h, m, s, tzinfo=IST)


def make_signal(sig_id, symbol="IRFC", side="CE", sec_id="55001", entry=43.6,
                setup=SetupType.SETUP_5_OPTION_BB):
    rec = OptionStrikeRecommendation(
        symbol=symbol, underlying_price=100.0, option_type=side,
        atm_strike=100, recommended_strike=100, strike_symbol=f"{symbol} 100 {side}",
        lot_size=100, risk=2.0, stop_loss=98.0, target_1=103.0, target_2=105.0,
        estimated_option_entry=entry, option_sl_pts=2.0, option_target_1_pts=3.0,
        option_target_2_pts=5.0, option_sl_price=entry - 2.0,
        option_target_1_price=entry + 3.0, option_target_2_price=entry + 5.0,
        option_security_id=sec_id, is_live_quote=True, real_ask_price=entry,
    )
    return Signal(
        id=sig_id, symbol=symbol, timeframe="5m", setup_type=setup, option_type=side,
        timestamp="2026-10-14 11:00:00", entry_price=entry, stop_loss=entry - 2.0,
        target_1=entry + 3.0, target_2=entry + 5.0, strike_recommendation=rec,
        is_confirmed=True, indicators_snapshot={}, rationale="test",
    )


@pytest.fixture
def engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "t.db"))


# ---------------------------------------------------------------- market hours (P0-1)

def test_session_boundaries_and_calendar():
    mh = market_hours
    assert not mh.is_market_open(at(9, 14, 59))
    assert mh.is_market_open(at(9, 15))
    assert mh.is_market_open(at(15, 29, 59))
    assert not mh.is_market_open(at(15, 30))
    assert mh.is_entry_allowed(at(15, 14, 59))
    assert not mh.is_entry_allowed(at(15, 15))
    assert not mh.is_market_open(at(11, 0, day=17))          # Saturday
    assert not mh.is_market_open(at(11, 0, day=20))          # Dussehra (in NSE_HOLIDAYS)
    assert not mh.is_square_off_due(at(15, 19, 59))
    assert mh.is_square_off_due(at(15, 20))
    assert mh.is_square_off_due(at(11, 0, day=17))           # nothing may be carried on a closed day
    # naive datetimes are read as IST; aware ones are converted to IST
    assert mh.is_market_open(datetime(2026, 10, 14, 11, 0))
    assert mh.is_market_open(at(11, 0).astimezone(timezone.utc))
    assert not mh.is_market_open(at(11, 0).astimezone(timezone.utc).replace(tzinfo=IST))


def test_clock_is_injectable_and_restorable():
    with market_hours.override_clock(at(22, 0)):
        assert market_hours.now_ist().hour == 22
        assert not market_hours.is_market_open()
    assert market_hours.now_ist().hour == 11     # conftest pin restored


def _fake_marketfeed():
    return {
        "NSE_EQ": {"1333": {"last_price": 22500.0, "ohlc": {"open": 22400.0, "high": 22550.0, "low": 22350.0, "close": 22500.0}}},
        "IDX_I": {"13": {"last_price": 22500.0, "ohlc": {"open": 22400.0, "high": 22550.0, "low": 22350.0, "close": 22500.0}}},
    }


def _frozen_chain(volume):
    return {"22500.000000": {
        "ce": {"strike_price": 22500.0, "security_id": 44612, "last_price": 43.6,
               "best_ask_price": 43.65, "best_bid_price": 43.55, "volume": volume},
        "pe": {"strike_price": 22500.0, "security_id": 44613, "last_price": 43.6,
               "best_ask_price": 43.65, "best_bid_price": 43.55, "volume": volume},
    }}


@pytest.mark.asyncio
async def test_after_hours_frozen_setup5_replay_gives_no_signals_or_positions():
    """Frozen evening scenario: 12 evening slots, option price frozen at 43.6, cumulative
    day volume sitting at a large constant. Must yield zero signals / positions / bars."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker.set_session_credentials("10001", "tok")
    worker.dhan_client.fetch_marketfeed_quotes = AsyncMock(return_value=_fake_marketfeed())
    worker.dhan_client.fetch_expiry_list = AsyncMock(return_value=["2026-10-15"])
    worker.dhan_client.fetch_option_chain = AsyncMock(return_value=_frozen_chain(2_500_000))
    frozen = pd.DataFrame([{
        "timestamp": datetime(2026, 10, 14, 15, 30) - timedelta(minutes=5 * (40 - i)),
        "open": 43.6, "high": 43.6, "low": 43.6, "close": 43.6, "volume": 2_500_000,
    } for i in range(40)])
    worker.dhan_client.fetch_intraday_candles = AsyncMock(return_value=frozen)

    from app.services.paper_trader import paper_trader
    pf = paper_trader.get_portfolio()
    before = len(pf.active_positions), len(pf.closed_trades)

    for i in range(12):
        with market_hours.override_clock(at(18, 0) + timedelta(minutes=5 * i)):
            state = await worker.run_single_scan_cycle("10001", "tok")
            assert state.active_mode == "closed"
            assert state.feed_status == "CLOSED"
            assert [s for s in state.signals if s.setup_type == SetupType.SETUP_5_OPTION_BB] == []
            # even if something bypassed the mode, Setup 5 itself must return nothing
            assert await worker._evaluate_option_chart_setups(
                "10001", "tok", worker.universe_mgr.get_indices()[0],
                _frozen_chain(2_500_000), "2026-10-15", 22500.0) == []
            worker._get_or_update_option_candles("44612", 43.6, 2_500_000)

    assert worker._option_forming_candle == {}
    assert worker._option_candle_history.get("44612", []) == []
    pf = paper_trader.get_portfolio()
    assert (len(pf.active_positions), len(pf.closed_trades)) == before


@pytest.mark.asyncio
async def test_in_session_scan_still_reports_live():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker.set_session_credentials("10001", "tok")
    worker.dhan_client.fetch_marketfeed_quotes = AsyncMock(return_value=_fake_marketfeed())
    worker.dhan_client.fetch_expiry_list = AsyncMock(return_value=["2026-10-15"])
    worker.dhan_client.fetch_option_chain = AsyncMock(return_value={})
    worker.dhan_client.fetch_intraday_candles = AsyncMock(return_value=pd.DataFrame())
    state = await worker.run_single_scan_cycle("10001", "tok")
    assert state.active_mode == "live"


# ---------------------------------------------------------------- option volume (P0-3)

def test_cumulative_day_volume_becomes_per_bar_increments():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    sec = "9001"
    with market_hours.override_clock(at(11, 0, 10)):
        df = worker._get_or_update_option_candles(sec, 50.0, 1_000_000)  # first obs: no increment
    assert df.iloc[-1]["volume"] == 0 and not df.iloc[-1]["volume_known"]
    with market_hours.override_clock(at(11, 2)):
        df = worker._get_or_update_option_candles(sec, 51.0, 1_000_400)
    assert df.iloc[-1]["volume"] == 400 and df.iloc[-1]["volume_known"]
    with market_hours.override_clock(at(11, 4)):
        df = worker._get_or_update_option_candles(sec, 52.0, 1_000_900)
    assert df.iloc[-1]["volume"] == 900
    with market_hours.override_clock(at(11, 5, 5)):                          # next slot
        df = worker._get_or_update_option_candles(sec, 52.0, 1_001_000)
    assert len(df) == 2
    assert df.iloc[0]["volume"] == 900 and df.iloc[1]["volume"] == 100
    assert df.iloc[1]["timestamp"] == datetime(2026, 10, 14, 11, 5)          # IST slot start


def test_unknown_volume_is_not_treated_as_zero_or_total():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    with market_hours.override_clock(at(11, 1)):
        worker._get_or_update_option_candles("9002", 50.0, None)
        df = worker._get_or_update_option_candles("9002", 51.0, None)
    assert not df.iloc[-1]["volume_known"]
    # counter going backwards (reset) re-baselines instead of producing a negative bar
    with market_hours.override_clock(at(11, 2)):
        worker._get_or_update_option_candles("9003", 50.0, 5000)
        df = worker._get_or_update_option_candles("9003", 50.0, 100)
    assert df.iloc[-1]["volume"] == 0


def _breakout_df(volume_known):
    df = create_option_candles(n=30, base_premium=100.0, start_time=datetime(2026, 10, 14, 9, 15))
    df.loc[29] = {"timestamp": datetime(2026, 10, 14, 11, 50), "open": 101.0, "high": 115.0,
                  "low": 100.5, "close": 114.0, "volume": 45000}
    df["volume_known"] = True
    df.loc[29, "volume_known"] = volume_known
    return calculate_indicators(df)


def _eval(df):
    return evaluate_option_chart_signal(
        symbol="RELIANCE", strike_symbol="RELIANCE 100 CE", option_type="CE", option_df=df,
        underlying_price=2500.0, strike_price=2500, option_security_id="1")


def test_setup5_volume_filter_does_not_pass_by_default_when_volume_unknown():
    assert _eval(_breakout_df(True)) is not None
    assert _eval(_breakout_df(False)) is None
    nan_df = _breakout_df(True)
    nan_df.loc[len(nan_df) - 1, "volume"] = float("nan")
    assert _eval(nan_df) is None


# ---------------------------------------------------------------- completed bars + cutoff (P0-4 / P0-1)

@pytest.mark.asyncio
async def test_setup5_ignores_forming_bar_breakout():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]
    slot = market_hours.ist_slot_start()
    flat = pd.DataFrame([{
        "timestamp": slot - timedelta(minutes=5 * (30 - i)), "open": 100.0 + (i % 2) * 0.1,
        "high": 100.5, "low": 99.5, "close": 100.0 + (i % 2) * 0.1, "volume": 10000,
    } for i in range(30)])
    worker.dhan_client.fetch_intraday_candles = AsyncMock(return_value=flat)
    oc = {"22500": {"ce": {"security_id": 7001, "last_price": 100.0, "volume": 50000}}}
    await worker._evaluate_option_chart_setups("c", "t", inst, oc, "2026-10-15", 22500.0)
    # price explodes inside the forming bar with a volume surge: still no signal until the bar closes
    oc["22500"]["ce"].update(last_price=140.0, volume=500000)
    res = await worker._evaluate_option_chart_setups("c", "t", inst, oc, "2026-10-15", 22500.0)
    assert res == []
    assert worker._option_forming_candle["7001"]["close"] == 140.0


@pytest.mark.asyncio
async def test_setup5_not_evaluated_after_entry_cutoff():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]
    worker.dhan_client.fetch_intraday_candles = AsyncMock(return_value=pd.DataFrame())
    oc = {"22500": {"ce": {"security_id": 7002, "last_price": 100.0, "volume": 1}}}
    with market_hours.override_clock(at(15, 16)):
        assert await worker._evaluate_option_chart_setups("c", "t", inst, oc, "x", 22500.0) == []
        worker.dhan_client.fetch_intraday_candles.assert_not_called()
        assert _eval(_breakout_df(True)) is None


def test_live_entry_rejected_after_cutoff_and_outside_session(engine):
    with market_hours.override_clock(at(15, 16)):
        assert engine.open_position_from_signal(make_signal("S1"), lots=1, feed_mode="live") is None
    with market_hours.override_clock(at(19, 0)):
        assert engine.open_position_from_signal(make_signal("S2"), lots=1, feed_mode="live") is None
    with market_hours.override_clock(at(15, 14)):
        assert engine.open_position_from_signal(make_signal("S3"), lots=1, feed_mode="live") is not None


# ---------------------------------------------------------------- exposure guards (P0-2)

def test_same_contract_cannot_be_stacked_irfc_like(engine):
    sigs = [make_signal(f"IRFC_S5_{i}", sec_id="55001") for i in range(12)]
    opened = [engine.open_position_from_signal(s, lots=1, feed_mode="live") for s in sigs]
    assert sum(p is not None for p in opened) == 1
    assert len(engine.get_portfolio().active_positions) == 1


def test_contract_key_falls_back_to_strike_symbol(engine):
    a = make_signal("A", sec_id="")
    b = make_signal("B", sec_id="")
    assert engine.open_position_from_signal(a, lots=1, feed_mode="demo") is not None
    assert engine.open_position_from_signal(b, lots=1, feed_mode="demo") is None


def test_one_position_per_stock_and_side_but_ce_and_pe_allowed(engine):
    assert engine.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")
    # different contract, same stock + side -> blocked
    assert engine.open_position_from_signal(make_signal("B", sec_id="2"), lots=1, feed_mode="live") is None
    # opposite side is a different exposure
    assert engine.open_position_from_signal(make_signal("C", side="PE", sec_id="3"), lots=1, feed_mode="live")
    # other stock is fine
    assert engine.open_position_from_signal(make_signal("D", symbol="SBIN", sec_id="4"), lots=1, feed_mode="live")


def test_cooldown_after_exit_on_same_stock_and_side(engine, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 300)
    with market_hours.override_clock(at(11, 0)):
        pos = engine.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")
        assert engine.close_position(pos.id, reason="manual")
    with market_hours.override_clock(at(11, 2)):
        assert engine.open_position_from_signal(make_signal("B", sec_id="2", entry=60.0), lots=1, feed_mode="live") is None
        # the opposite side is not on cooldown
        assert engine.open_position_from_signal(make_signal("B2", side="PE", sec_id="9"), lots=1, feed_mode="live")
    with market_hours.override_clock(at(11, 6)):
        assert engine.open_position_from_signal(make_signal("C", sec_id="3", entry=60.0), lots=1, feed_mode="live")


# ---------------------------------------------------------------- EOD / carry-over / datetimes (P0-5)

def test_eod_square_off_at_1520_with_reason_and_iso_datetimes(engine):
    with market_hours.override_clock(at(14, 0, 5)):
        pos = engine.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")
    assert pos.entry_time == "14:00:05"                            # HH:MM:SS display kept
    assert pos.entry_datetime == "2026-10-14T14:00:05+05:30"       # full ISO with date
    with market_hours.override_clock(at(15, 19, 59)):
        assert engine.square_off_if_due() == []
    with market_hours.override_clock(at(15, 20, 1)):
        closed = engine.square_off_if_due()
    assert len(closed) == 1
    # live closes without a fresh quote get a "(Modeled: Last Price)" suffix appended
    assert closed[0].exit_reason.startswith(EOD_SQUARE_OFF)
    assert closed[0].exit_time == "15:20:01"
    assert closed[0].exit_datetime == "2026-10-14T15:20:01+05:30"
    assert engine.get_portfolio().active_positions == []


def test_eod_square_off_is_configurable(engine, monkeypatch):
    monkeypatch.setattr(settings, "EOD_SQUARE_OFF_TIME", "15:25")
    with market_hours.override_clock(at(14, 0)):
        engine.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")
    with market_hours.override_clock(at(15, 21)):
        assert engine.square_off_if_due() == []
    with market_hours.override_clock(at(15, 25)):
        assert len(engine.square_off_if_due()) == 1


def test_stale_carryover_flagged_on_startup_and_excluded_from_stats(tmp_path):
    db = str(tmp_path / "carry.db")
    e1 = PaperTradingEngine(db_path=db)
    with market_hours.override_clock(at(13, 0, day=13)):                # Tuesday
        e1.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")

    with market_hours.override_clock(at(9, 16)):                         # next trading morning
        e2 = PaperTradingEngine(db_path=db)
    pf = e2.get_portfolio()
    assert pf.active_positions == []
    assert len(pf.closed_trades) == 1
    stale = pf.closed_trades[0]
    assert stale.exit_reason == STALE_CARRYOVER and stale.quarantine_reason == STALE_CARRYOVER
    assert pf.total_trades_count == 0 and pf.total_pnl == 0.0           # excluded from stats
    assert e2.get_portfolio(mode="live").total_trades_count == 0
    # persisted, so a further restart does not resurrect it
    e3 = PaperTradingEngine(db_path=db)
    assert e3.get_portfolio().active_positions == []
    assert e3.get_portfolio().closed_trades[0].quarantine_reason == STALE_CARRYOVER


def test_same_day_open_position_is_not_flagged_on_restart(tmp_path):
    db = str(tmp_path / "same.db")
    e1 = PaperTradingEngine(db_path=db)
    with market_hours.override_clock(at(10, 0)):
        e1.open_position_from_signal(make_signal("A", sec_id="1"), lots=1, feed_mode="live")
    with market_hours.override_clock(at(11, 0)):
        e2 = PaperTradingEngine(db_path=db)
    assert len(e2.get_portfolio().active_positions) == 1


def test_legacy_rows_migrate_without_losing_data(tmp_path):
    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE positions (id TEXT PRIMARY KEY, signal_id TEXT, symbol TEXT, option_type TEXT,
        strike_symbol TEXT, timeframe TEXT, setup_type TEXT, entry_time TEXT, underlying_entry REAL,
        underlying_sl REAL, underlying_target_1 REAL, underlying_target_2 REAL, option_entry REAL,
        option_sl REAL, option_target_1 REAL, option_target_2 REAL, lot_size INTEGER, lots INTEGER,
        quantity INTEGER, current_underlying REAL, current_option_price REAL, pnl_points REAL,
        pnl_rupees REAL, status TEXT, exit_time TEXT, exit_reason TEXT, initial_lots INTEGER,
        initial_quantity INTEGER, booked_lots INTEGER, booked_pnl_rupees REAL)""")
    epoch = int(datetime(2026, 10, 12, 19, 5, 0, tzinfo=IST).timestamp())    # evening: an off-session row
    conn.execute("INSERT INTO positions VALUES (" + ",".join("?" * 30) + ")",
                 (f"POS_IRFC_CE_{epoch}_abc123", "sig", "IRFC", "CE", "IRFC 100 CE", "5m", "SETUP_5_OPTION_BB",
                  "19:05:00", 100, 98, 103, 105, 43.6, 41.6, 46.6, 48.6, 100, 1, 100, 100, 40.0, -3.6,
                  -360.0, "STOPPED_OUT", "19:20:00", "Stop-Loss Hit", 1, 100, 0, 0.0))
    conn.commit()
    conn.close()

    storage = PaperStorage(db)
    active, closed = storage.load_all_positions()
    assert len(closed) == 1 and active == []
    p = closed[0]
    assert p.entry_time == "19:05:00" and p.exit_time == "19:20:00"                  # untouched
    assert p.entry_datetime == "2026-10-12T19:05:00+05:30"
    assert p.exit_datetime == "2026-10-12T19:20:00+05:30"
    assert p.pnl_rupees == -360.0
    # re-running the migration is idempotent
    PaperStorage(db)
    assert storage.load_all_positions()[1][0].entry_datetime == p.entry_datetime


# ---------------------------------------------------------------- quarantine (P0-6)

def _insert(storage, **kw):
    base = dict(
        id="X", signal_id="s", symbol="IRFC", option_type="CE", strike_symbol="IRFC 100 CE",
        timeframe="5m", setup_type="SETUP_5_OPTION_BB", entry_time="11:00:00",
        underlying_entry=100, underlying_sl=98, underlying_target_1=103, underlying_target_2=105,
        option_entry=43.6, option_sl=41.6, option_target_1=46.6, option_target_2=48.6,
        lot_size=100, lots=1, quantity=100, current_underlying=100, current_option_price=43.6,
        pnl_points=0.0, pnl_rupees=0.0, status="CLOSED", option_security_id="55001", feed_mode="live",
    )
    base.update(kw)
    storage.upsert_position(PaperPosition(**base))


def test_quarantine_flags_without_deleting_and_excludes_from_totals(tmp_path):
    db = str(tmp_path / "q.db")
    storage = PaperStorage(db)
    _insert(storage, id="GOOD", entry_datetime="2026-10-14T10:00:00+05:30", exit_datetime="2026-10-14T10:20:00+05:30",
            pnl_rupees=500.0, gross_pnl=500.0, net_pnl=480.0)
    _insert(storage, id="EVENING", entry_datetime="2026-10-14T19:00:00+05:30", exit_datetime="2026-10-14T19:10:00+05:30",
            pnl_rupees=-900.0, gross_pnl=-900.0, net_pnl=-920.0, option_security_id="55002")
    _insert(storage, id="STACK1", entry_datetime="2026-10-14T11:00:00+05:30", exit_datetime="2026-10-14T11:30:00+05:30",
            option_security_id="77")
    _insert(storage, id="STACK2", entry_datetime="2026-10-14T11:05:00+05:30", exit_datetime="2026-10-14T11:25:00+05:30",
            option_security_id="77", pnl_rupees=-300.0, gross_pnl=-300.0, net_pnl=-310.0)
    _insert(storage, id="STACK3", entry_datetime="2026-10-14T11:40:00+05:30", exit_datetime="2026-10-14T11:50:00+05:30",
            option_security_id="77")  # after STACK1 exited -> legitimate

    suspects = find_suspect_rows(db)
    assert suspects == {"EVENING": OFF_SESSION_ENTRY, "STACK2": STACKED_DUPLICATE}

    # nothing flagged until applied
    assert all(p.quarantine_reason is None for p in storage.load_all_positions()[1])
    assert apply_quarantine(db, suspects) == 2

    eng = PaperTradingEngine(db_path=db)
    pf = eng.get_portfolio()
    assert len(pf.closed_trades) == 5                       # nothing deleted
    assert pf.total_trades_count == 3                       # quarantined rows excluded
    assert pf.total_realized_pnl == 500.0
    live = eng.get_portfolio(mode="live")
    assert live.total_trades_count == 3 and live.total_realized_pnl == 500.0
    assert live.total_net_pnl == 480.0

    # reversible
    storage.clear_quarantine(["EVENING", "STACK2"])
    assert PaperTradingEngine(db_path=db).get_portfolio().total_trades_count == 5
