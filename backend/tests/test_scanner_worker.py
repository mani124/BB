import pytest
import asyncio
import pandas as pd
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker, IndexRadarItem
from app.services.paper_trader import paper_trader

def test_universe_manager_curation():
    mgr = UniverseManager()
    indices = mgr.get_indices()
    stocks = mgr.get_momentum_stocks()
    all_inst = mgr.get_all_instruments()
    universe = mgr.get_universe()

    assert len(indices) == 4
    assert any(i.symbol == "NIFTY 50" for i in indices)
    assert any(i.symbol == "NIFTY BANK" for i in indices)
    assert any(i.symbol == "FINNIFTY" for i in indices)
    assert any(i.symbol == "SENSEX" for i in indices)
    assert len(stocks) == 35
    assert len(all_inst) >= 214
    assert len(universe) >= 214
    # Verify timeframes: stocks unified to 5m for responsive momentum scalps
    assert all(i.default_timeframe == "5m" for i in indices)
    assert all(s.default_timeframe == "5m" for s in stocks)

@pytest.mark.asyncio
async def test_scanner_worker_demo_cycle():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker._session_credentials = None
    worker._state.active_mode = "demo"
    # Execute one full scan cycle in demo/synthetic mode
    state = await worker.run_single_scan_cycle(client_id=None, access_token=None)

    assert state.scan_cycle_count >= 1
    assert state.universe_count >= 214
    assert len(state.radar) == 4
    assert "NIFTY 50" in state.radar
    assert "NIFTY BANK" in state.radar
    assert "FINNIFTY" in state.radar
    assert "SENSEX" in state.radar
    assert isinstance(state.signals, list)
    assert state.scan_progress == 100.0
    assert state.active_mode == "demo"
    assert worker.get_latest_state() == state
    await worker.stop()

@pytest.mark.asyncio
async def test_scanner_worker_radar_metrics():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    state = await worker.run_single_scan_cycle()

    for sym in ["NIFTY 50", "NIFTY BANK", "FINNIFTY", "SENSEX"]:
        radar_item = state.radar[sym]
        assert isinstance(radar_item, IndexRadarItem)
        assert radar_item.symbol == sym
        assert radar_item.close > 0
        assert isinstance(radar_item.change_pct, float)
        assert isinstance(radar_item.bandwidth, float)
        assert isinstance(radar_item.percent_b, float)
        assert isinstance(radar_item.is_squeeze, bool)
        assert radar_item.vwap_bias in ["ABOVE_VWAP", "BELOW_VWAP"]
        assert radar_item.trend_state in ["BULLISH_WALK", "BEARISH_WALK", "SQUEEZE", "RANGE"]
    await worker.stop()

@pytest.mark.asyncio
async def test_scanner_worker_subscribe_broadcast_unsubscribe():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    queue = worker.subscribe()
    assert queue in worker._listeners

    payload = {"test_event": "ping"}
    await worker.broadcast(payload)
    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg == payload

    worker.unsubscribe(queue)
    assert queue not in worker._listeners
    await worker.stop()

@pytest.mark.asyncio
async def test_scanner_worker_paper_trading_integration():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    state = await worker.run_single_scan_cycle()
    portfolio = state.paper_portfolio
    assert portfolio is not None
    assert isinstance(portfolio.active_positions, list)
    await worker.stop()

@pytest.mark.asyncio
async def test_scanner_worker_session_credentials_and_live_mode():
    mock_dhan = MagicMock()
    # Mock return dummy candles so it doesn't fail
    dummy_df = pd.DataFrame({
        "timestamp": pd.date_range("2026-10-08 09:15", periods=25, freq="5min"),
        "open": [25000.0 + i for i in range(25)],
        "high": [25010.0 + i for i in range(25)],
        "low": [24990.0 + i for i in range(25)],
        "close": [25005.0 + i for i in range(25)],
        "volume": [1000] * 25
    })
    mock_dhan.fetch_marketfeed_quotes = AsyncMock(return_value={
        "IDX_I": {"13": {"last_price": 22500.0, "ohlc": {"open": 22400.0, "high": 22550.0, "low": 22350.0, "close": 22380.0}}}
    })
    mock_dhan.close = AsyncMock()

    worker = ScannerWorker(universe_mgr=UniverseManager(), dhan_client=mock_dhan)
    worker.set_session_credentials("TEST_CID", "TEST_TOKEN")
    state = await worker.run_single_scan_cycle()

    assert state.active_mode == "live"
    assert mock_dhan.fetch_marketfeed_quotes.called
    await worker.stop()

@pytest.mark.asyncio
async def test_scanner_worker_start_and_stop():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker.start()
    assert worker._running is True
    assert worker._task is not None
    # Wait briefly for background execution
    await asyncio.sleep(0.05)
    await worker.stop()
    assert worker._running is False
    assert worker._task is None

@pytest.mark.asyncio
async def test_scanner_worker_momentum_ranking_and_bias():
    mock_dhan = MagicMock()
    mock_dhan.fetch_marketfeed_quotes = AsyncMock(return_value={
        "IDX_I": {
            "13": {"last_price": 25100.0, "average_price": 25000.0, "ohlc": {"open": 25000.0, "high": 25120.0, "low": 24980.0, "close": 24950.0}} # Nifty > VWAP -> BULLISH
        },
        "NSE_EQ": {
            "3499": {"last_price": 160.0, "average_price": 155.0, "ohlc": {"open": 152.0, "high": 161.0, "low": 151.0, "close": 150.0}}, # TATASTEEL: +6.67%, high range pos -> BULLISH
            "2885": {"last_price": 2400.0, "average_price": 2450.0, "ohlc": {"open": 2450.0, "high": 2460.0, "low": 2390.0, "close": 2480.0}} # RELIANCE: -3.2%, low range pos -> BEARISH
        }
    })
    mock_dhan.close = AsyncMock()

    worker = ScannerWorker(universe_mgr=UniverseManager(), dhan_client=mock_dhan)
    worker.set_session_credentials("TEST_CID", "TEST_TOKEN")
    state = await worker.run_single_scan_cycle()

    assert state.market_bias == "BULLISH"
    assert "TATASTEEL" in state.top_bullish
    assert "RELIANCE" in state.top_bearish
    await worker.stop()

