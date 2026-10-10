# Post-fix code review

Reviewed `main` at `d215ae8` on 2026-10-10, with emphasis on the latest fix commit and its integration with the rest of the dashboard. Application code was not changed. Verification: **239 backend tests passed**, **23 frontend tests passed**, and the frontend production build succeeded. The findings below concern cases those checks do not cover.

## 🔴 Critical Issues — Must fix before merge

### 1. Origin protection accepts attacker-controlled hosts and `Origin: null`

- **Location:** `backend/app/main.py:63-81`
- **Problem:** A mutation is permitted whenever the origin host ends in `.sslip.io`; that suffix is not specific to this deployment. The middleware also permits an origin that parses to no hostname and requests without either header. A harmless probe against `POST /api/paper/trade` with an invalid body returned **403** for `https://evil.example`, but **422** (route reached) for both `https://evil.sslip.io` and `Origin: null`. A valid body can therefore reach state-changing routes from these origins. Origin filtering alone also does not authorize direct non-browser clients.
- **Suggested solution:** Match an exact configured origin, including scheme and port, reject malformed/`null` origins for browser mutations, and require a server-issued session credential for writes. For example:

  ```python
  allowed = {"http://127.0.0.1:5173", "https://options.example.com"}
  if request.method in WRITE_METHODS:
      if request.headers.get("origin") not in allowed:
          return JSONResponse({"detail": "Forbidden"}, status_code=403)
      verify_session_capability(request)
  ```

- **Rationale:** Portfolio reset, settings, trade, close, and disconnect must be tied to the dashboard's authorized session. Add tests for arbitrary `*.sslip.io`, `Origin: null`, missing origin, and direct clients.

### 2. The second close endpoint bypasses the new quote-freshness logic

- **Location:** `backend/app/api/signals.py:76-105`; compare `backend/app/api/paper.py:85-119`
- **Problem:** `/api/signals/close/{position_id}` calls `paper_trader.close_position` directly, skipping the freshness checks and modeled-fill labeling added to `/api/paper/close/{position_id}`. It also accepts caller-supplied `real_bid_price`, `real_opt_price`, and `exit_price`. A caller can close a live position using any positive bid and record arbitrary realized P&L; the test at `backend/tests/test_scanner_slippage_wiring.py:256-273` explicitly exercises this alias with a supplied bid.
- **Suggested solution:** Have both paths invoke one close service that obtains a timestamped server-observed quote and decides whether a modeled fill is necessary. Do not accept market-observation fields from the request:

  ```python
  @router.post("/close/{position_id}")
  def close_alias(position_id: str):
      return close_position_with_server_quote(position_id)
  ```

- **Rationale:** All routes that mutate a live position need the same pricing and validation rules. Test both paths with a stale quote and a forged bid.

### 3. Client confirmation can override the server's provisional signal

- **Location:** `backend/app/api/paper.py:25-26,43-74`
- **Problem:** The endpoint checks `body.signal.is_confirmed` before looking up the signal by ID. It then replaces `target_signal` with the server's matching signal but never checks that signal's `is_confirmed`. If the current radar contains a provisional signal and a caller submits its ID with `is_confirmed=true`, the route can open a live position from that provisional server signal, provided its contract has a quote. The new forged-signal test covers an unknown ID, not this case.
- **Suggested solution:** Accept only `signal_id` and lots for live entry, resolve the server signal first, and check `target_signal.is_confirmed` and quote freshness after resolution:

  ```python
  target = next((s for s in worker.get_state().signals if s.id == body.signal_id), None)
  if target is None or not target.is_confirmed:
      raise HTTPException(400, "Signal is unavailable or provisional")
  ```

- **Rationale:** A client flag cannot establish whether an exchange candle has closed. Add a test with a real provisional radar signal and a forged confirmed copy of the same ID.

### 4. A current, unfinished historical bar is still treated as confirmed

- **Location:** `backend/app/services/scanner_worker.py:488-504,935-955`
- **Problem:** Historical seeding sorts and deduplicates bars but still inserts the latest API bar into `_candle_history` without checking that its time interval has ended. The confirmation gate checks only `s_dt.date() == today_date`. If Dhan returns the current 5-minute or 15-minute bar while it is forming, that bar can become a confirmed live signal. The first live quote also creates a second forming bar for the same time slot, duplicating that interval in indicator input.
- **Suggested solution:** After timestamp normalization, separate bars by slot end and only put finished bars in `_candle_history`; merge any current-slot API row into `_current_forming_candle` by timestamp. For example:

  ```python
  slot_end = bar_ts + timedelta(minutes=interval)
  if slot_end <= exchange_now:
      completed.append(bar)
  else:
      forming = merge_same_slot(forming, bar)
  ```

- **Rationale:** A calendar-date check does not establish candle completion. Test a restart halfway through a 5-minute slot with a breakout that reverses before the slot ends.

### 5. Disconnect can race with WebSocket connect and later scan awaits

- **Location:** `backend/app/services/scanner_worker.py:162-179,340-372,979-1054,1067-1084`
- **Problem:** Disconnect increments a generation but does not cancel the pending `_ws_connect_task`. A connect that finishes after the disconnect can subscribe and set `ws_connected=True` and `feed_status="WS_LIVE"`. The scan checks the generation after option-chain fetch, then awaits `_evaluate_option_chart_setups` and `_subscribe_active_positions` without checking again before publishing state and trades. Disconnect during either await can let old-session work finish after logout.
- **Suggested solution:** Cancel and await the connection task during disconnect. Give connect and scan operations the captured generation, checking it after every network await and immediately before state mutation, broadcast, or trade creation:

  ```python
  if generation != self._session_generation or self._session_credentials is None:
      return
  ```

- **Rationale:** Session invalidation must cover the entire asynchronous operation, not only selected awaits. Add tests that pause connect, option-candle fetch, and subscription independently while disconnect runs.

### 6. Option-chain presence refreshes quote age without a valid quote

- **Location:** `backend/app/services/scanner_worker.py:993-1003`; `backend/app/api/paper.py:98-105`
- **Problem:** Every option-chain contract with a `security_id` refreshes `_option_last_quote_time`, even when `last_price` is missing, zero, or invalid. If an old `_option_forming_candle` exists for that contract, manual close then sees a timestamp less than 15 seconds old and uses the old candle close as a fresh observed fill. The new stale-close test sets an old timestamp but does not cover a zero-priced chain response that renews it.
- **Suggested solution:** Refresh the timestamp only after validating a positive quote for the same contract, and store quote value and receipt time together. Manual close should use that pair rather than combining a chain timestamp with a separate candle's close:

  ```python
  if c_ltp_f > 0:
      self._last_option_quote[sec_id] = (c_ltp_f, time.time())
  ```

- **Rationale:** A contract appearing in a response does not mean its market price was refreshed. Test an old candle plus a chain entry with `last_price=0`.

## 🟡 Suggestions — Improvements to consider

### 7. Live-entry lookup fails open on unexpected errors

- **Location:** `backend/app/api/paper.py:45-60`
- **Problem:** `except Exception: pass` leaves `target_signal = body.signal`. If server lookup fails for an unexpected reason, the route can continue with a client-supplied live signal and quote. The broad catch also hides the operational error.
- **Suggested solution:** Let unexpected errors surface as a 5xx response, or convert them to a clear fail-closed 503. Remove the broad catch around server signal resolution:

  ```python
  try:
      target_signal = lookup_current_signal(body.signal_id)
  except Exception as exc:
      logger.exception("Live signal lookup failed")
      raise HTTPException(503, "Signal state unavailable") from exc
  ```

- **Rationale:** Trading validation should never become weaker when an internal dependency fails.

### 8. Historical seed success is decided before deduplication

- **Location:** `backend/app/services/scanner_worker.py:488-508`
- **Problem:** An API response with 20 rows but fewer than 20 unique timestamps passes the length check, is stored as a successful seed, and clears its backoff. The next scan sees fewer than 20 cached bars and immediately fetches again. This recreates repeated upstream requests for duplicate-heavy responses.
- **Suggested solution:** Validate `len(df) >= 20` after timestamp parsing, invalid-row removal, sorting, and deduplication; count insufficient unique bars as a failed attempt subject to backoff.
- **Rationale:** Retry policy should be based on usable bars, not raw API row count. Add a 20-row/19-unique-row test.

### 9. New regression tests have vacuous success paths

- **Location:** `backend/tests/test_audit_deep_dive.py:119-187,190-212`
- **Problem:** The prior-session and forming-candle tests loop over `state.signals` without asserting that a candidate signal exists. The forming test supplies fewer than 20 bars, so strategy evaluation returns no signals. The missing-quote test mocks an entirely empty response, so the scan may be in `error` mode; it does not exercise a partial live response. All three can pass while the intended protection regresses.
- **Suggested solution:** Mock strategy evaluation to return a known candidate with controlled timestamp and setup, assert it appears in the resulting state with the intended confirmation flag, and return a valid quote for a second instrument in the partial-feed test.
- **Rationale:** A regression test must fail when the behavior it claims to protect is removed.

### 10. SQLite writes still run synchronously in the WebSocket callback

- **Location:** `backend/app/services/scanner_worker.py:252-258`; `backend/app/services/paper_trader.py:735-738`
- **Problem:** The new batch upsert reduces the number of transactions, but a changed position still performs SQLite I/O synchronously while the async WebSocket callback processes a tick. Under disk contention, this delays subsequent market ticks and stop/target handling.
- **Suggested solution:** Queue changed positions to a single persistence worker, or run the batch write in an executor with explicit ordering and shutdown flush. Measure tick-to-exit latency with delayed SQLite writes.
- **Rationale:** Batching improves throughput; moving disk I/O off the feed reader preserves responsiveness.

### 11. Failed trade actions are silent in the dashboard

- **Location:** `frontend/src/App.tsx:142-160,163-173`
- **Problem:** A rejected manual trade receives no user-visible message when `res.ok` is false; close likewise refreshes the portfolio without checking the close response. With the new server-side trade validation, a normal provisional or expired signal can appear to do nothing when Buy is clicked.
- **Suggested solution:** Read the API error payload for non-2xx responses and show a concise toast or inline message beside the action. Refresh the portfolio only after a successful close.
- **Rationale:** Users need to distinguish rejected trades from network problems and successful actions. Add a frontend test for an HTTP 400 trade rejection.

## ✅ Good Practices — What's done well

- **Bounded historical retries:** `backend/app/services/scanner_worker.py:465-477` introduces per-instrument backoff, reducing repeated failed requests. The post-dedup length check above would complete this safeguard.
- **Explicit data-source separation:** `backend/app/services/scanner_worker.py:958-977` now marks live forming-bar strategy results provisional and lets confirmed closed-bar results take precedence by signal ID.
- **Charge verification:** `backend/app/services/charges_calculator.py:67-71` and `backend/tests/test_audit_deep_dive.py:22-30` use an updated exchange-fee rate with a numeric test case, making P&L assumptions easier to audit.
- **Changed-row persistence:** `backend/app/services/paper_trader.py:436-451,722-738` avoids rewriting unchanged positions and batches changed rows, a useful reduction in SQLite work.

## Overall assessment

The fixes improve normal-path behavior and all automated checks pass. The remaining release risk is concentrated in write authorization, duplicated close behavior, server-versus-client signal trust, and asynchronous session invalidation. Address the critical issues and add tests that force each boundary condition before relying on live paper-trade results.
