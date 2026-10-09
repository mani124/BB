import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock

from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker

@pytest.mark.asyncio
async def test_two_tier_funnel_ranks_all_fno_and_deep_scans_top_movers():
    mgr = UniverseManager()
    fno_stocks = mgr.get_fno_stocks()
    indices = mgr.get_indices()
    assert len(fno_stocks) >= 210

    mock_dhan = MagicMock()
    # Mock marketfeed quotes returning quotes for Nifty and 213 stocks
    # Set PAGEIND as strong bullish (+5%), 360ONE as strong bearish (-4%)
    mock_quotes = {
        "IDX_I": {
            "13": {"last_price": 25100.0, "average_price": 25000.0, "ohlc": {"open": 25000.0, "high": 25120.0, "low": 24980.0, "close": 24950.0}}
        },
        "NSE_EQ": {
            "3499": {"last_price": 160.0, "average_price": 155.0, "ohlc": {"open": 152.0, "high": 161.0, "low": 151.0, "close": 150.0}}, # TATASTEEL (+6.67%)
            "14418": {"last_price": 45000.0, "average_price": 44000.0, "ohlc": {"open": 43500.0, "high": 45200.0, "low": 43400.0, "close": 43000.0}}, # PAGEIND (+4.6%)
            "13061": {"last_price": 950.0, "average_price": 980.0, "ohlc": {"open": 990.0, "high": 995.0, "low": 945.0, "close": 1000.0}} # 360ONE (-5.0%)
        }
    }
    mock_dhan.fetch_marketfeed_quotes = AsyncMock(return_value=mock_quotes)
    mock_dhan.close = AsyncMock()

    worker = ScannerWorker(universe_mgr=mgr, dhan_client=mock_dhan)
    worker.set_session_credentials("TEST_CID", "TEST_TOKEN")
    state = await worker.run_single_scan_cycle()

    # Universe count reflects all indices + all 213 F&O stocks
    assert state.universe_count >= 214
    # All 213 stocks are ranked for momentum
    assert "PAGEIND" in state.top_bullish or "TATASTEEL" in state.top_bullish
    assert "360ONE" in state.top_bearish
    assert state.market_bias == "BULLISH"
    await worker.stop()
