import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scanner_worker import ScannerWorker, SESSION_FILE
from app.services.universe_manager import UniverseManager
from app.services.paper_trader import paper_trader
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import recommend_strike


@pytest.fixture(autouse=True)
def reset_paper_trader():
    paper_trader.reset()
    yield
    paper_trader.reset()


@pytest.mark.asyncio
async def test_incoming_option_tick_triggers_paper_exit_instantaneously():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    # Open paper position
    rec = recommend_strike("BANK NIFTY", 50000.0, "CE", 49900.0)
    rec.option_security_id = "99881"
    rec.estimated_option_entry = 100.0
    rec.is_live_quote = True
    rec.real_ask_price = 100.0
    rec.option_sl_price = 90.0
    rec.option_target_1_price = 115.0

    sig = Signal(
        id="ws_test_sig",
        symbol="BANK NIFTY",
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type="CE",
        timestamp="10:00:00",
        entry_price=50000.0,
        stop_loss=49900.0,
        target_1=rec.target_1,
        target_2=rec.target_2,
        strike_recommendation=rec,
        indicators_snapshot={},
        rationale="WS test"
    )
    pos = paper_trader.open_position_from_signal(sig, lots=2, feed_mode="live")
    assert pos is not None

    # Simulate sub-second tick arrival for option contract hitting Target 1 (116.0)
    await worker._handle_incoming_ws_tick({
        "security_id": 99881,
        "ltp": 116.0,
        "volume": 50000,
        "response_code": 2
    })

    assert pos.status == "TARGET_1"
    assert pos.booked_lots == 1
    assert pos.option_sl == 100.0

    # Simulate immediate pullback tick hitting Trailed SL (99.0)
    await worker._handle_incoming_ws_tick({
        "security_id": 99881,
        "ltp": 99.0,
        "volume": 51000,
        "response_code": 2
    })

    assert len(paper_trader.get_portfolio(mode="live").active_positions) == 0
    await worker.stop()


@pytest.mark.asyncio
async def test_incoming_spot_tick_updates_radar_and_broadcasts():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    q = worker.subscribe()

    # NIFTY 50 security_id is 13
    await worker._handle_incoming_ws_tick({
        "security_id": 13,
        "exchange_segment": 0,
        "ltp": 22600.5,
        "response_code": 2
    })

    # Check that listener received a broadcast event
    assert not q.empty()
    event = q.get_nowait()
    assert event.get("type") == "tick" or "security_id" in event or "radar" in event or "symbol" in event

    # Clean up
    worker.unsubscribe(q)
    await worker.stop()


@pytest.mark.asyncio
async def test_dynamic_subscription_and_fallback():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    # Verify ws_manager is initialized on worker
    assert hasattr(worker, "ws_manager")
    assert worker.ws_manager is not None
    assert worker.ws_manager.is_connected is False

    # When credentials set, ws_manager connects
    with patch.object(worker.ws_manager, "connect", new_callable=AsyncMock) as mock_connect, \
         patch.object(worker.ws_manager, "subscribe", new_callable=AsyncMock) as mock_subscribe:
        worker.set_session_credentials("TEST_CLIENT", "TEST_TOKEN")
        # Allow any background connection tasks to fire
        await asyncio.sleep(0.01)
        mock_connect.assert_called_once_with("TEST_CLIENT", "TEST_TOKEN")

    await worker.stop()


@pytest.mark.asyncio
async def test_position_opening_triggers_dynamic_option_subscription():
    worker = ScannerWorker(universe_mgr=UniverseManager())

    with patch.object(worker.ws_manager, "subscribe", new_callable=AsyncMock) as mock_sub:
        rec = recommend_strike("NIFTY 50", 22500.0, "CE", 22400.0)
        rec.option_security_id = "88771"
        rec.estimated_option_entry = 80.0
        rec.is_live_quote = True
        rec.real_ask_price = 80.0
        rec.option_sl_price = 70.0
        rec.option_target_1_price = 95.0

        sig = Signal(
            id="ws_dyn_sub_sig",
            symbol="NIFTY 50",
            timeframe="5m",
            setup_type=SetupType.SETUP_1_SQUEEZE,
            option_type="CE",
            timestamp="10:00:00",
            entry_price=22500.0,
            stop_loss=22400.0,
            target_1=rec.target_1,
            target_2=rec.target_2,
            strike_recommendation=rec,
            indicators_snapshot={},
            rationale="Dynamic sub test"
        )
        pos = paper_trader.open_position_from_signal(sig, lots=2, feed_mode="live")
        assert pos is not None

        # Give async task time to execute callback
        await asyncio.sleep(0.02)
        mock_sub.assert_called_with([(2, 88771)])

    await worker.stop()


@pytest.mark.asyncio
async def test_scanner_fallback_to_http_when_ws_disconnected():
    mock_dhan = MagicMock()
    mock_dhan.fetch_marketfeed_quotes = AsyncMock(return_value={
        "NSE_EQ": {"1333": {"last_price": 1600.0, "volume": 1000}}
    })
    mock_dhan.fetch_expiry_list = AsyncMock(return_value=["2026-10-15"])
    mock_dhan.fetch_option_chain = AsyncMock(return_value={})
    mock_dhan.close = AsyncMock()

    worker = ScannerWorker(universe_mgr=UniverseManager(), dhan_client=mock_dhan)
    worker._session_credentials = ("TEST_CID", "TEST_TOKEN")
    assert worker.ws_manager.is_connected is False

    # Scanning executes without stalling and uses HTTP quotes
    state = await worker.run_single_scan_cycle()
    assert state.is_scanning is False
    assert mock_dhan.fetch_marketfeed_quotes.called

    await worker.stop()


@pytest.mark.asyncio
async def test_zero_token_persistence_remediation():
    worker = ScannerWorker(universe_mgr=UniverseManager())

    # Ensure any preexisting file is removed
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    worker.set_session_credentials("TEST_CID_SAFE", "TEST_TOKEN_SAFE")
    # File must NOT be created on disk
    assert not SESSION_FILE.exists()
    # Credentials must be in memory
    assert worker._session_credentials == ("TEST_CID_SAFE", "TEST_TOKEN_SAFE")

    # Clear credentials
    worker.set_session_credentials(None, None)
    assert worker._session_credentials is None
    assert not SESSION_FILE.exists()

    await worker.stop()


@pytest.mark.asyncio
async def test_sse_stream_formats_tick_as_named_event_and_snapshot_as_data():
    from app.api.signals import stream_signals
    import json

    worker = ScannerWorker(universe_mgr=UniverseManager())

    # Patch the global worker in app.main with our worker for the test
    with patch("app.main.worker", worker):
        req = MagicMock()
        async def is_disc():
            return False
        req.is_disconnected = is_disc

        resp = await stream_signals(req, max_events=3)
        gen = resp.body_iterator

        # 1. Initial snapshot emitted as standard data: ...\n\n (no event: tick)
        first_event = await anext(gen)
        assert first_event.startswith("data:")
        assert "event: tick" not in first_event
        snapshot = json.loads(first_event.replace("data:", "").strip())
        assert "active_mode" in snapshot

        # 2. Tick broadcast emitted as named event: tick\ndata: ...\n\n
        await worker.broadcast({
            "type": "tick",
            "security_id": 13,
            "ltp": 22550.0,
            "volume": 12000,
        })
        second_event = await anext(gen)
        assert second_event.startswith("event: tick\ndata:")
        parsed_tick = json.loads(second_event.replace("event: tick\ndata:", "").strip())
        assert parsed_tick["type"] == "tick"
        assert parsed_tick["ltp"] == 22550.0

        # 3. Regular state update broadcast emitted as standard data: ...\n\n
        await worker.broadcast({
            "active_mode": "live",
            "signals": [],
            "scan_cycle_count": 5
        })
        third_event = await anext(gen)
        assert third_event.startswith("data:")
        assert "event: tick" not in third_event

    await worker.stop()


@pytest.mark.asyncio
async def test_worker_stop_and_logout_disconnect_during_reconnecting_state():
    worker = ScannerWorker(universe_mgr=UniverseManager())

    # Simulate WebSocket in RECONNECTING status (where is_connected is False)
    worker.ws_manager.status = "RECONNECTING"
    assert worker.ws_manager.is_connected is False

    with patch.object(worker.ws_manager, "disconnect", new_callable=AsyncMock) as mock_disc:
        # Logging out with credentials=None must trigger disconnect
        worker.set_session_credentials(None, None)
        await asyncio.sleep(0.01)
        assert mock_disc.called

    # Reset and test stop() also unconditionally disconnects
    worker.ws_manager.status = "CONNECTING"
    assert worker.ws_manager.is_connected is False
    with patch.object(worker.ws_manager, "disconnect", new_callable=AsyncMock) as mock_disc:
        await worker.stop()
        assert mock_disc.called
