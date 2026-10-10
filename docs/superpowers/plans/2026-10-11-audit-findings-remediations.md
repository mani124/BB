# Code Review Remediation Plan — 11 October 2026

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 5 critical issues and 4 suggestions documented in `REVIEW_FINDINGS_2026-10-11.md` incorporating user refinements on direct-client capability boundary, unified server-owned exit pricing records, ordered async SQLite persistence queue with shutdown flush, and comprehensive `is_scanning = False` finally guards.

**Architecture:**
- **F1 (Direct-Client Capability Boundary)**: 
  - For browser clients: verify `Origin` / `Referer` against `_ALLOWED_ORIGINS`.
  - For direct HTTP clients (`Origin` and `Referer` absent): strictly reject state mutations (`POST`, `PUT`, `DELETE`, `PATCH`) with `HTTP 401 Unauthorized` unless accompanied by a trusted capability header `X-Dashboard-Capability` (or `Authorization: Bearer <token>`).
  - Configure `DASHBOARD_CAPABILITY` token in settings, defaulted to a persistent server token or env var.
- **F2 & F4 (Server-Owned Exit Pricing & Unified Quote Store)**:
  - Define `OptionQuote` dataclass: `ltp: float`, `bid: Optional[float]`, `timestamp: float`, `source: str` ("ws" or "chain").
  - `ScannerWorker` maintains `_latest_option_quotes: dict[str, OptionQuote]`.
  - Both `/api/paper/close` and `/api/signals/close` query `worker.get_option_quote(sec_id, max_age_s=15.0)` and ignore/strip client pricing fields.
- **F3 (Server-Governed Feed Mode & Radar Purge)**:
  - Derive live mode strictly from server credentials and active mode. Reject client requests specifying `feed_mode="live"` when server is in demo mode with `HTTP 409 Conflict`.
  - `set_session_credentials(None, None)` clears `_state.signals` and `_state.radar`.
- **F5 (Scan Disconnect Guards & Finally Block)**:
  - Check `_session_generation` immediately after `_subscribe_active_positions()` before state publication.
  - Wrap scan cycle in `try ... finally: self._state.is_scanning = False`.
- **F6 (Intraday Volume Baseline)**:
  - Base initial volume offset on whether current-session (today's) bars exist in `_candle_history`. If only prior-session bars exist, initialize today's volume from the quote's cumulative volume.
- **F7 (Race Test Barriers)**:
  - Test disconnect races using `asyncio.Event` barriers to guarantee await points were actively paused and aborted.
- **F8 (Ordered Async SQLite Persistence Queue)**:
  - Use an ordered `asyncio.Queue` consumed by a single background worker running `await asyncio.to_thread(self._sync_persist, batch)`.
  - On engine shutdown, await queue drain and flush.
- **F9 (5M Option Chart Cache)**:
  - Cache completed option contract charts by security ID and 5-minute slot boundary to prevent duplicate 5-day chart downloads on consecutive scan cycles.

**Tech Stack:** Python 3.14, FastAPI, Pandas, SQLite, React 18, TypeScript, Pytest, Vitest.

**Spec:** `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/REVIEW_FINDINGS_2026-10-11.md`

## Global Constraints
- Target Location: Strictly inside `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`.
- All backend pytest tests must pass (`/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`).
- All frontend vitest tests must pass (`cd frontend && npm test -- --run`).
- Frontend production build must compile with 0 errors (`npm run build`).

---

### Task 1: Direct-Client Capability Boundary & Origin Protection (F1)

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_audit_oct11.py`

**Interfaces:**
- Consumes: Request headers (`Origin`, `Referer`, `X-Dashboard-Capability`, `Authorization`)
- Produces: `verify_state_mutation_origin` middleware returning `HTTP 401` when direct clients omit capability token on mutations.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_oct11.py`**
  Assert that direct POST/PUT/DELETE requests with no Origin/Referer return HTTP 401 unless `X-Dashboard-Capability` is provided.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_direct_client_capability_required -v`

- [ ] **Step 3: Implement direct-client capability boundary in `main.py`**
  Verify browser origin when present. When Origin and Referer are absent, require valid `X-Dashboard-Capability` or `Authorization` header.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_direct_client_capability_required -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(security): enforce capability token for direct-client mutations (F1)"`

---

### Task 2: Server-Owned Exit Pricing & Unified Quote Store (F2, F4)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/app/api/paper.py`
- Modify: `backend/app/api/signals.py`
- Test: `backend/tests/test_audit_oct11.py`

**Interfaces:**
- Consumes: WebSocket ticks & option chain ticks
- Produces: `worker.get_option_quote(sec_id, max_age_s=15.0) -> Optional[OptionQuote]`. ClosePositionRequest without caller prices.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_oct11.py`**
  Assert that close routes ignore caller-supplied `real_bid_price`, and use atomic `OptionQuote` from server store.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_server_owned_exit_pricing -v`

- [ ] **Step 3: Implement atomic OptionQuote and refactor close routes**
  Implement `OptionQuote` in `scanner_worker.py`. Update `/api/paper/close` and `/api/signals/close` to resolve fills strictly from `get_option_quote`.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_server_owned_exit_pricing -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(paper): enforce server-owned exit quotes with atomic timestamp records (F2, F4)"`

---

### Task 3: Server-Governed Feed Mode & Radar Purge (F3)

**Files:**
- Modify: `backend/app/api/paper.py`
- Modify: `backend/app/services/scanner_worker.py`
- Test: `backend/tests/test_audit_oct11.py`

**Interfaces:**
- Consumes: `worker._session_credentials`, `worker._state.active_mode`
- Produces: `open_manual_trade` rejecting `feed_mode="live"` when backend is in demo mode with HTTP 409. `set_session_credentials(None, None)` clears `signals` and `radar`.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_oct11.py`**
  Assert HTTP 409 on `feed_mode="live"` when credentials are None. Assert disconnect clears radar signals.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_server_governed_feed_mode -v`

- [ ] **Step 3: Implement feed mode gate and signal purge**
  Enforce server-mode in `open_manual_trade`. Purge signals/radar in `set_session_credentials`.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_server_governed_feed_mode -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(paper): govern feed mode by server credentials and purge signals on logout (F3)"`

---

### Task 4: Scan Disconnect Guards & Finally Block (F5)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Test: `backend/tests/test_audit_oct11.py`

**Interfaces:**
- Consumes: `_session_generation`
- Produces: Check generation immediately after `_subscribe_active_positions()`. Wrap `_execute_scan_cycle` with `try ... finally: self._state.is_scanning = False`.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_oct11.py`**
  Assert scan disconnect during `_subscribe_active_positions` aborts publication, and `is_scanning` is cleared via finally.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_scan_disconnect_guard_finally -v`

- [ ] **Step 3: Implement post-subscription check and finally block**
  Add generation check and wrap scan cycle with `try ... finally`.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -k test_scan_disconnect_guard_finally -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(scanner): check generation after subscription and clear is_scanning in finally (F5)"`

---

### Task 5: Intraday Volume Baseline, Ordered Async Persistence & Option Chart Cache (F6, F7, F8, F9)

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/app/services/paper_trader.py`
- Test: `backend/tests/test_audit_oct11.py`

**Interfaces:**
- Consumes: Market quotes, Position updates, Option chart requests
- Produces:
  - F6: Today volume baseline checks for current-session bars in history.
  - F7: Async barrier tests verifying disconnect races.
  - F8: Ordered persistence queue with shutdown drain/flush.
  - F9: 5-minute slot cache for completed option contract charts.

- [ ] **Step 1: Write tests in `backend/tests/test_audit_oct11.py` for F6, F7, F8, F9**
- [ ] **Step 2: Implement current-session volume baseline (F6)**
- [ ] **Step 3: Implement ordered persistence queue with shutdown flush (F8)**
- [ ] **Step 4: Implement 5m option chart caching (F9)**
- [ ] **Step 5: Run tests to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_oct11.py -v`
- [ ] **Step 6: Commit**
  `git commit -am "perf(core): add ordered db write queue, 5m chart cache, and current-session volume baseline (F6-F9)"`

---

### Task 6: Full Verification, GCP Deployment & Git Push

**Files:**
- Deploy: All changed files to GCP VM (`34.14.178.224`)

- [ ] **Step 1: Run full backend pytest suite**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`

- [ ] **Step 2: Run frontend vitest suite and build**
  Run: `cd frontend && npm test -- --run && npm run build`

- [ ] **Step 3: Synchronize to GCP VM and restart service**
  Run: `rsync` to VM and `sudo systemctl restart bb-options`

- [ ] **Step 4: Verify remote endpoints & security capability**
  Verify `/api/health`, capability gates, and origin gates.

- [ ] **Step 5: Push commits to remote origin**
  Run: `git push origin main`
