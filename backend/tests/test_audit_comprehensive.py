import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app, worker
from app.services.paper_trader import PaperTradingEngine, PaperPosition
from app.services.paper_storage import PaperStorage
from app.services.strategy_engine import Signal, SetupType, evaluate_signals
from app.services.strike_selector import OptionStrikeRecommendation
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import Instrument
from app.services.indicators import calculate_indicators

client = TestClient(app)

def create_mock_signal(
    symbol="NIFTY 50",
    setup_type=SetupType.SETUP_6_PINBAR_SNAPBACK,
    option_type="CE",
    is_live_quote=True,
    option_security_id="12345",
    is_confirmed=True,
    real_ask=150.0,
    real_ltp=149.0
) -> Signal:
    rec = OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=22000.0,
        option_type=option_type,
        atm_strike=22000,
        recommended_strike=22000,
        strike_symbol=f"{symbol} 22000 {option_type}",
        lot_size=50,
        risk=50.0,
        stop_loss=21950.0,
        target_1=22050.0,
        target_2=22100.0,
        estimated_option_entry=150.0,
        option_sl_pts=25.0,
        option_target_1_pts=25.0,
        option_target_2_pts=50.0,
        option_sl_price=125.0,
        option_target_1_price=175.0,
        option_target_2_price=200.0,
        option_security_id=option_security_id,
        is_live_quote=is_live_quote,
        real_ask_price=real_ask,
        real_bid_price=148.0,
        real_ltp=real_ltp,
    )
    return Signal(
        id=f"TEST_{symbol}_{setup_type}_{datetime.now().timestamp()}",
        symbol=symbol,
        timeframe="5m",
        setup_type=setup_type,
        option_type=option_type,
        timestamp="2026-10-10 10:00:00",
        entry_price=22000.0,
        stop_loss=21950.0,
        target_1=22050.0,
        target_2=22100.0,
        strike_recommendation=rec,
        indicators_snapshot={"close": 22000.0},
        rationale="Test signal",
        is_confirmed=is_confirmed,
    )

def test_h1_live_trades_require_resolved_contract_and_live_quote():
    engine = PaperTradingEngine()
    
    # 1. Missing option_security_id in live mode -> Rejected
    sig_no_sec_id = create_mock_signal(option_security_id="", is_live_quote=True)
    pos1 = engine.open_position_from_signal(sig_no_sec_id, feed_mode="live")
    assert pos1 is None

    # 2. is_live_quote is False and no real ask/ltp -> Rejected
    sig_no_quote = create_mock_signal(option_security_id="12345", is_live_quote=False, real_ask=0.0, real_ltp=0.0)
    pos2 = engine.open_position_from_signal(sig_no_quote, feed_mode="live")
    assert pos2 is None

    # 3. Valid contract and quote in live mode -> Accepted
    sig_valid = create_mock_signal(option_security_id="12345", is_live_quote=True, real_ask=150.0)
    pos3 = engine.open_position_from_signal(sig_valid, feed_mode="live")
    assert pos3 is not None
    assert pos3.option_security_id == "12345"
    assert pos3.feed_mode == "live"

from app.services.universe_manager import UniverseManager
from app.services.dhan_client import DhanClient
from app.services.momentum_ranker import MomentumRanker

def get_test_worker():
    return ScannerWorker(
        universe_mgr=UniverseManager(),
        dhan_client=DhanClient()
    )

def test_h2_ws_live_scanning_preserves_forming_candle():
    worker = get_test_worker()
    worker._state.active_mode = "live"
    inst = Instrument(
        symbol="NIFTY 50",
        name="Nifty 50",
        security_id="13",
        exchange_segment="IDX_I",
        instrument_type="INDEX",
        default_timeframe="5m",
        sector="Benchmark"
    )
    # Simulate a tick arriving via WS to form a candle
    worker._current_forming_candle["NIFTY 50"] = {
        "timestamp": datetime.now(),
        "open": 22100.0,
        "high": 22150.0,
        "low": 22090.0,
        "close": 22120.0,
        "volume": 5000,
    }
    
    # When inst_quote is None in live mode, forming candle is NOT dropped
    df = worker.get_or_update_live_candles(inst, inst_quote=None)
    assert not df.empty
    assert len(df) == 1
    assert df.iloc[-1]["close"] == 22120.0

def test_h3_target_1_pending_without_fresh_quote():
    engine = PaperTradingEngine()
    sig = create_mock_signal(option_type="CE")
    pos = engine.open_position_from_signal(sig, lots=2, feed_mode="live")
    assert pos is not None
    assert pos.status == "OPEN"

    # Spot hits target 1 (22050), but no fresh option quote (feed_mode live)
    engine.update_market_prices(
        price_map={"NIFTY 50": 22060.0},
        option_price_map=None,
        feed_mode="live"
    )
    assert pos.status == "OPEN"
    assert pos.pending_spot_tp1 is True
    assert pos.lots == 2  # Not yet sold at stale price

    # Now fresh quote arrives
    engine.update_market_prices(
        price_map={"NIFTY 50": 22060.0},
        option_price_map={"12345": 178.0},
        feed_mode="live",
        option_bid_map={"12345": 177.5}
    )
    assert pos.status == "TARGET_1"
    assert pos.pending_spot_tp1 is False
    assert pos.lots == 1  # 1 lot booked at fresh bid!
    assert pos.booked_lots == 1
    assert pos.booked_slippage_cost >= 0.0

@pytest.mark.asyncio
async def test_h4_seed_historical_candles_if_needed():
    worker = get_test_worker()
    inst = Instrument(
        symbol="TCS",
        name="Tata Consultancy Services",
        security_id="11536",
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        default_timeframe="5m",
        sector="IT"
    )
    mock_df = pd.DataFrame([
        {
            "timestamp": datetime.now() - timedelta(minutes=5 * i),
            "open": 3500.0,
            "high": 3510.0,
            "low": 3495.0,
            "close": 3505.0,
            "volume": 1000
        }
        for i in range(25)
    ])
    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_df
        success = await worker.seed_historical_candles_if_needed("CID123", "TOKEN123", inst)
        assert success is True
        assert len(worker._candle_history["TCS"]) == 25

def test_m1_sqlite_storage_pending_exits_and_slippage(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    storage = PaperStorage(db_path=db_path)
    engine = PaperTradingEngine(db_path=db_path)
    
    sig = create_mock_signal()
    pos = engine.open_position_from_signal(sig, feed_mode="live")
    pos.booked_slippage_cost = 45.5
    pos.pending_spot_exit = "Stop-Loss Hit"
    pos.pending_spot_tp1 = True
    storage.upsert_position(pos)

    # Load in new storage instance
    storage2 = PaperStorage(db_path=db_path)
    active, _ = storage2.load_all_positions()
    assert len(active) == 1
    loaded = active[0]
    assert loaded.booked_slippage_cost == 45.5
    assert loaded.pending_spot_exit == "Stop-Loss Hit"
    assert loaded.pending_spot_tp1 is True

def test_m2_manual_trade_guards_provisional_signal():
    # Signal with is_confirmed=False should be rejected on /trade in live mode
    sig = create_mock_signal(is_confirmed=False)
    res = client.post("/api/paper/trade", json={
        "signal": sig.model_dump(),
        "lots": 1,
        "feed_mode": "live"
    })
    assert res.status_code == 400
    assert "unconfirmed provisional" in res.json()["detail"]

def test_m4_orb_suppressed_when_window_missing():
    # DataFrame that begins at 12:00 PM (no 09:15-09:30 AM data)
    records = []
    base_t = datetime(2026, 10, 10, 12, 0)
    for i in range(25):
        records.append({
            "timestamp": base_t + timedelta(minutes=5 * i),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 2000
        })
    df = pd.DataFrame(records)
    ind_df = calculate_indicators(df)
    assert pd.isna(ind_df.iloc[-1]["or_high"])
    assert pd.isna(ind_df.iloc[-1]["or_low"])

    signals = evaluate_signals("NIFTY 50", ind_df, timeframe="5m")
    s4_signals = [s for s in signals if s.setup_type == SetupType.SETUP_4_ORB]
    assert len(s4_signals) == 0

def test_m5_manual_close_modeled_label():
    engine = PaperTradingEngine()
    sig = create_mock_signal(option_type="CE")
    pos = engine.open_position_from_signal(sig, feed_mode="live")
    
    # Close without real bid or real opt price
    closed = engine.close_position(pos.id, reason="Manual User Exit")
    assert closed is not None
    assert "Modeled: Last Price" in closed.exit_reason
