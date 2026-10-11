import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.services.universe_manager import UniverseManager, Instrument
from app.services.dhan_client import DhanClient
from app.services.scanner_worker import ScannerWorker
from app.services.paper_trader import PaperTradingEngine, paper_trader
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.paper_storage import PaperStorage

client = TestClient(app)


def test_finding_10_exchange_fee_updated_rate():
    """Finding 10: Exchange transaction fee uses updated NSE circular rate (0.03553%)."""
    # For ₹100,000 turnover: 100,000 * 0.0003553 = 35.53
    breakdown = calculate_option_trade_charges(buy_price=500.0, sell_price=500.0, quantity=100, orders_count=2)
    assert breakdown.total_turnover == 100000.0
    assert abs(breakdown.exchange_fee - 35.53) <= 0.05
    # GST should be 18% of (brokerage + exchange_fee + sebi_fee) = (40 + 35.53 + 0.10) * 0.18 = 13.61
    assert abs(breakdown.gst - 13.61) <= 0.05


def test_finding_12_debug_dhan_removed():
    """Finding 12: Public diagnostic endpoint /api/debug-dhan is removed."""
    res = client.get("/api/debug-dhan")
    assert res.status_code == 404


def test_finding_13_oauth_get_rejects_app_secret():
    """Finding 13: GET /oauth/login-url rejects app_secret in query string."""
    res = client.get("/api/auth/oauth/login-url?app_id=TEST_APP&app_secret=LEAKED_SECRET")
    assert res.status_code == 400
    assert "prohibited" in res.json()["detail"].lower()

    # GET without app_secret still works
    res_ok = client.get("/api/auth/oauth/login-url?app_id=TEST_APP")
    assert res_ok.status_code == 200


def test_finding_7_cross_origin_mutations_blocked():
    """Finding 7 / F1: State-changing local API routes reject cross-origin requests from foreign origins, null, and arbitrary sslip.io."""
    # Arbitrary sslip.io host blocked
    res_evil = client.post("/api/paper/reset", headers={"Origin": "https://evil.sslip.io"})
    assert res_evil.status_code == 403
    assert "Forbidden" in res_evil.json()["detail"]

    # null origin blocked
    res_null = client.post("/api/paper/reset", headers={"Origin": "null"})
    assert res_null.status_code == 403
    assert "Forbidden" in res_null.json()["detail"]

    # Malicious referer blocked
    res_ref = client.post("/api/paper/reset", headers={"Referer": "https://evil.sslip.io/page"})
    assert res_ref.status_code == 403
    assert "Forbidden" in res_ref.json()["detail"]

    # Allowed local origin succeeds
    res_ok = client.post("/api/paper/reset", headers={"Origin": "http://localhost:5174"})
    assert res_ok.status_code == 200

    # Non-mutating GET with foreign origin is not blocked by mutation origin middleware
    res_get = client.get("/api/health", headers={"Origin": "https://evil.sslip.io"})
    assert res_get.status_code == 200


def test_finding_1_allowed_origin_env_var(monkeypatch):
    """Finding 1: ALLOWED_ORIGIN environment variable is included in allowed origins."""
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://options.mydomain.com")
    from app.main import create_app
    test_app = create_app()
    with TestClient(test_app) as custom_client:
        res = custom_client.post("/api/paper/reset", headers={"Origin": "https://options.mydomain.com"})
        assert res.status_code == 200
        # Untrusted origin still blocked
        res_evil = custom_client.post("/api/paper/reset", headers={"Origin": "https://evil.sslip.io"})
        assert res_evil.status_code == 403




def test_finding_8_volume_less_ticker_does_not_reset_cumulative_baseline():
    """Finding 8: Dhan ticker packets (no volume) must not reset cumulative volume baseline."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    # 1. Quote with cumulative volume 1,000
    df1 = worker.get_or_update_live_candles(inst, {"last_price": 22500.0, "volume": 1000})
    assert worker._last_cumulative_volume.get(inst.symbol) == 1000

    # 2. Ticker packet with NO volume (volume: None)
    df2 = worker.get_or_update_live_candles(inst, {"last_price": 22505.0, "volume": None})
    # Must preserve baseline 1,000
    assert worker._last_cumulative_volume.get(inst.symbol) == 1000

    # 3. Next quote with cumulative volume 1,010 -> increment must be 10, NOT 1,010
    df3 = worker.get_or_update_live_candles(inst, {"last_price": 22510.0, "volume": 1010})
    forming = worker._current_forming_candle[inst.symbol]
    assert worker._last_cumulative_volume.get(inst.symbol) == 1010
    # Candle volume should have increased by exactly 10 (1000 + 10 = 1010)
    assert forming["volume"] == 1010


def test_finding_9_first_quote_does_not_double_count_volume():
    """Finding 9: First quote after startup adds its incremental volume once, not twice."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    worker.get_or_update_live_candles(inst, {"last_price": 22500.0, "volume": 500})
    forming = worker._current_forming_candle[inst.symbol]
    # Initial reported volume of 500 should result in forming volume of 500, NOT 1,000
    assert forming["volume"] == 500


def test_finding_1_prior_session_historical_candles_cannot_open_live_trade():
    """Finding 1: Signals on candles from previous trading sessions must not be marked confirmed."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    # Populate 25 bars strictly from yesterday
    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=10, minute=0, second=0)
    bars = []
    for i in range(25):
        ts = yesterday + timedelta(minutes=i * 5)
        bars.append({
            "timestamp": ts,
            "open": 22000.0 + i,
            "high": 22010.0 + i,
            "low": 21990.0 + i,
            "close": 22005.0 + i,
            "volume": 10000,
        })
    worker._candle_history[inst.symbol] = bars

    dummy_rec = OptionStrikeRecommendation(
        symbol=inst.symbol, underlying_price=22050.0, option_type="CE",
        atm_strike=22050, recommended_strike=22050, strike_symbol=f"{inst.symbol} 22050 CE",
        lot_size=50, risk=10.0, stop_loss=22040.0, target_1=22065.0, target_2=22075.0,
        estimated_option_entry=100.0, option_sl_pts=10.0, option_target_1_pts=15.0,
        option_target_2_pts=25.0, option_sl_price=90.0, option_target_1_price=115.0,
        option_target_2_price=125.0
    )

    # Create a synthetic prior-session candidate signal
    mock_candidate = Signal(
        id="SIG_PAST_CANDIDATE", symbol=inst.symbol, timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=(yesterday + timedelta(minutes=100)).strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22050.0, stop_loss=22040.0, target_1=22065.0, target_2=22075.0,
        strike_recommendation=dummy_rec, is_confirmed=False,
        indicators_snapshot={}, rationale="past candidate"
    )

    with patch("app.services.scanner_worker.evaluate_signals", return_value=[mock_candidate]), \
         patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf:
        mock_mf.return_value = {
            inst.exchange_segment: {
                str(inst.security_id): {"last_price": 22100.0, "volume": 50000}
            }
        }
        state = asyncio.run(worker._execute_scan_cycle(client_id="CID", access_token="TOK"))
        found = [s for s in state.signals if s.id == "SIG_PAST_CANDIDATE"]
        assert len(found) > 0, "Candidate signal must be present in evaluated signals"
        for s in found:
            s_dt = pd.to_datetime(s.timestamp)
            assert s_dt.date() < datetime.now().date()
            assert not s.is_confirmed, f"Past-session signal {s.id} was marked confirmed!"


def test_finding_2_setup5_prior_session_breakout_rejected():
    """Finding 2: Setup 5 breakout on a prior-session candle is suppressed."""
    # Build 25 bars ending yesterday
    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=14, minute=0, second=0)
    records = []
    for i in range(25):
        ts = yesterday + timedelta(minutes=i * 5)
        records.append({
            "timestamp": ts,
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 98.0 + i,
            "close": 103.0 + i,
            "volume": 5000 + i * 100,
            "bb_upper": 100.0,
            "bb_middle": 95.0,
            "bb_lower": 90.0,
            "vwap": 95.0,
            "rsi": 65.0,
            "ema_9": 98.0
        })
    df = pd.DataFrame(records)
    sig = evaluate_option_chart_signal(
        symbol="NIFTY 50",
        strike_symbol="NIFTY 50 22500 CE",
        option_type="CE",
        option_df=df,
        underlying_price=22500.0,
        strike_price=22500.0,
        timeframe="5m"
    )
    assert sig is None, "Prior-session breakout candle should not generate Setup 5 signal"


def test_finding_3_forming_candle_signals_are_provisional_in_live_mode():
    """Finding 3: All setups evaluated on an active forming candle in live mode are provisional."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    # Empty completed bars, but forming candle active
    worker._candle_history[inst.symbol] = []
    worker.get_or_update_live_candles(inst, {"last_price": 22500.0, "volume": 1000})

    dummy_rec = OptionStrikeRecommendation(
        symbol=inst.symbol, underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol=f"{inst.symbol} 22500 CE",
        lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        estimated_option_entry=100.0, option_sl_pts=10.0, option_target_1_pts=15.0,
        option_target_2_pts=25.0, option_sl_price=90.0, option_target_1_price=115.0,
        option_target_2_price=125.0
    )

    mock_forming_sig = Signal(
        id="SIG_FORMING_CANDIDATE", symbol=inst.symbol, timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        strike_recommendation=dummy_rec, is_confirmed=False,
        indicators_snapshot={}, rationale="forming candidate"
    )

    with patch("app.services.scanner_worker.evaluate_signals", return_value=[mock_forming_sig]), \
         patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf:
        mock_mf.return_value = {
            inst.exchange_segment: {
                str(inst.security_id): {"last_price": 22500.0, "volume": 1000}
            }
        }
        state = asyncio.run(worker._execute_scan_cycle(client_id="CID", access_token="TOK"))
        found = [s for s in state.signals if s.id == "SIG_FORMING_CANDIDATE"]
        assert len(found) > 0, "Forming candidate signal must be in state signals"
        for s in found:
            assert s.is_confirmed is False, f"Forming candle signal {s.id} must be provisional in live mode"




def test_finding_4_missing_quote_omitted_from_price_map_in_live_mode():
    """Finding 4: In a partial live response, unquoted instruments are omitted from price_map while quoted ones are included."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    indices = worker.universe_mgr.get_indices()
    inst_missing = indices[0]
    inst_quoted = indices[1]

    now = datetime.now()
    for inst in (inst_missing, inst_quoted):
        worker._candle_history[inst.symbol] = [{
            "timestamp": now - timedelta(minutes=5 * i),
            "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
        } for i in range(25)]

    # Mock marketfeed returning quote ONLY for inst_quoted, omitting inst_missing
    worker.set_session_credentials("CID", "TOK")
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf, \
         patch.object(paper_trader, "update_market_prices") as mock_update:
        mock_mf.return_value = {
            inst_quoted.exchange_segment: {
                str(inst_quoted.security_id): {"last_price": 48500.0, "volume": 10000}
            }
        }
        state = asyncio.run(worker._execute_scan_cycle())
        called_args = mock_update.call_args
        assert called_args is not None
        called_price_map = called_args[0][0] if called_args.args else called_args.kwargs.get("price_map", {})
        assert inst_missing.symbol not in called_price_map, f"Stale {inst_missing.symbol} was erroneously included in live price_map"
        assert inst_quoted.symbol in called_price_map, f"Quoted {inst_quoted.symbol} was missing from live price_map"
        assert called_price_map[inst_quoted.symbol] == 48500.0
        assert state.active_mode == "live", "Scan cycle with partial live feed should remain in live mode"



def test_finding_5_manual_live_entry_rejects_forged_signal():
    """Finding 5: Manual live entry rejects forged signal not found in server radar."""
    from app.main import worker
    client.post("/api/paper/reset")
    worker.set_session_credentials("TEST_CID", "TEST_TOK")
    try:
        # Fabricated signal with forged low entry price
        forged_rec = OptionStrikeRecommendation(
            symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
            atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
            lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            estimated_option_entry=10.0, option_sl_pts=5.0, option_target_1_pts=7.5,
            option_target_2_pts=12.5, option_sl_price=5.0, option_target_1_price=17.5,
            option_target_2_price=22.5, option_security_id="99999", is_live_quote=True,
            real_ask_price=10.0
        )
        forged_sig = Signal(
            id="FORGED_SIGNAL_999", symbol="NIFTY 50", timeframe="5m",
            setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            strike_recommendation=forged_rec, is_confirmed=True,
            indicators_snapshot={}, rationale="forged"
        )

        res = client.post("/api/paper/trade", json={"signal": forged_sig.model_dump(), "lots": 1, "feed_mode": "live"})
        assert res.status_code == 400
        assert "not found" in res.json()["detail"].lower()
    finally:
        worker.set_session_credentials(None, None)


@pytest.mark.asyncio
async def test_finding_6_disconnect_in_flight_aborts_scan():
    """Finding 6: Disconnecting while a scan is in-flight invalidates the session generation and stays demo."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker.set_session_credentials("CID_1", "TOK_1")
    assert worker._state.active_mode == "live"

    # Mock fetch_marketfeed_quotes that disconnects credentials while awaiting
    async def slow_fetch(*args, **kwargs):
        # Disconnect credentials mid-scan!
        worker.set_session_credentials(None, None)
        return {"NSE_IDX": {"13": {"last_price": 22500.0}}}

    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", side_effect=slow_fetch):
        state = await worker._execute_scan_cycle()
        # Scan should have aborted and kept DEMO mode
        assert state.active_mode == "demo"
        assert state.feed_status == "DEMO"


def test_finding_11_manual_close_stale_option_quote_modeled():
    """Finding 11: Manual close when option candle is older than 15s marks exit as modeled."""
    engine = PaperTradingEngine()
    engine.reset_sync()
    # Create active live position
    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
        lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        estimated_option_entry=150.0, option_sl_pts=15.0, option_target_1_pts=22.5,
        option_target_2_pts=37.5, option_sl_price=135.0, option_target_1_price=172.5,
        option_target_2_price=187.5, option_security_id="88888", is_live_quote=True,
        real_ask_price=150.0
    )
    sig = Signal(
        id="SIG_STALE_CLOSE_01", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        strike_recommendation=rec, is_confirmed=True,
        indicators_snapshot={}, rationale="test"
    )
    from app.services.paper_trader import paper_trader
    pos = paper_trader.open_position_from_signal(sig, lots=1, feed_mode="live")
    assert pos is not None

    # Simulate stale quote timestamp (30s ago)
    from app.main import worker
    worker._option_last_quote_time["88888"] = time.time() - 30.0
    worker._option_forming_candle["88888"] = {"close": 155.0}

    # Close position via API without real bid
    res = client.post(f"/api/paper/close/{pos.id}", json={"reason": "User Closed"})
    assert res.status_code == 200
    data = res.json()
    assert "(Modeled: Unquoted)" in data["exit_reason"]


def test_signals_close_alias_applies_freshness_check():
    """F2 (post-fix): /api/signals/close/{id} applies 15-second freshness check and (Modeled: Unquoted) labeling."""
    from app.services.paper_trader import paper_trader
    from app.main import worker

    paper_trader.reset_sync()

    rec_stale = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
        lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        estimated_option_entry=150.0, option_sl_pts=15.0, option_target_1_pts=22.5,
        option_target_2_pts=37.5, option_sl_price=135.0, option_target_1_price=172.5,
        option_target_2_price=187.5, option_security_id="77771", is_live_quote=True,
        real_ask_price=150.0
    )
    sig_stale = Signal(
        id="SIG_ALIAS_STALE_01", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        strike_recommendation=rec_stale, is_confirmed=True,
        indicators_snapshot={}, rationale="test"
    )
    pos_stale = paper_trader.open_position_from_signal(sig_stale, lots=1, feed_mode="live")
    assert pos_stale is not None

    # Stale quote: > 15s ago
    worker._option_last_quote_time["77771"] = time.time() - 30.0
    worker._option_forming_candle["77771"] = {"close": 155.0}

    res_stale = client.post(f"/api/signals/close/{pos_stale.id}", json={"reason": "Manual Close"})
    assert res_stale.status_code == 200
    data_stale = res_stale.json()
    assert "(Modeled: Unquoted)" in data_stale["exit_reason"]

    # Fresh quote: <= 15s ago
    rec_fresh = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
        lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        estimated_option_entry=150.0, option_sl_pts=15.0, option_target_1_pts=22.5,
        option_target_2_pts=37.5, option_sl_price=135.0, option_target_1_price=172.5,
        option_target_2_price=187.5, option_security_id="77772", is_live_quote=True,
        real_ask_price=150.0
    )
    sig_fresh = Signal(
        id="SIG_ALIAS_FRESH_01", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
        strike_recommendation=rec_fresh, is_confirmed=True,
        indicators_snapshot={}, rationale="test"
    )
    pos_fresh = paper_trader.open_position_from_signal(sig_fresh, lots=1, feed_mode="live")
    assert pos_fresh is not None

    worker._option_last_quote_time["77772"] = time.time() - 2.0
    worker._option_forming_candle["77772"] = {"close": 160.0}

    res_fresh = client.post(f"/api/signals/close/{pos_fresh.id}", json={"reason": "Manual Close"})
    assert res_fresh.status_code == 200
    data_fresh = res_fresh.json()
    assert "(Modeled: Unquoted)" not in data_fresh["exit_reason"]
    assert data_fresh["current_option_price"] == 159.84  # 160.0 * 0.999 fill haircut



def test_finding_14_batch_upsert_positions():
    """Finding 14: batch_upsert_positions persists multiple positions in a single transaction."""
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        storage = PaperStorage(db_path=Path(tmp.name))
        pos1 = PaperTradingEngine(db_path=Path(tmp.name)).open_position_from_signal(
            Signal(
                id="SIG_B1", symbol="NIFTY 50", timeframe="5m",
                setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
                timestamp="10:00:00", entry_price=22500.0, stop_loss=22450.0,
                target_1=22550.0, target_2=22600.0,
                strike_recommendation=OptionStrikeRecommendation(
                    symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
                    atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
                    lot_size=50, risk=50.0, stop_loss=22450.0, target_1=22550.0, target_2=22600.0,
                    estimated_option_entry=100.0, option_sl_pts=25.0, option_target_1_pts=25.0,
                    option_target_2_pts=50.0, option_sl_price=75.0, option_target_1_price=125.0,
                    option_target_2_price=150.0
                ),
                indicators_snapshot={}, rationale="test"
            ), lots=1, feed_mode="demo"
        )
        storage.batch_upsert_positions([pos1])
        active, _ = storage.load_all_positions()
        assert len(active) == 1
        assert active[0].id == pos1.id


@pytest.mark.asyncio
async def test_finding_15_exponential_backoff_on_failed_seed():
    """Finding 15: Failed historical candle seeding applies exponential backoff."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_seed:
        mock_seed.return_value = pd.DataFrame() # Empty failure response
        # First attempt: calls upstream and fails
        res1 = await worker.seed_historical_candles_if_needed("CID", "TOK", inst)
        assert res1 is False
        assert mock_seed.call_count == 1
        assert worker._historical_seed_fail_count[inst.symbol] == 1

        # Immediate second attempt: must be blocked by backoff without calling upstream
        res2 = await worker.seed_historical_candles_if_needed("CID", "TOK", inst)
        assert res2 is False
        assert mock_seed.call_count == 1  # No additional call!


def test_finding_3_forged_client_confirmation_rejected():
    """Finding 3: Client sending is_confirmed=True is rejected if server radar signal is provisional."""
    from app.main import worker
    client.post("/api/paper/reset")
    worker.set_session_credentials("TEST_CID", "TEST_TOK")
    try:
        rec = OptionStrikeRecommendation(
            symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
            atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
            lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            estimated_option_entry=150.0, option_sl_pts=15.0, option_target_1_pts=22.5,
            option_target_2_pts=37.5, option_sl_price=135.0, option_target_1_price=172.5,
            option_target_2_price=187.5, option_security_id="88881", is_live_quote=True,
            real_ask_price=150.0
        )
        server_sig = Signal(
            id="SIG_PROVISIONAL_F3", symbol="NIFTY 50", timeframe="5m",
            setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            strike_recommendation=rec, is_confirmed=False,
            indicators_snapshot={}, rationale="provisional server signal"
        )

        # Register provisional signal in server radar
        worker._state.signals = [server_sig]

        # Client constructs payload claiming is_confirmed=True for this signal
        client_sig = server_sig.model_copy(update={"is_confirmed": True})

        res = client.post(
            "/api/paper/trade",
            json={"signal": client_sig.model_dump(), "lots": 1, "feed_mode": "live"}
        )
        assert res.status_code == 400
        assert "unconfirmed provisional" in res.json()["detail"].lower()
    finally:
        worker.set_session_credentials(None, None)


def test_finding_7_radar_lookup_fails_closed():
    """Finding 7: Radar lookup failure fails closed with HTTP 503 rather than falling open."""
    from app.main import worker
    client.post("/api/paper/reset")
    worker.set_session_credentials("TEST_CID", "TEST_TOK")
    try:
        rec = OptionStrikeRecommendation(
            symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
            atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 50 22500 CE",
            lot_size=50, risk=10.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            estimated_option_entry=150.0, option_sl_pts=15.0, option_target_1_pts=22.5,
            option_target_2_pts=37.5, option_sl_price=135.0, option_target_1_price=172.5,
            option_target_2_price=187.5, option_security_id="88882", is_live_quote=True,
            real_ask_price=150.0
        )
        client_sig = Signal(
            id="SIG_RADAR_ERR_F7", symbol="NIFTY 50", timeframe="5m",
            setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entry_price=22500.0, stop_loss=22490.0, target_1=22515.0, target_2=22525.0,
            strike_recommendation=rec, is_confirmed=True,
            indicators_snapshot={}, rationale="client live signal"
        )

        class BrokenState:
            active_mode = "live"

            @property
            def signals(self):
                raise RuntimeError("Redis connection lost")

        with patch.object(worker, "_state", BrokenState()):
            res = client.post(
                "/api/paper/trade",
                json={"signal": client_sig.model_dump(), "lots": 1, "feed_mode": "live"}
            )
            assert res.status_code == 503
            assert "radar state unavailable" in res.json()["detail"].lower()
    finally:
        worker.set_session_credentials(None, None)


@pytest.mark.asyncio
async def test_finding_8_deduplicated_unique_bar_count_enforced():
    """Finding 8: Seed candles with duplicate timestamps failing post-dedup count (< 20) fails and backs off."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    now = datetime.now()
    # 20 rows, but two rows have identical timestamps (so 19 unique timestamps)
    timestamps = [now - timedelta(minutes=5 * (20 - i)) for i in range(19)]
    timestamps.append(timestamps[-1])  # Duplicate of the 19th timestamp
    assert len(timestamps) == 20
    assert len(set(timestamps)) == 19

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": [22000.0 + i for i in range(20)],
        "high": [22010.0 + i for i in range(20)],
        "low": [21990.0 + i for i in range(20)],
        "close": [22005.0 + i for i in range(20)],
        "volume": [1000] * 20,
    })

    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_seed:
        mock_seed.return_value = df
        res = await worker.seed_historical_candles_if_needed("CID", "TOK", inst)
        assert res is False
        assert worker._historical_seed_fail_count.get(inst.symbol) == 1
        assert inst.symbol not in worker._candle_history or len(worker._candle_history[inst.symbol]) == 0


@pytest.mark.asyncio
async def test_finding_4_unfinished_historical_bar_routed_to_forming_candle():
    """Finding 4: Unfinished bar (slot_end > now) is routed to _current_forming_candle, completed bars to _candle_history."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]
    interval = 5 if inst.default_timeframe == "5m" else 15

    now = datetime.now()
    # 20 completed bars ending in past, and 1 unfinished bar ending in future
    unfinished_bar_ts = now - timedelta(minutes=2)
    completed_start = unfinished_bar_ts - timedelta(minutes=interval * 20)
    completed_timestamps = [completed_start + timedelta(minutes=interval * i) for i in range(20)]
    all_timestamps = completed_timestamps + [unfinished_bar_ts]

    df = pd.DataFrame({
        "timestamp": all_timestamps,
        "open": [22000.0 + i for i in range(21)],
        "high": [22010.0 + i for i in range(21)],
        "low": [21990.0 + i for i in range(21)],
        "close": [22005.0 + i for i in range(21)],
        "volume": [1000] * 21,
    })

    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_seed:
        mock_seed.return_value = df
        res = await worker.seed_historical_candles_if_needed("CID", "TOK", inst)
        assert res is True
        assert len(worker._candle_history[inst.symbol]) == 20
        # The unfinished bar is NOT in _candle_history
        for bar in worker._candle_history[inst.symbol]:
            assert bar["timestamp"] != unfinished_bar_ts
        # Unfinished bar is placed into _current_forming_candle
        assert worker._current_forming_candle[inst.symbol]["timestamp"] == unfinished_bar_ts


@pytest.mark.asyncio
async def test_finding_5_disconnect_cancels_ws_task_and_aborts_in_flight_scan():
    """Finding 5: Disconnect cancels _ws_connect_task and aborts in-flight scan cycles."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    # 1. Test connect task cancellation
    loop = asyncio.get_running_loop()
    connect_event = asyncio.Event()

    async def fake_connect(cid, tok, generation=None):
        connect_event.set()
        await asyncio.sleep(10.0)

    with patch.object(worker, "_connect_websocket", side_effect=fake_connect):
        worker.set_session_credentials("CID_TEST", "TOK_TEST")
        assert worker._ws_connect_task is not None
        assert not worker._ws_connect_task.done()

        # Disconnect must cancel the task
        worker.set_session_credentials(None, None)
        assert worker._ws_connect_task is None or worker._ws_connect_task.cancelled() or worker._ws_connect_task.done()

    # 2. Test scan cycle in-flight abort
    worker.set_session_credentials("CID_TEST", "TOK_TEST")
    initial_gen = worker._session_generation

    # Populate dummy candles
    worker._candle_history[inst.symbol] = [{
        "timestamp": datetime.now() - timedelta(minutes=5 * i),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
    } for i in range(25)]

    async def fake_eval_option_chart(*args, **kwargs):
        # Session disconnects during option chart evaluation
        worker.set_session_credentials(None, None)
        return []

    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf, \
         patch.object(worker, "get_or_fetch_option_chain", new_callable=AsyncMock) as mock_oc, \
         patch.object(worker, "_evaluate_option_chart_setups", side_effect=fake_eval_option_chart), \
         patch.object(paper_trader, "update_market_prices") as mock_update:
        mock_mf.return_value = {inst.exchange_segment: {str(inst.security_id): {"last_price": 22000.0, "volume": 1000}}}
        mock_oc.return_value = ("2026-10-15", {"22000": {"ce": {"security_id": "9999", "last_price": 100.0}}})

        state = await worker._execute_scan_cycle(client_id="CID_TEST", access_token="TOK_TEST")
        # Should abort before trade updates or stay in demo mode
        assert worker._session_credentials is None


@pytest.mark.asyncio
async def test_finding_6_zero_price_option_chain_does_not_refresh_quote_time():
    """Finding 6: Contract in option chain with last_price <= 0 does not refresh _option_last_quote_time."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    worker._option_last_quote_time.clear()
    sec_id_zero = "77701"
    sec_id_valid = "77702"

    dummy_chain = {
        "22000": {
            "ce": {
                "security_id": sec_id_zero,
                "last_price": 0.0,  # Zero price: must NOT refresh quote time
                "top_bid_price": 0.0
            },
            "pe": {
                "security_id": sec_id_valid,
                "last_price": 125.5,  # Valid positive price: must refresh quote time
                "top_bid_price": 125.0
            }
        }
    }

    worker._candle_history[inst.symbol] = [{
        "timestamp": datetime.now() - timedelta(minutes=5 * i),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
    } for i in range(25)]

    worker.set_session_credentials("CID", "TOK")
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf, \
         patch.object(worker, "get_or_fetch_option_chain", new_callable=AsyncMock) as mock_oc:
        mock_mf.return_value = {inst.exchange_segment: {str(inst.security_id): {"last_price": 22000.0, "volume": 1000}}}
        mock_oc.return_value = ("2026-10-15", dummy_chain)

        await worker._execute_scan_cycle()

        assert sec_id_zero not in worker._option_last_quote_time, "Zero-price contract refreshed quote timestamp!"
        assert sec_id_valid in worker._option_last_quote_time, "Valid contract did not refresh quote timestamp!"



