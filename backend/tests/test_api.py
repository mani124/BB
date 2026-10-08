import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app, worker
from app.core.config import settings
from app.api.signals import stream_signals
from app.api import signals
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import recommend_strike

client = TestClient(app)

def create_test_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0) -> Signal:
    rec = recommend_strike(symbol, entry, opt, sl)
    return Signal(
        id=f"test_sig_{symbol}_{opt}_{int(entry)}",
        symbol=symbol,
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type=opt,
        timestamp="09:30:00",
        entry_price=entry,
        stop_loss=sl,
        target_1=rec.target_1,
        target_2=rec.target_2,
        strike_recommendation=rec,
        indicators_snapshot={"rsi": 55.0, "bandwidth": 3.2},
        rationale="Bollinger Band Squeeze Breakout CE"
    )

def test_api_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == settings.APP_NAME
    assert data["version"] == settings.VERSION
    assert data["active_mode"] in ["demo", "live"]

def test_api_universe():
    response = client.get("/api/universe")
    assert response.status_code == 200
    data = response.json()
    assert "indices" in data
    assert "stocks" in data
    assert len(data["indices"]) == 4
    assert len(data["stocks"]) == 35
    assert data["total_count"] == 39

    idx_symbols = [i["symbol"] for i in data["indices"]]
    assert "NIFTY 50" in idx_symbols
    assert "NIFTY BANK" in idx_symbols
    assert "FINNIFTY" in idx_symbols
    assert "SENSEX" in idx_symbols

    stock_symbols = [s["symbol"] for s in data["stocks"]]
    assert "RELIANCE" in stock_symbols
    assert "TCS" in stock_symbols
    assert "INFY" in stock_symbols
    assert "HDFCBANK" in stock_symbols

def test_api_auth_verify_missing_headers():
    response = client.post("/api/auth/verify")
    assert response.status_code == 401
    assert "Missing Dhan authentication headers" in response.json()["detail"]

def test_api_auth_verify_success():
    with patch("app.api.auth.dhan_client.verify_credentials", new_callable=AsyncMock) as mock_verify:
        with patch.object(worker, "run_single_scan_cycle", new_callable=AsyncMock) as mock_scan:
            mock_verify.return_value = {"valid": True, "data": {"userName": "Test Trader"}}
            mock_scan.return_value = worker.get_state()

            headers = {
                "X-Dhan-Client-Id": "1000000001",
                "X-Dhan-Access-Token": "test_access_token_jwt_12345"
            }
            response = client.post("/api/auth/verify", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["client_id"] == "1000000001"
            assert data["token_masked"] == "tes...2345"
            assert data["error"] is None
            assert worker.get_state().active_mode == "live"

def test_api_auth_verify_invalid_credentials():
    with patch("app.api.auth.dhan_client.verify_credentials", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {"valid": False, "error": "Invalid or expired Dhan Access Token"}
        headers = {
            "X-Dhan-Client-Id": "1000000001",
            "X-Dhan-Access-Token": "bad_token"
        }
        response = client.post("/api/auth/verify", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] == "Invalid or expired Dhan Access Token"

def test_api_auth_disconnect():
    worker.set_session_credentials("1000000001", "live_token")
    assert worker.get_state().active_mode == "live"

    response = client.post("/api/auth/disconnect")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disconnected"
    assert data["mode"] == "demo"
    assert worker.get_state().active_mode == "demo"
    assert worker._session_credentials is None

def test_api_signals_snapshot():
    response = client.get("/api/signals")
    assert response.status_code == 200
    data = response.json()
    assert "signals" in data
    assert "radar" in data
    assert "scan_cycle_count" in data
    assert "active_mode" in data
    assert "universe_count" in data
    assert "is_scanning" in data

def test_api_signals_scan_now():
    response = client.post("/api/signals/scan-now")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "scan_complete"
    assert "signals_found" in data
    assert "cycle" in data
    assert data["cycle"] >= 1

def test_api_paper_portfolio():
    client.post("/api/paper/reset")
    response = client.get("/api/paper/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert data["total_pnl"] == 0.0
    assert data["total_realized_pnl"] == 0.0
    assert data["total_unrealized_pnl"] == 0.0
    assert data["win_rate_pct"] == 0.0
    assert data["total_trades_count"] == 0
    assert len(data["active_positions"]) == 0
    assert len(data["closed_trades"]) == 0

def test_api_paper_trade_open_and_duplicate_prevention():
    client.post("/api/paper/reset")
    sig = create_test_signal(symbol="NIFTY 50", opt="CE")
    body = {"signal": sig.model_dump(), "lots": 2}

    response = client.post("/api/paper/trade", json=body)
    assert response.status_code == 200
    pos = response.json()
    assert pos["symbol"] == "NIFTY 50"
    assert pos["lots"] == 2
    assert pos["status"] == "OPEN"
    assert pos["quantity"] == 65 * 2

    # Duplicate trade on same signal must fail with 400
    dup_resp = client.post("/api/paper/trade", json=body)
    assert dup_resp.status_code == 400
    assert "Position already exists" in dup_resp.json()["detail"]

def test_api_paper_close_trade_and_not_found():
    client.post("/api/paper/reset")
    sig = create_test_signal(symbol="RELIANCE", opt="PE", entry=2800.0, sl=2820.0)
    res = client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    assert res.status_code == 200
    pos = res.json()
    pos_id = pos["id"]

    # Close existing trade
    close_res = client.post(f"/api/paper/close/{pos_id}")
    assert close_res.status_code == 200
    closed_pos = close_res.json()
    assert closed_pos["id"] == pos_id
    assert closed_pos["status"] == "CLOSED"
    assert closed_pos["exit_reason"] == "Manual User Exit"

    # Close nonexistent trade
    bad_close = client.post("/api/paper/close/invalid_pos_999")
    assert bad_close.status_code == 404
    assert "Position not found" in bad_close.json()["detail"]

def test_api_paper_settings():
    response = client.post("/api/paper/settings", json={"auto_trade_enabled": True, "default_lots": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["auto_trade_enabled"] is True
    assert data["default_lots"] == 3

    # Reset back to false / 1
    client.post("/api/paper/settings", json={"auto_trade_enabled": False, "default_lots": 1})

def test_api_paper_reset():
    sig = create_test_signal(symbol="TCS", opt="CE")
    client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    port_before = client.get("/api/paper/portfolio").json()
    assert len(port_before["active_positions"]) == 1

    reset_res = client.post("/api/paper/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "portfolio_reset"

    port_after = client.get("/api/paper/portfolio").json()
    assert len(port_after["active_positions"]) == 0
    assert len(port_after["closed_trades"]) == 0

def test_api_signals_stream_http_endpoint():
    response = client.get("/api/signals/stream?max_events=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"

    content = response.text
    assert content.startswith("data:")
    raw_json = content.replace("data:", "").strip()
    data = json.loads(raw_json)
    assert "signals" in data
    assert "radar" in data
    assert "active_mode" in data

@pytest.mark.asyncio
async def test_api_signals_stream_generator_events_and_cleanup():
    req = MagicMock()
    async def is_disc():
        return False
    req.is_disconnected = is_disc

    listeners_start = len(worker._listeners)
    resp = await stream_signals(req)
    gen = resp.body_iterator
    assert len(worker._listeners) == listeners_start + 1

    # 1. Initial snapshot emitted
    first_chunk = await anext(gen)
    assert first_chunk.startswith("data:")
    snapshot = json.loads(first_chunk.replace("data:", "").strip())
    assert "active_mode" in snapshot

    # 2. Worker broadcast emitted and received
    await worker.broadcast({"active_mode": "demo", "signals": [], "broadcast_test": True})
    second_chunk = await anext(gen)
    assert second_chunk.startswith("data:")
    event_payload = json.loads(second_chunk.replace("data:", "").strip())
    assert event_payload.get("broadcast_test") is True

    # 3. Ping keepalive on timeout
    orig_ping = signals.SSE_PING_INTERVAL
    signals.SSE_PING_INTERVAL = 0.01
    try:
        ping_chunk = await anext(gen)
        assert ping_chunk == ": ping\n\n"
    finally:
        signals.SSE_PING_INTERVAL = orig_ping

    # 4. Clean unsubscription on generator close
    await gen.aclose()
    assert len(worker._listeners) == listeners_start

@pytest.mark.asyncio
async def test_api_signals_stream_disconnect_breaks_loop():
    req = MagicMock()
    # Simulate client already disconnected
    async def is_disc():
        return True
    req.is_disconnected = is_disc

    listeners_start = len(worker._listeners)
    resp = await stream_signals(req)
    gen = resp.body_iterator

    # First event is initial snapshot
    first_chunk = await anext(gen)
    assert first_chunk.startswith("data:")

    # Next iteration detects disconnect and terminates generator cleanly
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    assert len(worker._listeners) == listeners_start
