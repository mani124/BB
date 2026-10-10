# Comprehensive code review findings

Reviewed current `main` at `d58c89f` on 2026-10-10. Scope: backend, frontend, launcher, tests, and the latest committed changes. This is a diagnostic review; no application code was changed. The backend suite passed (223 tests), the frontend suite passed (23 tests), and the frontend build succeeded. Passing tests do not cover the scenarios below.

## Findings

### 1. Prior-session history can open a new live trade

- **Severity:** High
- **Location:** `backend/app/services/scanner_worker.py:467`
- **Triggering Input / Scenario:** Start or restart the dashboard when Dhan's five-day intraday response has at least 20 bars but its last bar is from an earlier trading session, or contains a still-forming bar. A setup is present on that last bar and the feed is otherwise live.
- **Actual Behavior vs. Expected Behavior:** `seed_historical_candles_if_needed` accepts every returned row without checking its session, ordering, or completion. At `scanner_worker.py:878-892`, the last stored row is evaluated as a confirmed signal and can reach automatic trading. A past or unfinished bar can therefore create a current live position. Only a completed, current-session signal should be eligible for a new live trade; older bars may be retained solely as indicator warm-up data.
- **Suggested Remediation:** Normalize timestamps to the exchange timezone, sort and deduplicate bars, separate warm-up history from eligible signal bars, and require the signal bar to belong to the active session and to have ended before marking it confirmed. Add a restart test with 20 prior-day bars plus an incomplete current bar.

### 2. Setup 5 labels a historical option close as a live quote

- **Severity:** High
- **Location:** `backend/app/services/option_chart_strategy.py:93`
- **Triggering Input / Scenario:** The option intraday API returns a nonempty chart whose last breakout candle is from an earlier session; `scanner_worker.py:1113-1148` passes it into Setup 5.
- **Actual Behavior vs. Expected Behavior:** The chart close becomes `real_ltp` and `is_live_quote=True` (`option_chart_strategy.py:102-103`). The live entry gate in `paper_trader.py:239-250` accepts these fields, so a position can be booked from an old candle at a historical premium. A current contract quote should determine the live fill, with chart data used only to detect a time-valid setup.
- **Suggested Remediation:** Check the option candle's session and completion time, and obtain a separately timestamped current ask or LTP for the selected security ID before allowing a live entry. Test a previous-session breakout paired with a healthy current underlying feed.

### 3. Forming-bar setups 1–4 are marked confirmed and can auto-trade

- **Severity:** High
- **Location:** `backend/app/services/scanner_worker.py:902`
- **Triggering Input / Scenario:** During an unfinished 5-minute or 15-minute candle, price briefly crosses a Bollinger or opening-range threshold and then falls back before the candle closes.
- **Actual Behavior vs. Expected Behavior:** `evaluate_signals` runs on `ind_df`, which includes the forming candle; only setups 6–8 are marked provisional. Setups 1–4 receive `is_confirmed=True` at line 911, and `paper_trader.py:351-363` can trade them immediately. Their signal can disappear at the actual close. Setups described by candle-close conditions should become confirmed only after that bar finishes.
- **Suggested Remediation:** Derive confirmation from the evaluated bar's completion state for every setup; keep all forming-bar signals provisional, or explicitly designate and test intrabar strategies. Add a test where an intrabar breakout reverses before close and must not open a trade.

### 4. A missing instrument quote can trigger an exit from an old spot price

- **Severity:** High
- **Location:** `backend/app/services/scanner_worker.py:803`
- **Triggering Input / Scenario:** A partial HTTP marketfeed response omits one held underlying, while another quote or the WebSocket keeps the scan in live mode.
- **Actual Behavior vs. Expected Behavior:** Lines 806–814 fall back to the last forming or historical close and insert it into `price_map`. At lines 997–1002, the paper engine treats that value as the current spot for stop and target decisions. A pending exit may be created, or an exit executed if a fresh option quote is available. Exit decisions should use a fresh quote for that specific underlying, not merely a globally healthy feed.
- **Suggested Remediation:** Track quote age per security ID and omit missing or stale symbols from the trade-update map. Keep historical closes available for charting only. Test a partial marketfeed response with a held position at a stop boundary.

### 5. Manual live entry trusts caller-supplied signal and quote fields

- **Severity:** High
- **Location:** `backend/app/api/paper.py:9`
- **Triggering Input / Scenario:** A caller posts an old or fabricated `Signal` with `is_confirmed=true`, an `option_security_id`, and `is_live_quote=true` or an arbitrary positive `real_ask_price`.
- **Actual Behavior vs. Expected Behavior:** Lines 41–59 validate fields from the request itself and pass the full object to the paper engine. The engine can record a live trade and P&L at a caller-chosen premium without checking the current scanner signal, contract, quote, or timestamp. The server should resolve and validate these values from its own current state.
- **Suggested Remediation:** Accept a signal ID and desired lot count only. Resolve the signal and current contract quote on the server, enforce a maximum quote age, and calculate price and lot size there. Test forged confirmation, stale signal ID, wrong contract, and forged premium.

### 6. Disconnect can be undone by an in-flight scan

- **Severity:** Medium
- **Location:** `backend/app/services/scanner_worker.py:640`
- **Triggering Input / Scenario:** Disconnect while a scan is awaiting the marketfeed, historical candle, or option-chain API.
- **Actual Behavior vs. Expected Behavior:** The scan retains `cid` and `tok` captured before the await. `set_session_credentials(None, None)` changes the state to demo at lines 351–360, but the older scan can resume, set `active_mode` back to live at lines 682–702, issue more requests with the old token, and publish or auto-trade live signals. A completed disconnect should prevent older work from restoring live state.
- **Suggested Remediation:** Give each credential session a generation number; invalidate it on disconnect and verify it after each awaited operation and before state updates or trade creation. Cancel or drain the active scan on disconnect. Test a scan paused at an awaited request while disconnect occurs.

### 7. State-changing local API routes have no origin or authorization check

- **Severity:** Medium
- **Location:** `backend/app/api/paper.py:114`
- **Triggering Input / Scenario:** Another local process, or a browser request from an unrelated origin, sends a POST to `/api/paper/reset`, `/api/paper/settings`, `/api/paper/close/{id}`, or `/api/auth/disconnect`.
- **Actual Behavior vs. Expected Behavior:** These endpoints change the shared journal or session without checking a session capability, request origin, or CSRF token. The CORS allowlist in `backend/app/main.py:33-44` governs reading cross-origin responses; it is not a write authorization check. The launcher binding to loopback limits network reach but does not protect against local requests or browser-origin writes. Only the dashboard's authorized session should be able to mutate state.
- **Suggested Remediation:** Require a server-issued session capability or equivalent authorization for mutations, and validate `Origin`/`Host` (or a CSRF token) for browser requests. Cover unauthorized form-style POSTs and direct calls in API tests.

### 8. Volume-less ticker packets reset the cumulative volume baseline

- **Severity:** Medium
- **Location:** `backend/app/services/scanner_worker.py:211`
- **Triggering Input / Scenario:** A Dhan response-code-2 ticker packet arrives between response-code-4 quote packets. The codec at `backend/app/services/dhan_packet_codec.py:188-200` correctly omits volume from ticker packets.
- **Actual Behavior vs. Expected Behavior:** Missing volume is converted to zero and passed to `get_or_update_live_candles`. At `scanner_worker.py:513`, zero replaces `_last_cumulative_volume`; the next quote adds the entire day's cumulative volume to the current candle. VWAP and volume-based filters then use inflated data. A packet without volume should update price without changing the volume baseline.
- **Suggested Remediation:** Preserve `None` for absent volume and update `_last_cumulative_volume` only when a real cumulative volume is present. Test the sequence quote(volume=1000), ticker(no volume), quote(volume=1010): the last increment must be 10.

### 9. The first quote adds its cumulative volume to a candle twice

- **Severity:** Medium
- **Location:** `backend/app/services/scanner_worker.py:519`
- **Triggering Input / Scenario:** First nonzero cumulative-volume quote for an instrument after startup or a session reset.
- **Actual Behavior vs. Expected Behavior:** The new forming candle initializes `volume` to `incremental_vol` at line 529 and, in the same call, the `else` branch adds `incremental_vol` again at line 556. For an initial reported volume of 1,000, the forming candle starts at 2,000 even before considering overlap with seeded history. The current bar should receive each observed increment once.
- **Suggested Remediation:** Return after initialization or initialize volume to zero and let the common update path add the increment once. Initialize the cumulative baseline from compatible current-session history, if present. Test the first quote and restart-with-history cases.

### 10. Exchange transaction fee is calculated using a stale rate

- **Severity:** Medium
- **Location:** `backend/app/services/charges_calculator.py:70`
- **Triggering Input / Scenario:** Any NSE equity-option round trip whose premium turnover is used to calculate displayed charges and net P&L.
- **Actual Behavior vs. Expected Behavior:** The code applies 0.05% to total premium turnover. The [NSE circular effective 1 March 2026](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf) specifies ₹3,552.99 per crore for equity-option transaction charges, approximately 0.0355299% (₹3,553 per crore including the stated IPFT contribution). For ₹100,000 turnover, the code charges ₹50 instead of approximately ₹35.53 before GST, understating net P&L by about ₹17.07 after GST. The existing test at `backend/tests/test_charges_calculator.py:16` asserts the stale result.
- **Suggested Remediation:** Use a dated, cited fee schedule with the applicable NSE transaction rate and IPFT treatment, then update independent golden-value tests for turnover, GST, and net P&L. Keep the 2026 STT rate separately; it is already 0.15% in code.

### 11. Manual close can treat an old option candle as a fresh fill

- **Severity:** Medium
- **Location:** `backend/app/api/paper.py:83`
- **Triggering Input / Scenario:** A user closes a live position after option ticks have stopped, while `_option_forming_candle` still contains a previous `close`.
- **Actual Behavior vs. Expected Behavior:** The route uses that cached close as `real_opt_price` without checking the candle timestamp or last tick time. It therefore bypasses the `"(Modeled: Unquoted)"` label at lines 89–91 and may record a stale price as an observed fill. The close should either use a current quote or clearly identify the modeled/unquoted result.
- **Suggested Remediation:** Store the last option quote timestamp separately, apply a short freshness limit, and only pass `real_opt_price` when it meets that limit. Test manual close after the option feed stalls.

### 12. A public diagnostic endpoint uses live credentials for repeated upstream calls

- **Severity:** Medium
- **Location:** `backend/app/main.py:55`
- **Triggering Input / Scenario:** Repeated GETs to `/api/debug-dhan` while a Dhan session is connected.
- **Actual Behavior vs. Expected Behavior:** The route performs nine upstream probes with active credentials at lines 67–111, outside the normal Dhan client throttle, including a synchronous SDK call. It returns snippets of upstream bodies and can consume request quota or stall the server; its fixed October 2026 probe dates also become stale. Diagnostic probes should not be available as a normal unauthenticated application route.
- **Suggested Remediation:** Remove the route from normal startup or gate it behind explicit local diagnostic authorization and rate limiting. Use configurable current dates if retained. Add an API test that normal clients cannot invoke it.

### 13. The legacy OAuth GET route still accepts an app secret in a URL

- **Severity:** Medium
- **Location:** `backend/app/api/auth.py:99`
- **Triggering Input / Scenario:** A caller uses `/api/auth/oauth/login-url?app_id=...&app_secret=...` instead of the new POST route.
- **Actual Behavior vs. Expected Behavior:** The secret appears in the request URL and can be retained by browser history, URL logging, or intermediary diagnostics. The frontend now uses POST, but the server still accepts and documents the unsafe GET form. Secrets should enter through a request body only.
- **Suggested Remediation:** Remove the GET route, or reject any GET with `app_secret` and direct callers to POST. Test that secret-bearing GET requests cannot succeed.

### 14. Every option tick synchronously rewrites all active positions

- **Severity:** Medium
- **Location:** `backend/app/services/paper_trader.py:719`
- **Triggering Input / Scenario:** Frequent WebSocket option ticks with multiple active positions.
- **Actual Behavior vs. Expected Behavior:** `scanner_worker.py:247-253` invokes `update_market_prices` for each tick. That method iterates all active positions and calls `upsert_position` for every survivor at lines 719–723. `paper_storage.py:113-168` opens and commits a SQLite transaction per position. The synchronous work runs within the WebSocket callback and grows with both tick rate and portfolio size, delaying later ticks and exits even for unrelated positions. Only affected rows should be persisted, preferably in a batch or off the reader path.
- **Suggested Remediation:** Track changed positions, batch their writes in one transaction, and schedule persistence away from the socket reader. Add a multi-position tick-throughput test that verifies unrelated rows are not rewritten.

### 15. Failed historical seeding is retried for every instrument on every scan

- **Severity:** Medium
- **Location:** `backend/app/services/scanner_worker.py:800`
- **Triggering Input / Scenario:** A live instrument repeatedly returns an empty/error intraday response or fewer than 20 bars.
- **Actual Behavior vs. Expected Behavior:** Each approximately three-second scan awaits `seed_historical_candles_if_needed` again for that instrument, without a retry timer or negative cache. The deep-scan loop does this sequentially, so multiple failures consume Dhan quota and defer later instruments and state broadcasts. Failures should be retried with bounded backoff while live quotes and existing charts continue.
- **Suggested Remediation:** Keep per-instrument last-attempt time and exponential backoff with a cap; reset after success or a new session. Add a test for repeated empty responses across several scan cycles and assert bounded upstream calls.

## Executive summary

The main risk is trade and P&L integrity: stale historical bars and option prices can be promoted to live signals or fills, forming bars can auto-trade before confirmation, and manual entry trusts client-supplied market facts. Volume accounting and the exchange-fee rate also distort calculations. The passing tests mostly cover normal paths and do not exercise the listed timing, stale-data, adversarial-request, or throughput cases.

**Overall risk score: 8/10.**
