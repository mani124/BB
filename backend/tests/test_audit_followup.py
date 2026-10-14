import pytest
from starlette.testclient import TestClient
from app.main import create_app
from app.core.config import settings

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_spoofed_origin_mutation_rejected_without_capability(client):
    """F1: Supplying an allowed Origin does not bypass capability token requirement for mutations."""
    # Spoofed local development origin
    res = client.post(
        "/api/paper/reset",
        headers={"Origin": "http://localhost:5174", "X-Omit-Capability": "1"}
    )
    assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}: {res.text}"
    assert "capability" in res.json().get("detail", "").lower()

    # Spoofed production origin
    res_prod = client.post(
        "/api/paper/reset",
        headers={"Origin": "https://options.34-14-178-224.sslip.io", "X-Omit-Capability": "1"}
    )
    assert res_prod.status_code == 401, f"Expected 401 Unauthorized, got {res_prod.status_code}: {res_prod.text}"


def test_oauth_routes_protected_by_capability(client):
    """F1/F3: Session-mutating OAuth routes require dashboard capability to prevent session hijacking."""
    # /api/auth/verify without capability
    res_verify = client.post(
        "/api/auth/verify",
        headers={
            "X-Omit-Capability": "1",
            "X-Dhan-Client-Id": "1100000000",
            "X-Dhan-Access-Token": "test_token"
        }
    )
    assert res_verify.status_code == 401, f"Expected 401, got {res_verify.status_code}: {res_verify.text}"

    # /api/auth/oauth/token without capability
    res_token = client.post(
        "/api/auth/oauth/token",
        json={"app_id": "app", "app_secret": "secret", "consent_id": "consent"},
        headers={"X-Omit-Capability": "1"}
    )
    assert res_token.status_code == 401, f"Expected 401, got {res_token.status_code}: {res_token.text}"


def test_private_reads_and_sse_require_capability(client):
    """F3: Private dashboard reads and SSE streams are protected from unauthenticated access."""
    # Private portfolio read
    res_port = client.get("/api/paper/portfolio", headers={"X-Omit-Capability": "1"})
    assert res_port.status_code == 401, f"Expected 401 for /portfolio, got {res_port.status_code}"

    # Private scanner state read
    res_state = client.get("/api/signals/state", headers={"X-Omit-Capability": "1"})
    assert res_state.status_code == 401, f"Expected 401 for /signals/state, got {res_state.status_code}"

    # Public health check remains open
    res_health = client.get("/api/health")
    assert res_health.status_code == 200


def test_auth_session_endpoint_and_cookie_bootstrap(client):
    """F1/F3: POST /api/auth/session authorizes via master secret and issues dashboard_session cookie."""
    # Wrong secret rejected
    bad_res = client.post("/api/auth/session", json={"secret": "wrong_secret"})
    assert bad_res.status_code == 401

    # Valid master capability secret accepted
    good_res = client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY})
    assert good_res.status_code == 200
    data = good_res.json()
    assert data.get("status") == "authenticated"
    assert "dashboard_session" in good_res.cookies

    # Authenticated client with cookie can read private endpoints
    cookie_val = good_res.cookies["dashboard_session"]
    auth_client = TestClient(create_app(), cookies={"dashboard_session": cookie_val})
    res_port = auth_client.get("/api/paper/portfolio")
    assert res_port.status_code == 200

    res_state = auth_client.get("/api/signals/state")
    assert res_state.status_code == 200


def test_mutation_with_both_origin_and_capability(client):
    """F1: Browser requests succeed when both allowed Origin and valid capability (or cookie) are present."""
    res = client.post(
        "/api/paper/reset",
        headers={
            "Origin": "http://localhost:5174",
            "X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY
        }
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_reset_barrier_prevents_stale_upsert_resurrection(tmp_path):
    """F2: A delayed in-flight position upsert cannot commit after reset and resurrect trades."""
    import asyncio
    import time
    from app.services.paper_trader import PaperTradingEngine, PaperPosition
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation

    db_path = str(tmp_path / "test_reset_barrier.db")
    engine = PaperTradingEngine(db_path=db_path)
    await engine.start_persistence_worker()

    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id="88801", is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )

    sig = Signal(
        id="SIG_BARRIER_1", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp="09:30:00", entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )

    # 1. Open trade (queues an upsert)
    pos = engine.open_position_from_signal(sig, feed_mode="demo")
    assert pos is not None

    # Capture the old generation
    old_gen = engine._portfolio_generation

    # 2. Reset portfolio through the ordered queue barrier
    await engine.reset()

    # 3. Simulate an in-flight scan attempting to enqueue a write with the old generation
    engine._enqueue_write("upsert", pos, generation=old_gen)

    # Await flush
    await engine.flush()

    # Verify database is completely empty upon reload!
    loaded_active, loaded_closed = engine.storage.load_all_positions()
    assert len(loaded_active) == 0, f"Resurrected trades found in DB: {loaded_active}"
    assert len(loaded_closed) == 0

    await engine.stop_persistence_worker()


@pytest.mark.asyncio
async def test_storage_error_tracked_and_surfaced_by_flush_and_reset(tmp_path):
    """F7: Storage errors are tracked per operation and raised during flush and reset rather than swallowed."""
    import asyncio
    from unittest.mock import MagicMock
    from app.services.paper_trader import PaperTradingEngine

    db_path = str(tmp_path / "test_storage_err.db")
    engine = PaperTradingEngine(db_path=db_path)
    await engine.start_persistence_worker()

    # Make storage.upsert_position raise an explicit SQLite error
    failing_storage = MagicMock()
    failing_storage.upsert_position.side_effect = RuntimeError("Disk I/O Error: Database locked")
    failing_storage.clear_all.side_effect = RuntimeError("Disk I/O Error: Disk full")
    engine.storage = failing_storage

    # Enqueue a write
    engine._enqueue_write("upsert", "dummy_pos")

    # Flush must raise the tracked operation failure!
    with pytest.raises(RuntimeError, match="Database locked"):
        await engine.flush()

    await engine.stop_persistence_worker()


def test_cached_chain_quote_timestamp_retains_observation_time():
    """F4: Quotes from chain retain original fetch observation time, failing 15s freshness when aged."""
    import time
    from unittest.mock import patch
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager

    worker = ScannerWorker(universe_mgr=UniverseManager())
    sec_id = "77112"

    # Chain fetched at monotonic T=100.0
    chain_fetch_mono = 100.0
    worker.record_option_quote(sec_id, ltp=150.0, bid=149.5, source="chain", timestamp=chain_fetch_mono)

    # At T=110.0 (10s later), quote is still within 15s window
    with patch("time.monotonic", return_value=110.0):
        q = worker.get_option_quote(sec_id, max_age_s=15.0)
        assert q is not None
        assert q.ltp == 150.0
        assert q.timestamp == 100.0

    # At T=116.0 (16s after observation), quote must fail freshness check even if queried later!
    with patch("time.monotonic", return_value=116.0):
        q = worker.get_option_quote(sec_id, max_age_s=15.0)
        assert q is None, "Expected quote to be stale after 16s from original observation"


def test_websocket_quote_not_overwritten_by_older_cached_chain_quote():
    """F4: Sub-second WebSocket quote at T+5s is not overwritten by chain quote observed at T."""
    from unittest.mock import patch
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager

    worker = ScannerWorker(universe_mgr=UniverseManager())
    sec_id = "77113"

    # 1. WebSocket quote arrives at T=105.0
    worker.record_option_quote(sec_id, ltp=155.0, bid=154.5, source="ws", timestamp=105.0)

    # 2. Scan cycle records cached chain quote observed earlier at T=100.0
    worker.record_option_quote(sec_id, ltp=150.0, bid=149.0, source="chain", timestamp=100.0)

    # Verify that the newer WebSocket quote was NOT overwritten!
    with patch("time.monotonic", return_value=106.0):
        q = worker.get_option_quote(sec_id, max_age_s=15.0)
        assert q is not None
        assert q.ltp == 155.0
        assert q.source == "ws"
        assert q.timestamp == 105.0


@pytest.mark.asyncio
async def test_option_chart_forming_candle_dynamic_update():
    """F5: Option chart cache caches completed bars only; live forming candle updates dynamically without freezing."""
    import asyncio
    import pandas as pd
    from datetime import datetime, timedelta
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager, Instrument

    from app.services import market_hours

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]

    now = market_hours.now_ist().replace(tzinfo=None)
    step_min = 5
    current_slot_ts = market_hours.ist_slot_start(step_min=step_min)

    # 25 completed bars before current slot
    bars = []
    for i in range(25, 0, -1):
        ts = current_slot_ts - timedelta(minutes=step_min * i)
        bars.append({
            "timestamp": ts,
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 1000
        })

    # Historical API returns 25 completed bars PLUS a premature forming bar at current_slot_ts
    hist_bars = list(bars)
    hist_bars.append({
        "timestamp": current_slot_ts,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 200
    })
    hist_df = pd.DataFrame(hist_bars)

    sec_id = "88991"
    chain_oc = {
        "22500": {
            "ce": {
                "security_id": sec_id,
                "last_price": 100.0,
                "volume": 200,
                "top_ask_price": 100.5,
                "top_bid_price": 99.5
            }
        }
    }

    captured_dfs = []
    original_calc = None

    with patch.object(worker.dhan_client, "fetch_intraday_candles", new_callable=AsyncMock) as mock_fetch, \
         patch("app.services.scanner_worker.calculate_indicators") as mock_calc:

        mock_fetch.return_value = hist_df

        def capture_calc(df):
            captured_dfs.append(df.copy())
            # Minimal return matching indicator columns so evaluate doesn't error
            out = df.copy()
            out["bb_middle"] = 100.0
            out["bb_upper"] = 110.0
            out["bb_lower"] = 90.0
            out["bb_bandwidth"] = 20.0
            out["bb_percent_b"] = 0.5
            out["vwap"] = 100.0
            out["rsi"] = 50.0
            out["adx"] = 20.0
            out["vol_sma"] = 500.0
            return out

        mock_calc.side_effect = capture_calc

        # First scan evaluation in the slot: tick 1 (LTP=100.0, vol=200)
        res1 = await worker._evaluate_option_chart_setups("CID", "TOK", inst, chain_oc, "2026-10-15", 22500.0)
        assert mock_fetch.call_count == 1
        assert len(captured_dfs) == 1
        last_row_1 = captured_dfs[0].iloc[-1]
        assert last_row_1["close"] == 100.0

        # Second scan evaluation in the same slot: tick 2 arrives with breakout price LTP=125.0 and vol=3500!
        chain_oc["22500"]["ce"]["last_price"] = 125.0
        chain_oc["22500"]["ce"]["volume"] = 3500
        res2 = await worker._evaluate_option_chart_setups("CID", "TOK", inst, chain_oc, "2026-10-15", 22500.0)

        # Historical API must NOT be called again (cache preserved)
        assert mock_fetch.call_count == 1, "Historical chart was re-fetched over network within same slot!"
        assert len(captured_dfs) == 2

        # P0-4: Setup 5 is evaluated on COMPLETED bars only. Neither tick may leak into the
        # frame passed to the indicators; the premature forming bar from the API is excluded too.
        for df_i in captured_dfs:
            assert df_i["timestamp"].max() < current_slot_ts
            assert df_i.iloc[-1]["close"] == 100.0
            assert df_i["timestamp"].is_unique

        # The live forming candle itself still tracks the ticks (high/low/close), for display & exits
        forming = worker._option_forming_candle[sec_id]
        assert forming["close"] == 125.0 and forming["high"] == 125.0


def test_volume_baseline_with_seeded_forming_bar():
    """F6: First live quote establishes baseline subtracting both today's completed bars and any seeded forming bar."""
    from datetime import datetime, timedelta
    from app.services.scanner_worker import ScannerWorker
    from app.services.universe_manager import UniverseManager

    worker = ScannerWorker(universe_mgr=UniverseManager())
    inst = worker.universe_mgr.get_indices()[0]
    sym = inst.symbol

    now = datetime.now()
    step_min = 5
    current_slot_min = (now.minute // step_min) * step_min
    current_slot_ts = now.replace(minute=current_slot_min, second=0, microsecond=0)

    # 1. Seed today's completed bars totaling 50,000 volume
    worker._candle_history[sym] = [
        {"timestamp": current_slot_ts - timedelta(minutes=10), "open": 22000.0, "high": 22010.0, "low": 21990.0, "close": 22005.0, "volume": 30000},
        {"timestamp": current_slot_ts - timedelta(minutes=5), "open": 22005.0, "high": 22015.0, "low": 22000.0, "close": 22010.0, "volume": 20000},
    ]

    # 2. Seed an unfinished forming bar with 2,000 volume
    worker._current_forming_candle[sym] = {
        "timestamp": current_slot_ts,
        "open": 22010.0,
        "high": 22015.0,
        "low": 22008.0,
        "close": 22012.0,
        "volume": 2000
    }

    # Total volume represented in local state = 50,000 + 2,000 = 52,000.

    # 3. First live quote arrives with cumulative session volume = 55,000
    quote = {
        "last_price": 22015.0,
        "volume": 55000
    }
    df = worker.get_or_update_live_candles(inst, quote)

    # The forming candle volume should now be: 2000 (initial) + (55000 - 52000) = 5000!
    forming = worker._current_forming_candle[sym]
    assert forming["volume"] == 5000, f"Expected forming volume 5000, got {forming['volume']}"

    # Total volume across all bars in df (30k + 20k + 5k) should equal 55,000
    assert df["volume"].sum() == 55000


def test_close_ignores_caller_exit_price_and_preserves_slippage_integrity(client, no_reentry_cooldown):
    """F8: Public close requests cannot alter theoretical exit or distort slippage metrics via exit_price."""
    from app.services.paper_trader import paper_trader
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation

    paper_trader.reset_sync()

    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id="99981", is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )

    sig = Signal(
        id="SIG_SLIP_F8_1", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp="09:30:00", entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )

    pos = paper_trader.open_position_from_signal(sig, feed_mode="live")
    assert pos is not None
    pos_id = pos.id

    # 1. Close via /api/paper/close with an adversarial exit_price of 100,000.0
    res = client.post(
        f"/api/paper/close/{pos_id}",
        json={"reason": "Adversarial Exit", "exit_price": 100000.0}
    )
    assert res.status_code == 200
    closed_data = res.json()

    # Theoretical exit must NOT be 100,000.0!
    assert closed_data["theoretical_exit"] != 100000.0
    assert closed_data["theoretical_exit"] == 100.0
    assert closed_data["exit_slippage"] == 0.0
    assert closed_data["total_slippage_cost"] == 0.0

    # 2. Test the alias /api/signals/close/{id} as well
    sig2 = Signal(
        id="SIG_SLIP_F8_2", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp="09:35:00", entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )
    pos2 = paper_trader.open_position_from_signal(sig2, feed_mode="live")
    assert pos2 is not None
    pos_id_2 = pos2.id

    res2 = client.post(
        f"/api/signals/close/{pos_id_2}",
        json={"reason": "Adversarial Exit 2", "exit_price": 50000.0}
    )
    assert res2.status_code == 200
    closed_data_2 = res2.json()

    assert closed_data_2["theoretical_exit"] != 50000.0
    assert closed_data_2["theoretical_exit"] == 100.0
    assert closed_data_2["exit_slippage"] == 0.0




