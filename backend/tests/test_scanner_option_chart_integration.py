import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import UniverseManager
from app.services.strategy_engine import SetupType
from app.services.indicators import calculate_indicators
from tests.test_option_chart_strategy import create_option_candles

@pytest.mark.asyncio
async def test_scanner_worker_evaluates_setup_5_from_live_option_candles():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)
    worker.set_session_credentials("10001", "test_tok")

    # Mock DhanClient methods
    # 1. Marketfeed quotes
    fake_quotes = {
        "NSE_EQ": {"1333": {"last_price": 22500.0, "ohlc": {"open": 22400.0, "high": 22550.0, "low": 22350.0, "close": 22500.0}, "volume": 500000}},
        "IDX_I": {"13": {"last_price": 22500.0, "ohlc": {"open": 22400.0, "high": 22550.0, "low": 22350.0, "close": 22500.0}, "volume": 1000000}}
    }
    worker.dhan_client.fetch_marketfeed_quotes = AsyncMock(return_value=fake_quotes)

    # 2. Expiry list and option chain
    worker.dhan_client.fetch_expiry_list = AsyncMock(return_value=["2026-10-15"])
    mock_oc = {
        "22500.000000": {
            "ce": {
                "strike_price": 22500.0,
                "security_id": 44612,
                "last_price": 115.0,
                "best_ask_price": 115.5,
                "best_bid_price": 114.5
            },
            "pe": {
                "strike_price": 22500.0,
                "security_id": 44613,
                "last_price": 95.0,
                "best_ask_price": 95.5,
                "best_bid_price": 94.5
            }
        }
    }
    worker.dhan_client.fetch_option_chain = AsyncMock(return_value=mock_oc)

    # 3. Option candles: 30 candles with candle 30 breaking out above Option Upper BB
    opt_candles = create_option_candles(n=30, base_premium=100.0)
    opt_candles.loc[29] = {
        "timestamp": datetime(2026, 10, 9, 12, 30),
        "open": 101.0,
        "high": 116.0,
        "low": 100.5,
        "close": 115.0,
        "volume": 50000
    }
    
    # Return valid candles for option security ID
    worker.dhan_client.fetch_intraday_candles = AsyncMock(return_value=opt_candles)

    # Run single scan cycle
    state = await worker.run_single_scan_cycle("10001", "test_tok")

    # Verify Setup 5 is detected and present in signals
    s5_signals = [s for s in state.signals if s.setup_type == SetupType.SETUP_5_OPTION_BB]
    assert len(s5_signals) >= 1, "ScannerWorker should surface Setup 5 Option Chart BB signals"
    sig = s5_signals[0]
    assert sig.entry_price == 115.0
    assert sig.strike_recommendation.underlying_price == 22500.0
    assert sig.strike_recommendation.estimated_option_entry == 115.0
    assert sig.setup_type == SetupType.SETUP_5_OPTION_BB
