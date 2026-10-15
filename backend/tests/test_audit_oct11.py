import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_direct_client_capability_required():
    """F1: Direct client mutations (no Origin/Referer) require a valid capability token."""
    # 1. Missing capability on direct mutation -> 401
    res_no_cap = client.post("/api/paper/reset", headers={"X-Omit-Capability": "1"})
    assert res_no_cap.status_code == 401
    assert "capability required" in res_no_cap.json()["detail"].lower()

    # 2. Invalid capability token on direct mutation -> 401
    res_bad_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": "wrong-secret-token"})
    assert res_bad_cap.status_code == 401
    assert "capability" in res_bad_cap.json()["detail"].lower()

    # 3. Valid X-Dashboard-Capability header -> 200
    res_good_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY})
    assert res_good_cap.status_code == 200

    # 4. Valid Authorization Bearer header -> 200
    res_auth = client.post("/api/paper/reset", headers={"Authorization": f"Bearer {settings.DASHBOARD_CAPABILITY}"})
    assert res_auth.status_code == 200

    # 5. Browser request with valid origin still requires capability -> 401 if omitted, 200 when capability present
    res_origin = client.post("/api/paper/reset", headers={"Origin": "http://localhost:5174", "X-Omit-Capability": "1"})
    assert res_origin.status_code == 401

    res_origin_with_cap = client.post(
        "/api/paper/reset",
        headers={"Origin": "http://localhost:5174", "X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY}
    )
    assert res_origin_with_cap.status_code == 200

    # 6. Browser request with untrusted origin -> 403 Forbidden even if capability provided
    res_evil = client.post(
        "/api/paper/reset",
        headers={"Origin": "https://evil.sslip.io", "X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY}
    )
    assert res_evil.status_code == 403

    # 7. Direct GET request with no capability -> 200 (read routes not blocked)
    res_get = client.get("/api/health", headers={"X-Omit-Capability": "1"})
    assert res_get.status_code == 200


def test_server_owned_exit_pricing(no_reentry_cooldown):
    """F2, F4: Both close routes use server-owned OptionQuote records and reject caller-supplied fill prices."""
    from datetime import datetime
    from app.services.paper_trader import paper_trader
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation
    from app.main import worker

    paper_trader.reset_sync()
    sec_id = "99881"

    rec1 = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id=sec_id, is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )
    sig1 = Signal(
        id="SIG_F2_TEST_1", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec1, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )

    pos = paper_trader.open_position_from_signal(sig1, feed_mode="live")
    assert pos is not None

    # Clear quotes on worker initially
    worker._latest_option_quotes.clear()
    worker._option_last_quote_time.clear()

    # 1. Attacker submits forged bid of 10,000. Server has NO quote in store.
    # Must NOT fill at 10,000. Must be labeled "(Modeled: Unquoted)".
    res_forged = client.post(
        f"/api/paper/close/{pos.id}",
        json={"reason": "User Closed", "real_bid_price": 10000.0, "real_opt_price": 10000.0}
    )
    assert res_forged.status_code == 200
    closed_data = res_forged.json()
    assert "(Modeled: Unquoted)" in closed_data["exit_reason"]
    assert closed_data["current_option_price"] < 1000.0, "Attacker inflated fill price!"

    # 2. Test server-owned quote lookup (fresh OptionQuote)
    sig2 = Signal(
        id="SIG_F2_TEST_2", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec1, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )
    pos2 = paper_trader.open_position_from_signal(sig2, feed_mode="live")
    assert pos2 is not None

    # Record legitimate server-side OptionQuote
    worker.record_option_quote(sec_id, ltp=120.0, bid=119.5, source="chain")

    res_fresh = client.post(
        f"/api/signals/close/{pos2.id}",
        json={"reason": "Manual Close"}
    )
    assert res_fresh.status_code == 200
    closed2 = res_fresh.json()
    assert "(Modeled" not in closed2["exit_reason"]
    assert closed2["current_option_price"] == 119.5
    assert closed2["exit_slippage"] == 0.5  # 120.0 theoretical - 119.5 real_bid


def test_server_governed_feed_mode():
    """F3: Reject feed_mode='live' when server is in demo mode (HTTP 409), and purge signals/radar on logout."""
    from datetime import datetime
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation
    from app.main import worker

    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id="99882", is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )
    sig = Signal(
        id="SIG_F3_RADAR_TEST", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )

    # 1. Server in live mode has an active signal
    worker.set_session_credentials("TEST_CID", "TEST_TOK")
    worker._state.signals = [sig]
    assert len(worker.get_state().signals) == 1

    # 2. Session disconnects (logout)
    worker.set_session_credentials(None, None)
    assert worker.get_state().active_mode == "demo"
    assert worker._session_credentials is None
    # Verify signals and radar were purged
    assert len(worker.get_state().signals) == 0
    assert len(worker.get_state().radar) == 0

    # 3. Client attempts to execute a trade specifying feed_mode="live" after disconnect
    res = client.post(
        "/api/paper/trade",
        json={"signal": sig.model_dump(), "lots": 1, "feed_mode": "live"}
    )
    assert res.status_code == 409
    assert "live feed unavailable" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_scan_disconnect_guard_finally():
    """F5: Abort state publication if disconnected during _subscribe_active_positions, and clear is_scanning in finally."""
    from unittest.mock import AsyncMock, patch
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager
    from datetime import datetime, timedelta

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    worker._candle_history[inst.symbol] = [{
        "timestamp": datetime.now() - timedelta(minutes=5 * i),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
    } for i in range(25)]

    worker.set_session_credentials("CID_GUARD", "TOK_GUARD")
    broadcast_called = False

    async def fake_broadcast(*args, **kwargs):
        nonlocal broadcast_called
        broadcast_called = True

    worker.broadcast = fake_broadcast

    # 1. Test disconnect during _subscribe_active_positions
    async def disconnect_during_subscribe():
        # Disconnect credentials while subscribing to active positions
        worker.set_session_credentials(None, None)

    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf, \
         patch.object(worker, "get_or_fetch_option_chain", new_callable=AsyncMock) as mock_oc, \
         patch.object(worker, "_subscribe_active_positions", side_effect=disconnect_during_subscribe):
        mock_mf.return_value = {inst.exchange_segment: {str(inst.security_id): {"last_price": 22000.0, "volume": 1000}}}
        mock_oc.return_value = ("2026-10-15", {})

        worker.ws_manager = AsyncMock()
        worker.ws_manager.is_healthy = True
        worker.ws_manager.is_connected = True

        state = await worker._execute_scan_cycle(client_id="CID_GUARD", access_token="TOK_GUARD")

        assert worker._session_credentials is None
        assert worker._state.is_scanning is False
        assert broadcast_called is False, "Broadcast was sent after disconnect during position subscription!"
        assert len(worker._state.signals) == 0

    # 2. Test unhandled exception in scan cycle clears is_scanning in finally
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", side_effect=RuntimeError("Network explosion")):
        worker.set_session_credentials("CID_2", "TOK_2")
        try:
            await worker._execute_scan_cycle(client_id="CID_2", access_token="TOK_2")
        except RuntimeError:
            pass
        assert worker._state.is_scanning is False, "is_scanning remained True after exception!"


def test_finding_6_intraday_volume_baseline_checks_today_bars():
    """F6: Prior-session bars in history do not prevent first today quote from initializing forming candle volume."""
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager
    from datetime import timedelta
    from app.services import market_hours

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]
    now = market_hours.now_ist_naive()  # pinned exchange clock, not the wall clock

    # Pre-populate history with bars from YESTERDAY
    yesterday = now - timedelta(days=1)
    worker._candle_history[inst.symbol] = [{
        "timestamp": yesterday.replace(hour=15, minute=0, second=0),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 50000
    }]
    worker._last_cumulative_volume.clear()
    worker._current_forming_candle.clear()

    # Quote arrives today with cumulative volume 8000
    df = worker.get_or_update_live_candles(inst, {"last_price": 22050.0, "volume": 8000})
    forming = worker._current_forming_candle[inst.symbol]
    # Because there were NO bars from today, forming candle should have received 8000 volume
    assert forming["volume"] == 8000, f"Expected 8000, got {forming['volume']}"

    # Second tick with cumulative volume 8050 -> incremental should be 50 -> total 8050
    df2 = worker.get_or_update_live_candles(inst, {"last_price": 22055.0, "volume": 8050})
    assert worker._current_forming_candle[inst.symbol]["volume"] == 8050


@pytest.mark.asyncio
async def test_finding_8_ordered_async_persistence_queue_and_flush(tmp_path, no_reentry_cooldown):
    """F8: Dedicated asyncio.Queue guarantees FIFO sequential commits and flushes pending writes on shutdown."""
    import asyncio
    from app.services.paper_trader import PaperTradingEngine
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation

    db_file = str(tmp_path / "test_trades_f8.db")
    engine = PaperTradingEngine(db_path=db_file)
    await engine.start_persistence_worker()

    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id="88801", is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )

    positions = []
    for i in range(5):
        # Distinct stock + contract per signal: stacking the same contract/side is now rejected
        rec_i = rec.model_copy(update={
            "symbol": f"STOCK{i}", "option_security_id": f"8880{i}", "strike_symbol": f"STOCK{i} 22500 CE",
        })
        sig = Signal(
            id=f"SIG_F8_{i}", symbol=f"STOCK{i}", timeframe="5m",
            setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
            timestamp=f"09:3{i}:00", entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
            strike_recommendation=rec_i, is_confirmed=True, indicators_snapshot={}, rationale="test"
        )
        pos = engine.open_position_from_signal(sig, feed_mode="demo")
        assert pos is not None
        positions.append(pos)

    # Await flush
    await engine.flush()

    # Verify all 5 positions were sequentially written to DB
    loaded_active, loaded_closed = engine.storage.load_all_positions()
    loaded_ids = {p.id for p in loaded_active}
    for p in positions:
        assert p.id in loaded_ids

    await engine.stop_persistence_worker()


@pytest.mark.asyncio
async def test_finding_9_5m_option_chart_cached_within_slot():
    """F9: 5-minute option chart candles are cached by contract within the 5m slot to avoid redundant network downloads."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    import pandas as pd
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager
    from datetime import datetime

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    sec_id = "55501"
    dummy_df = pd.DataFrame([{
        "timestamp": datetime.now(),
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000
    } for _ in range(25)])

    dummy_oc = {
        "22500": {
            "ce": {"security_id": sec_id, "last_price": 102.0, "volume": 1000}
        }
    }

    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = dummy_df

        # First evaluation: fetches from dhan_client
        res1 = await worker._evaluate_option_chart_setups("CID", "TOK", inst, dummy_oc, "2026-10-15", 22500.0)
        assert mock_fetch.call_count == 1

        # Second evaluation in same scan cycle / slot: uses cache!
        res2 = await worker._evaluate_option_chart_setups("CID", "TOK", inst, dummy_oc, "2026-10-15", 22500.0)
        assert mock_fetch.call_count == 1, "Cached 5m option chart was re-fetched over the network!"


@pytest.mark.asyncio
async def test_finding_7_in_flight_disconnect_barrier_race():
    """F7: Disconnect race verified with an asyncio.Event barrier ensuring await point was actively suspended."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager
    from datetime import datetime, timedelta

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    worker._candle_history[inst.symbol] = [{
        "timestamp": datetime.now() - timedelta(minutes=5 * i),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
    } for i in range(25)]

    worker.set_session_credentials("CID_RACE", "TOK_RACE")

    paused_event = asyncio.Event()
    release_event = asyncio.Event()

    async def slow_marketfeed_await(*args, **kwargs):
        # Signal that the network await is now actively paused
        paused_event.set()
        # Wait until barrier is released
        await release_event.wait()
        return {inst.exchange_segment: {str(inst.security_id): {"last_price": 22000.0, "volume": 1000}}}

    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", side_effect=slow_marketfeed_await):
        scan_task = asyncio.create_task(
            worker._execute_scan_cycle(client_id="CID_RACE", access_token="TOK_RACE")
        )

        # Wait until scan is actively paused inside network await
        await paused_event.wait()

        # In-flight disconnect occurs while scan is suspended!
        worker.set_session_credentials(None, None)

        # Release the network await
        release_event.set()

        state = await scan_task

        assert worker._session_credentials is None
        assert state.active_mode == "demo"
        assert worker._state.is_scanning is False
