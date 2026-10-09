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
