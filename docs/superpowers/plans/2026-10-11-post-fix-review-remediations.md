# Post-Fix Review Remediations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 11 critical and quality findings documented in `REVIEW_FINDINGS_2026-10-10_POST_FIX.md` across origin validation, quote freshness, server-side trade gating, historical candle completion, session race condition prevention, and frontend error surfacing.

**Architecture:** 
- Enforce strict exact-origin verification in FastAPI middleware, rejecting `Origin: null` and unauthorized hostnames on all mutating routes.
- Unify manual close operations through a single server-quote freshness pipeline with modeled-fill labeling.
- Enforce server-authoritative signal validation in `/api/paper/trade` ensuring the resolved radar signal itself is confirmed.
- Separate finished bars from forming bars during historical candle seeding, preventing intrabar breakout auto-trades.
- Invalidate in-flight scans across all asynchronous network boundaries (`_session_generation` checking) and properly cancel WebSocket connect tasks on disconnect.
- Guard option quote freshness timestamps strictly on positive prices (`last_price > 0`).
- Surface descriptive error toasts on failed paper trade/close actions in the React frontend.

**Tech Stack:** Python 3.14, FastAPI, Pandas, SQLite, React 18, TypeScript, Vitest, Pytest.

**Spec:** `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/REVIEW_FINDINGS_2026-10-10_POST_FIX.md`

## Global Constraints
- Target Location: Strictly inside `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`.
- All backend pytest tests must pass (`/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`).
- All frontend vitest tests must pass (`cd frontend && npm test -- --run`).
- Frontend production build must compile with 0 errors (`npm run build`).
- Do not break existing features: Setups 1-8, 4-metric hero bar, setup filter tabs, itemized tax receipt popover.

## Review Focus
1. An attacker sending `Origin: null` or `https://attacker.sslip.io` must receive HTTP 403 Forbidden on state-mutating routes.
2. A client submitting a valid `signal_id` for an active provisional signal with forged `is_confirmed=True` must be rejected with HTTP 400.
3. `/api/signals/close/{id}` must apply the exact same freshness checks and `(Modeled: Unquoted)` labeling as `/api/paper/close/{id}`.
4. Historical seed candles that include the currently forming intraday bar must NOT insert that bar into completed `_candle_history`.
5. Disconnect while an option chain fetch or option candle fetch is awaiting must abort the scan and keep demo mode.

---

### Task 1: Origin Middleware Exact Allowlist & Null Origin Rejection (F1)

**Files:**
- Modify: `backend/app/main.py:55-85`
- Test: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: FastAPI `Request`, `request.headers.get("origin")`, `request.headers.get("referer")`
- Produces: `verify_state_mutation_origin` middleware returning HTTP 403 for `Origin: null`, arbitrary `*.sslip.io`, and unauthorized origins.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_deep_dive.py`**
  Assert that `Origin: null` returns 403, `Origin: https://evil.sslip.io` returns 403, and allowed origin returns 200.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_finding_7 -v`

- [ ] **Step 3: Implement exact allowlist and null-origin rejection in `backend/app/main.py`**
  Verify origin against exact set `_ALLOWED_ORIGINS` (including `ALLOWED_ORIGIN` env). Reject `origin == "null"`.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_finding_7 -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(security): enforce exact origin match and reject null origin for mutations (F1)"`

---

### Task 2: Unified Close Route Freshness Validation (F2)

**Files:**
- Modify: `backend/app/api/paper.py:80-130`
- Modify: `backend/app/api/signals.py:76-105`
- Test: `backend/tests/test_scanner_slippage_wiring.py`
- Test: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: `_close_position_with_freshness` in `app.api.paper`
- Produces: `/api/signals/close/{id}` routing through `_close_position_with_freshness` so that stale quotes (>15s) receive `(Modeled: Unquoted)` and cannot bypass pricing logic.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_deep_dive.py`**
  Assert that closing via `/api/signals/close/{id}` with a stale quote (>15s) labels exit as `(Modeled: Unquoted)` just like `/api/paper/close/{id}`.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_signals_close_freshness -v`

- [ ] **Step 3: Wire `/api/signals/close` through `_close_position_with_freshness`**
  Ensure both endpoints share the exact same validation and labeling.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_signals_close_freshness -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(paper): route signals close alias through quote-freshness validation (F2)"`

---

### Task 3: Server-Authoritative Live Signal Confirmation Gate & Fail-Closed Lookup (F3, F7)

**Files:**
- Modify: `backend/app/api/paper.py:24-75`
- Test: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: `worker._state.signals`
- Produces: Server-verified `target_signal.is_confirmed is True` check after radar lookup. Fail-closed HTTP 503 if radar lookup raises unexpected exceptions.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_deep_dive.py`**
  Test where server radar has a provisional signal (`is_confirmed=False`), and client posts that signal ID with `is_confirmed=True`. Expect HTTP 400 rejection.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_forged_confirmation -v`

- [ ] **Step 3: Implement strict server confirmation gate in `backend/app/api/paper.py`**
  After resolving `matched` from radar, verify `getattr(target_signal, "is_confirmed", True)` and replace broad `except Exception: pass` with HTTP 503.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_forged_confirmation -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(paper): check server signal confirmation and fail closed on lookup errors (F3, F7)"`

---

### Task 4: Historical Seed Bar Completion & Post-Deduplication Validation (F4, F8)

**Files:**
- Modify: `backend/app/services/scanner_worker.py:480-515`
- Test: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: `fetch_intraday_candles` response DataFrame
- Produces: `_candle_history` containing strictly completed bars where `bar_ts + timedelta(minutes=interval) <= exchange_now`. In-progress bar merged into `_current_forming_candle`. Post-deduplication check ensures `>= 20` unique bars before clearing backoff.

- [ ] **Step 1: Write failing test in `backend/tests/test_audit_deep_dive.py`**
  Test with historical candles ending with a bar whose slot end is in the future. Assert the future bar is NOT added to `_candle_history`. Test with 20 rows but 19 unique timestamps; assert seed fails and triggers backoff.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_seed_slot_completion -v`

- [ ] **Step 3: Implement slot-completion separation and post-dedup length validation**
  In `seed_historical_candles_if_needed`, deduplicate first. Require `len(df) >= 20`. Separate completed bars from forming bar.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_seed_slot_completion -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(scanner): require completed candle slot and unique bar count for historical seed (F4, F8)"`

---

### Task 5: Asynchronous Disconnect Task Cancellation & In-Flight Generation Guards (F5, F6)

**Files:**
- Modify: `backend/app/services/scanner_worker.py:160-185,340-375,980-1085`
- Test: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: `_session_generation`
- Produces: 
  - `set_session_credentials(None, None)` cancels `_ws_connect_task`.
  - `_execute_scan_cycle` verifies `_session_generation == gen and self._session_credentials is not None` after option chain awaits, after option chart setups await, and before state broadcast / trade processing.
  - Option chain parser updates `_option_last_quote_time` only when `c_ltp_f > 0`.

- [ ] **Step 1: Write failing tests in `backend/tests/test_audit_deep_dive.py`**
  Test disconnect during `_evaluate_option_chart_setups`. Test option chain entry with `last_price=0` does not update `_option_last_quote_time`.

- [ ] **Step 2: Run test to verify RED**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_disconnect_race -v`

- [ ] **Step 3: Implement cancel task, multi-point generation checks, and positive quote guard**
  Update `set_session_credentials`, `_execute_scan_cycle`, and `_option_last_quote_time`.

- [ ] **Step 4: Run test to verify GREEN**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -k test_disconnect_race -v`

- [ ] **Step 5: Commit**
  `git commit -am "fix(scanner): guard scan cycle awaits against disconnect race and validate quote price (F5, F6)"`

---

### Task 6: Strengthen Regression Tests (F9)

**Files:**
- Modify: `backend/tests/test_audit_deep_dive.py`

**Interfaces:**
- Consumes: `ScannerWorker`, `PaperTradingEngine`
- Produces: Robust non-vacuous assertions for prior-session signals, forming candle signals, and partial feed quote maps.

- [ ] **Step 1: Update `test_finding_1`, `test_finding_3`, and `test_finding_4`**
  Ensure signals are actually populated and asserted. In partial feed test, assert that the instrument with a live quote IS present in `price_map` while the missing one is omitted.

- [ ] **Step 2: Run all deep dive tests to verify pass**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_audit_deep_dive.py -v`

- [ ] **Step 3: Commit**
  `git commit -am "test(audit): strengthen deep dive regression tests with non-vacuous assertions (F9)"`

---

### Task 7: Frontend Trade & Close Error Feedback Banner (F11)

**Files:**
- Modify: `frontend/src/App.tsx:140-185`
- Test: `frontend/src/App.test.tsx` (or new test file `frontend/src/components/TradeErrorFeedback.test.tsx`)

**Interfaces:**
- Consumes: HTTP error responses from `/api/paper/trade` and `/api/paper/close/{id}`
- Produces: User-visible error alert/toast displaying the server error `detail`.

- [ ] **Step 1: Write frontend test for error handling**
  Verify that when `/api/paper/trade` returns 400 with detail "Cannot enter trade on unconfirmed provisional candle setup", the error message is displayed to the user.

- [ ] **Step 2: Run test to verify RED**
  Run: `cd frontend && npm test -- --run`

- [ ] **Step 3: Implement error banner/toast in `frontend/src/App.tsx`**
  Capture `res.json().detail` on non-2xx responses and set `tradeError` state with auto-dismiss or close button.

- [ ] **Step 4: Run test to verify GREEN and check production build**
  Run: `cd frontend && npm test -- --run && npm run build`

- [ ] **Step 5: Commit**
  `git commit -am "feat(ui): display error banner for rejected trades and close actions (F11)"`

---

### Task 8: Full Verification, GCP Deployment & Git Push

**Files:**
- Deploy: All changed files to GCP VM (`34.14.178.224`)

- [ ] **Step 1: Run full backend pytest suite**
  Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`

- [ ] **Step 2: Run full frontend test suite and build**
  Run: `cd frontend && npm test -- --run && npm run build`

- [ ] **Step 3: Synchronize to GCP VM and restart service**
  Run: `rsync` to VM and `sudo systemctl restart bb-options`

- [ ] **Step 4: Verify remote endpoints**
  Verify `https://options.34-14-178-224.sslip.io/api/health`

- [ ] **Step 5: Push to git origin**
  Run: `git push origin main`
