# Real-Time WebSockets Feed & Dhan OAuth 2.0 Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Dhan OAuth 2.0 1-click login and a sub-second Real-Time WebSocket Feed (`wss://api-feed.dhan.co`) with binary packet decoding, dynamic instrument subscription, automatic reconnection, and instant paper trading SL/target execution.

**Architecture:** A dedicated async `DhanWebSocketManager` maintains a persistent binary connection to Dhan HQ, decodes incoming 16-byte Ticker and 50-byte Quote packets, and dispatches sub-second price updates directly into the in-memory paper trading engine and SSE broadcast stream, with automatic HTTP polling fallback. An OAuth 2.0 consent route generates login URLs and exchanges authorization codes for 24-hour access tokens without persisting secrets to disk.

**Tech Stack:** Python 3.12+, FastAPI, `websockets`, `struct`, React 18, TypeScript, Tailwind CSS, Vite.

**Spec:** [`docs/superpowers/specs/2026-10-09-websocket-oauth-feed-design.md`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/docs/superpowers/specs/2026-10-09-websocket-oauth-feed-design.md)

## Global Constraints
- Working directory: `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`
- Zero-Token Persistence: Tokens and secrets stored exclusively in memory / `sessionStorage`, never written to disk or logs
- Backend Port: 8001 (bound to 127.0.0.1 by default)
- Frontend Port: 5174
- All 132 existing unit tests in `backend/tests/` must remain passing throughout implementation
- Frontend TypeScript build (`npm run build`) must pass cleanly with 0 errors

## Review Focus
1. Binary packet malformation or incomplete frame handling (must drop gracefully without crashing the socket loop)
2. WebSocket disconnection during volatile market hours (must seamlessly fail over to HTTP polling within 10s and reconnect with backoff)
3. 24-hour token expiry boundary (must provide countdown in UI and return 401 when expired without hanging connections)
4. Dynamic subscription scaling (must handle subscribing active paper contracts without exceeding Dhan 100-scrip packet boundaries)
5. Zero synthetic data in live WebSocket mode (only positive decoded market prices trigger paper trader updates)

---

### Task 1: Dhan OAuth 2.0 Login Endpoints & Token Exchange

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/tests/test_oauth_auth.py`

**Interfaces:**
- Produces: `GET /api/auth/oauth/login-url` returning `{"login_url": str}`
- Produces: `POST /api/auth/oauth/token` accepting `{"app_id": str, "app_secret": str, "consent_id": str}` returning `{"status": "connected", "client_id": str, "masked_token": str, "expires_in_hours": int}`

- [ ] **Step 1: Write failing tests for OAuth login URL and token exchange**

```python
# backend/tests/test_oauth_auth.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_oauth_login_url_generation():
    res = client.get("/api/auth/oauth/login-url?app_id=APP123&redirect_uri=http://localhost:5174/")
    assert res.status_code == 200
    data = res.json()
    assert "https://auth.dhan.co/login/consent" in data["login_url"]
    assert "client_id=APP123" in data["login_url"]

@pytest.mark.asyncio
async def test_oauth_token_exchange_success():
    mock_resp = {
        "status": "success",
        "data": {
            "dhanClientId": "1000000000",
            "accessToken": "eyJh...sample_token",
            "expiresIn": 86400
        }
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_resp
        res = client.post("/api/auth/oauth/token", json={
            "app_id": "APP123",
            "app_secret": "SEC456",
            "consent_id": "CONSENT789"
        })
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "connected"
        assert body["client_id"] == "1000000000"
        assert "accessToken" not in body  # Must not leak full raw token
        assert body["expires_in_hours"] == 24
```

- [ ] **Step 2: Run test to verify RED**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_oauth_auth.py -v`  
Expected: FAIL with 404 Not Found for `/api/auth/oauth/login-url`

- [ ] **Step 3: Implement OAuth endpoints in `backend/app/api/auth.py`**

Add `GET /oauth/login-url` and `POST /oauth/token` to `backend/app/api/auth.py`.

- [ ] **Step 4: Run test to verify GREEN**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_oauth_auth.py -v`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add backend/app/api/auth.py backend/tests/test_oauth_auth.py backend/app/core/config.py
git commit -m "feat: add Dhan OAuth 2.0 login URL and token exchange endpoints"
```

---

### Task 2: Binary Packet Serialization & Deserialization Engine

**Files:**
- Create: `backend/app/services/dhan_packet_codec.py`
- Create: `backend/tests/test_dhan_packet_codec.py`

**Interfaces:**
- Produces: `encode_login_packet(client_id: str, access_token: str) -> bytes`
- Produces: `encode_subscription_packet(instruments: list[tuple[int, int]], mode: int = 2) -> bytes`
- Produces: `decode_packet(raw_bytes: bytes) -> Optional[dict]` (returns dict with `response_code`, `security_id`, `ltp`, `volume`, `vwap`, etc.)

- [ ] **Step 1: Write failing tests for binary encoding and decoding**

```python
# backend/tests/test_dhan_packet_codec.py
import pytest
import struct
from app.services.dhan_packet_codec import (
    encode_login_packet,
    encode_subscription_packet,
    decode_packet
)

def test_encode_login_packet():
    packet = encode_login_packet("1000000000", "my_sample_access_token")
    assert len(packet) == 83
    req_code, msg_len = struct.unpack_from("<HH", packet, 0)
    assert req_code == 11
    assert msg_len == 83

def test_decode_ticker_packet_code_2():
    # 16-byte Ticker packet: Code 2, Len 16, Seg 1, SecId 1330, LTP 25050.25, LTT 1728500000
    dummy = struct.pack("<BBHiif", 2, 0, 16, 1330, 1728500000, 25050.25)
    parsed = decode_packet(dummy)
    assert parsed is not None
    assert parsed["response_code"] == 2
    assert parsed["security_id"] == 1330
    assert pytest.approx(parsed["ltp"], 0.01) == 25050.25

def test_decode_quote_packet_code_4():
    # 50-byte Quote packet: Code 4, Len 50, Seg 2, SecId 44608, LTP 160.5, VWAP 158.0, Vol 250000
    dummy = struct.pack("<BBHiififiiii", 4, 0, 50, 44608, 1728500000, 160.5, 100, 158.0, 250000, 150, 165, 148)
    parsed = decode_packet(dummy)
    assert parsed is not None
    assert parsed["response_code"] == 4
    assert parsed["security_id"] == 44608
    assert pytest.approx(parsed["ltp"], 0.01) == 160.5
    assert pytest.approx(parsed["vwap"], 0.01) == 158.0
    assert parsed["volume"] == 250000
```

- [ ] **Step 2: Run test to verify RED**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_dhan_packet_codec.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.dhan_packet_codec'`

- [ ] **Step 3: Implement binary codec in `backend/app/services/dhan_packet_codec.py`**

Implement `encode_login_packet`, `encode_subscription_packet`, and `decode_packet` using `struct.pack` and `struct.unpack_from`.

- [ ] **Step 4: Run test to verify GREEN**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_dhan_packet_codec.py -v`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add backend/app/services/dhan_packet_codec.py backend/tests/test_dhan_packet_codec.py
git commit -m "feat: implement Dhan binary packet codec for WebSocket streaming"
```

---

### Task 3: Dhan Real-Time WebSocket Manager & Connection State Machine

**Files:**
- Create: `backend/app/services/dhan_websocket.py`
- Create: `backend/tests/test_dhan_websocket.py`

**Interfaces:**
- Produces: `DhanWebSocketManager(on_tick_callback: Callable[[dict], Awaitable[None]])`
- Methods: `connect(client_id: str, access_token: str)`, `disconnect()`, `subscribe(instruments: list[tuple[int, int]])`, `get_status() -> dict`

- [ ] **Step 1: Write failing tests for WebSocket Manager state transitions and subscriptions**

```python
# backend/tests/test_dhan_websocket.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.dhan_websocket import DhanWebSocketManager

@pytest.mark.asyncio
async def test_websocket_manager_lifecycle():
    ticks_received = []
    async def on_tick(tick):
        ticks_received.append(tick)

    mgr = DhanWebSocketManager(on_tick_callback=on_tick)
    assert mgr.is_connected is False
    assert mgr.status == "DISCONNECTED"

    # Mock connection and tick delivery
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00", # Login Ack (Code 11)
        asyncio.CancelledError() # Stop loop
    ])
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")
        assert mgr.is_connected is True
        assert mgr.status == "CONNECTED"
        await mgr.subscribe([(1, 1330), (2, 44608)])
        assert mock_ws.send.called
        await mgr.disconnect()
        assert mgr.is_connected is False
```

- [ ] **Step 2: Run test to verify RED**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_dhan_websocket.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.dhan_websocket'`

- [ ] **Step 3: Implement `DhanWebSocketManager` in `backend/app/services/dhan_websocket.py`**

Implement connection management, binary read loop, exponential backoff auto-reconnect, keepalive pings, and tick callbacks.

- [ ] **Step 4: Run test to verify GREEN**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_dhan_websocket.py -v`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add backend/app/services/dhan_websocket.py backend/tests/test_dhan_websocket.py
git commit -m "feat: implement DhanWebSocketManager with auto-reconnect and tick dispatch"
```

---

### Task 4: Sub-Second Price Dispatch & Paper Trading Trailed SL Integration

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/app/api/signals.py`
- Create: `backend/tests/test_websocket_scanner_integration.py`

**Interfaces:**
- Consumes: `DhanWebSocketManager` ticks
- Produces: Instant paper trading update `paper_trader.update_market_prices(...)` per tick and broadcasts tick deltas to SSE subscribers

- [ ] **Step 1: Write failing tests for instant paper trading execution on WebSocket tick**

```python
# backend/tests/test_websocket_scanner_integration.py
import pytest
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import UniverseManager
from app.services.paper_trader import paper_trader
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import recommend_strike

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
```

- [ ] **Step 2: Run test to verify RED**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_websocket_scanner_integration.py -v`  
Expected: FAIL with `AttributeError: 'ScannerWorker' object has no attribute '_handle_incoming_ws_tick'`

- [ ] **Step 3: Implement `_handle_incoming_ws_tick` and wire `DhanWebSocketManager` in `ScannerWorker`**

Connect WebSocket upon live session activation; route incoming ticks to `paper_trader` and SSE broadcast queue.

- [ ] **Step 4: Run test to verify GREEN**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_websocket_scanner_integration.py -v`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add backend/app/services/scanner_worker.py backend/tests/test_websocket_scanner_integration.py
git commit -m "feat: integrate sub-second WebSocket tick handling with paper trading engine"
```

---

### Task 5: Frontend OAuth Flow, Token Expiry Countdown & WebSocket Live Pill

**Files:**
- Modify: `frontend/src/context/DhanAuthContext.tsx`
- Modify: `frontend/src/components/Header.tsx`
- Modify: `frontend/src/components/Header.test.tsx`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: 1-Click "Log in with Dhan" OAuth flow in login modal
- Produces: `⚡ WS LIVE (Sub-second)` glowing pill when WebSocket is active
- Produces: 24-hour token expiry countdown in Header with reconnect reminder

- [ ] **Step 1: Write frontend test for OAuth login action and WS Live pill display**

Add tests in `frontend/src/components/Header.test.tsx` verifying:
- "WS LIVE" badge renders when `feedStatus === 'WS_LIVE'`
- Countdown tooltip displays remaining session hours

- [ ] **Step 2: Run test to verify RED**

Run: `cd frontend && npm test -- --run`  
Expected: FAIL on missing badge assertion

- [ ] **Step 3: Implement OAuth handler and WS status badge in frontend**

Update `DhanAuthContext.tsx` to handle OAuth redirect query params (`consentId`). Update `Header.tsx` with WebSocket badge and countdown.

- [ ] **Step 4: Run test and build to verify GREEN**

Run: `cd frontend && npm test -- --run && npm run build`  
Expected: PASS with 0 build errors

- [ ] **Step 5: Commit changes**

```bash
git add frontend/
git commit -m "feat: add Dhan OAuth 1-click login and real-time WebSocket live indicator"
```

---

### Task 6: Full System Verification, Production Build & VM Sync

**Files:**
- None (operational verification across full stack)

- [ ] **Step 1: Run complete backend pytest suite**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`  
Expected: All tests pass (>= 138 tests)

- [ ] **Step 2: Build frontend distribution**

Run: `cd frontend && npm run build`  
Expected: Clean build in `dist/`

- [ ] **Step 3: Rsync and deploy to remote GCP VM**

Run:
```bash
rsync -avz -e "ssh -i /Users/manigopal/.ssh/google_compute_engine -o StrictHostKeyChecking=no" --exclude 'node_modules' --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '.pytest_cache' /Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/ mani_vutla7@34.14.178.224:/home/mani_vutla7/BB_OPTIONS_DASHBOARD/
ssh -i /Users/manigopal/.ssh/google_compute_engine -o StrictHostKeyChecking=no mani_vutla7@34.14.178.224 "sudo systemctl restart bb-options && sudo systemctl status bb-options --no-pager"
```
Expected: `bb-options` active (running)

- [ ] **Step 4: Curl remote health and OAuth login-url endpoints**

Run: `curl -k https://options.34-14-178-224.sslip.io/api/health`  
Expected: `HTTP 200 {"status": "healthy", ...}`
