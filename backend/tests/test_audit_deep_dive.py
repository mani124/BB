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
    """Finding 7: State-changing local API routes reject cross-origin requests from foreign origins."""
    headers = {"Origin": "http://malicious-site.com"}
    res = client.post("/api/paper/reset", headers=headers)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # Allowed local origin succeeds
    local_headers = {"Origin": "http://localhost:5174"}
    res_ok = client.post("/api/paper/reset", headers=local_headers)
    assert res_ok.status_code == 200


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

    # Evaluate scan cycle in live mode with a mock
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf:
        mock_mf.return_value = {
            inst.exchange_segment: {
                str(inst.security_id): {"last_price": 22100.0, "volume": 50000}
            }
        }
        # Run scan
        state = asyncio.run(worker._execute_scan_cycle(client_id="CID", access_token="TOK"))
        # Any signal generated on yesterday's bars must NOT be confirmed
        for s in state.signals:
            if s.symbol == inst.symbol:
                s_dt = pd.to_datetime(s.timestamp)
                if s_dt.date() < datetime.now().date():
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

    # Execute scan cycle
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf:
        mock_mf.return_value = {
            inst.exchange_segment: {
                str(inst.security_id): {"last_price": 22500.0, "volume": 1000}
            }
        }
        state = asyncio.run(worker._execute_scan_cycle(client_id="CID", access_token="TOK"))
        for s in state.signals:
            if s.symbol == inst.symbol:
                assert s.is_confirmed is False, f"Forming candle signal {s.id} must be provisional in live mode"


def test_finding_4_missing_quote_omitted_from_price_map_in_live_mode():
    """Finding 4: When an instrument is not quoted in live mode, it is omitted from trade price_map."""
    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    # Pre-populate historical candles
    now = datetime.now()
    worker._candle_history[inst.symbol] = [{
        "timestamp": now - timedelta(minutes=5 * i),
        "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 1000
    } for i in range(25)]

    # Mock marketfeed returning EMPTY quotes for this instrument
    worker.set_session_credentials("CID", "TOK")
    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", new_callable=AsyncMock) as mock_mf, \
         patch.object(paper_trader, "update_market_prices") as mock_update:
        mock_mf.return_value = {}
        asyncio.run(worker._execute_scan_cycle())
        # Check what was passed to paper_trader.update_market_prices
        called_args = mock_update.call_args
        assert called_args is not None
        called_price_map = called_args[0][0] if called_args.args else called_args.kwargs.get("price_map", {})
        assert inst.symbol not in called_price_map, f"Stale {inst.symbol} was erroneously included in live trade price_map"


def test_finding_5_manual_live_entry_rejects_forged_signal():
    """Finding 5: Manual live entry rejects forged signal not found in server radar."""
    client.post("/api/paper/reset")
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
    engine.reset()
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
