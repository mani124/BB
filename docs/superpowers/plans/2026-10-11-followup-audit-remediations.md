# Follow-up Audit Remediations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate all 8 findings from `REVIEW_FINDINGS_2026-10-11_FOLLOWUP.md`: enforce capability authorization boundary across mutations, private reads, and SSE without Origin bypass (F1, F3); implement ordered async reset barrier preventing race resurrection and surfacing storage errors (F2, F7); preserve monotonic quote observation timestamps for cached option chains (F4); separate completed bars from live forming candle with slot deduplication (F5); include seeded forming bar in initial day volume baseline (F6); and derive theoretical exit strictly from server observations to protect slippage analytics (F8).

**Architecture:**
- **Security & Authorization (`app/main.py`, `app/core/security.py`, `app/api/auth.py`):** Require unguessable capability token for all state mutations independently of Origin/Referer. Protect `/api/auth/oauth/token` and `/api/auth/verify`. Protect private reads and SSE (`/api/signals/stream`). Provide bootstrap `POST /api/auth/session` authorized by `DASHBOARD_CAPABILITY` secret (Dhan credentials alone do not grant dashboard capability), issuing an HttpOnly `dashboard_session` cookie for native `EventSource` (avoiding leaky URL query tokens) and `X-Dashboard-Capability` header.
- **Durable FIFO Persistence & Ordered Reset Barrier (`app/services/paper_trader.py`, `app/api/paper.py`):** Capture owning event loop; threadsafe FIFO enqueueing with generation barrier; make `reset()` and `reset_sync()` route through the exact same ordered queue and committed `clear_all` barrier without bypassing the queue; reject stale scan writes; track failures per queued operation future so `flush()` and `reset()` report the exact relevant failure.
- **Quote Freshness & Monotonic Ordering (`app/services/scanner_worker.py`):** Use `time.monotonic()` consistently for all in-memory cache TTLs, quote freshness (`quote_age <= 15.0s`), and timestamp ordering (`OptionQuote.monotonic_time`), preventing clock jumps and older cached chain quotes from overwriting newer WebSocket quotes.
- **5m Option Chart Cache & Forming Candle Merging (`app/services/scanner_worker.py`):** Cache only completed 5m bars (`df["timestamp"] < current_slot_ts`); update active forming bar from live quotes via `_get_or_update_option_candles`; deduplicate on timestamp to prevent double-counting.
- **Intraday Volume Baseline (`app/services/scanner_worker.py`):** Sum today's seeded completed bars and forming bar; calculate `incremental_vol = max(0, quote_vol - total_represented_vol)` on first quote.
- **Pricing Analytics Integrity (`app/api/paper.py`, `app/services/paper_trader.py`):** Remove/ignore `exit_price` from close requests; derive theoretical exit strictly from server quote or `current_option_price`.

---

## Tasks

### Task 1: Authentication Boundary, Cookie SSE Bootstrap & Protected Mutations (F1, F3)

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/signals.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/context/DhanAuthContext.tsx`
- Create / Update Tests: `backend/tests/test_audit_followup.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_audit_followup.py`**
  - Test 1: Direct mutation with spoofed `Origin: http://localhost:5174` but missing/invalid capability token returns 401 Unauthorized.
  - Test 2: `POST /api/auth/verify` and `POST /api/auth/oauth/token` require valid capability token.
  - Test 3: Private read (`GET /api/paper/portfolio`) and SSE stream (`GET /api/signals/stream`) require capability (via header or `dashboard_session` cookie).
  - Test 4: `POST /api/auth/session` requires master capability secret; Dhan credentials alone do not grant session capability; sets `dashboard_session` HttpOnly cookie.
  - Test 5: SSE stream connects successfully via `dashboard_session` cookie; rejects unauthenticated connection with 401.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_spoofed_origin or test_oauth_routes_protected or test_sse_stream_auth" -v`

- [ ] **Step 3: Implement capability verification across mutations, private reads, and SSE**
  - In `backend/app/core/security.py`: Add session capability verification supporting header (`X-Dashboard-Capability`), Bearer token, or HttpOnly cookie (`dashboard_session`).
  - In `backend/app/main.py`: Enforce capability check on ALL mutations regardless of Origin/Referer. Browser requests must pass both Origin check and capability check. Protect private endpoints.
  - In `backend/app/api/auth.py`: Add `POST /api/auth/session` requiring `secret` matching `settings.DASHBOARD_CAPABILITY`. Set `dashboard_session` HttpOnly cookie. Protect `/oauth/token`, `/verify`, `/disconnect`.
  - In `frontend/src/App.tsx` and `DhanAuthContext.tsx`: Attach capability to fetch requests; EventSource uses cookie credentials.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_spoofed_origin or test_oauth_routes_protected or test_sse_stream_auth" -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(security): enforce capability token across mutations and SSE via cookie auth (F1, F3)"`

---

### Task 2: Ordered Reset Barrier with Queue-Level Cancellation & Per-Op Error Durability (F2, F7)

**Files:**
- Modify: `backend/app/services/paper_trader.py`
- Modify: `backend/app/api/paper.py`
- Modify: `backend/tests/test_audit_followup.py`
- Modify: Existing tests calling `engine.reset()`

- [ ] **Step 1: Write failing tests in `backend/tests/test_audit_followup.py`**
  - Test 1: Race test where delayed SQLite upsert is enqueued, `await engine.reset()` (and `engine.reset_sync()`) is called, queue processes clear_all in FIFO stream, database is verified empty upon reload with zero resurrected trades.
  - Test 2: In-flight scan write with old portfolio generation attempting enqueue after reset is rejected.
  - Test 3: Storage failure during write is tracked per operation and surfaced by `flush()` and `reset()` rather than silently swallowed.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_reset_barrier or test_storage_error_surfaced" -v`

- [ ] **Step 3: Implement ordered reset barrier and error propagation in `PaperTradingEngine`**
  - Capture owning event loop `self._loop` in `start_persistence_worker()`.
  - Maintain `self._portfolio_generation: int = 0`.
  - Make `async def reset(self) -> None`: increment generation, enqueue `("clear_all", gen, future)`, await `future`, reset in-memory state.
  - Implement `reset_sync()` using the exact same queue and completion barrier (waiting on the future threadsafe without bypassing the queue).
  - Make `/api/paper/reset` an `async def reset_portfolio()` route awaiting `paper_trader.reset()`.
  - Update `_persistence_worker` to track operation errors on each item's Future; raise in `flush()` and `reset()`.
  - Guard `_enqueue_write`: reject items if item generation < `self._portfolio_generation`.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_reset_barrier or test_storage_error_surfaced" -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(paper): implement ordered reset barrier with generation guard and per-op error durability (F2, F7)"`

---

### Task 3: Consistent Monotonic Quote Timestamps & Cached Chain Freshness (F4)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/tests/test_audit_followup.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_audit_followup.py`**
  - Test 1: Option quotes extracted from cached chain retain original fetch monotonic timestamp; close at T+16s fails freshness check even if scan ran at T+10s.
  - Test 2: Sub-second WebSocket quote at T+5s is not overwritten by chain quote observed at T.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_cached_chain_quote_timestamp or test_websocket_quote_monotonicity" -v`

- [ ] **Step 3: Implement monotonic observation timestamp capture and ordering**
  - Use `time.monotonic()` consistently for `OptionQuote.timestamp`, quote age checks, and option chain cache TTLs.
  - In `get_or_fetch_option_chain`: record `fetch_monotonic = time.monotonic()` when response arrives; cache `(fetch_monotonic, oc)`.
  - In `_execute_scan_cycle`: pass `timestamp=fetch_monotonic` to `record_option_quote`.
  - In `record_option_quote`: prevent overwriting an existing quote if `existing.timestamp > ts`.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k "test_cached_chain_quote_timestamp or test_websocket_quote_monotonicity" -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(scanner): enforce monotonic quote timestamps and retain chain fetch observation time (F4)"`

---

### Task 4: Deduplicated 5m Chart Caching with Live Forming Candle Merging (F5)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/tests/test_audit_followup.py`

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_followup.py`**
  - Test: Historical API called once in a 5m slot; two consecutive live quotes in that slot dynamically update the forming candle and indicator calculations without freezing, and duplicate timestamps are eliminated.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_option_chart_forming_candle_dynamic_update -v`

- [ ] **Step 3: Implement completed bar caching with forming candle merging**
  - In `_evaluate_option_chart_setups`: filter completed bars `df[df["timestamp"] < current_slot_ts]` and cache.
  - Fetch/update live forming candle via `_get_or_update_option_candles(sec_id_str, opt_ltp, opt_vol)`.
  - Combine completed bars with forming candle and deduplicate: `pd.concat(...).drop_duplicates(subset=["timestamp"], keep="last")`.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_option_chart_forming_candle_dynamic_update -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(scanner): cache completed 5m bars and dynamically merge live forming candle with deduplication (F5)"`

---

### Task 5: Intraday Volume Baseline with Seeded Forming Bar Representation (F6)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/tests/test_audit_followup.py`

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_followup.py`**
  - Test: Seeded history with completed bars totaling 50k and a partial forming bar of 2k receives first quote with cumulative volume 55k; incremental volume is correctly calculated as `max(0, 55000 - 52000) = 3000`.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_volume_baseline_with_seeded_forming_bar -v`

- [ ] **Step 3: Implement total represented volume calculation in `get_or_update_live_candles`**
  - Sum today's seeded completed bars + seeded forming candle volume to establish `total_represented_vol`.
  - Calculate `incremental_vol = max(0, quote_vol - total_represented_vol)` on first quote.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_volume_baseline_with_seeded_forming_bar -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(scanner): account for seeded completed and forming bars in initial volume baseline (F6)"`

---

### Task 6: Strict Server-Derived Exit Pricing & Metric Integrity (F8)

**Files:**
- Modify: `backend/app/api/paper.py`
- Modify: `backend/app/api/signals.py`
- Modify: `backend/tests/test_audit_followup.py`

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_followup.py`**
  - Test: Caller passing arbitrary `exit_price: 100000.0` in `/api/paper/close` or `/api/signals/close` for an unquoted position cannot alter `theoretical_exit` or inflate `exit_slippage`; theoretical exit defaults strictly to server-recorded `pos.current_option_price`.

- [ ] **Step 2: Run pytest to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_close_ignores_caller_exit_price -v`

- [ ] **Step 3: Strip caller exit_price and derive theoretical exit strictly on server**
  - Remove/ignore `exit_price` from `ClosePositionRequest`.
  - In `_close_position_with_freshness`: derive theoretical exit strictly from `server_ltp or server_bid or pos.current_option_price`.

- [ ] **Step 4: Run pytest to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_followup.py -k test_close_ignores_caller_exit_price -v`

- [ ] **Step 5: Commit changes**
  `git commit -am "fix(paper): derive theoretical exit strictly from server quotes and strip caller exit price (F8)"`

---

### Task 7: Full System Verification, Production Build, GCP Deployment & Git Push

**Files:**
- Deploy: All modified files to GCP VM (`34.14.178.224`)

- [ ] **Step 1: Run complete backend pytest suite**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`

- [ ] **Step 2: Run frontend vitest suite and production build**
  Run: `cd frontend && npm test -- --run && npm run build`

- [ ] **Step 3: Synchronize to GCP VM and restart service**
  Run: `rsync` to VM and `sudo systemctl restart bb-options`

- [ ] **Step 4: Verify remote endpoints, SSE stream, and capability boundary**
  Verify `/api/health`, capability gates on mutations/reads/SSE, and browser origin.

- [ ] **Step 5: Push commits to remote origin**
  Run: `git push origin main`
