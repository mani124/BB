# Follow-up code review — 11 October 2026

Scope: current `main` at `bdd85b8`, especially the F1–F9 fixes. Application code was not changed. Findings below are based on the current source; backend execution was unavailable because FastAPI is absent from the local offline dependency cache.

## 🔴 Critical Issues — Must fix before merge

### 1. A caller can bypass write authentication by supplying an allowed Origin

- **Location:** `backend/app/main.py:80-135`; `backend/app/core/config.py:21`; `backend/tests/test_audit_oct11.py:28-30`
- **Triggering scenario:** A direct HTTP client sends `Origin: http://localhost:5174` (or the listed production origin) with `POST /api/paper/reset`, `POST /api/auth/disconnect`, or another mutation. Direct clients can set this header freely. Even without an Origin, the fallback capability has a public hard-coded default.
- **Actual vs. expected:** The middleware accepts an allowed Origin without checking a session capability. The regression test explicitly expects this. Every mutation should require a server-issued, unguessable credential tied to an authorized dashboard session, regardless of Origin or Referer.
- **Suggested solution:** Move capability verification outside the Origin/Referer branches and remove the public fallback. For example:

  ```python
  if request.method in WRITE_METHODS:
      token = request.headers.get("X-Dashboard-Capability")
      if not token or not hmac.compare_digest(token, session_capability(request)):
          return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
      # Optionally validate Origin as an additional browser CSRF check.
  ```

  Issue the capability only after session authorization; do not expose it through a public GET endpoint. Test a spoofed allowed Origin and the documented default token from an unauthenticated direct client.
- **Rationale:** Origin and Referer identify a claimed request source, not a caller. The current F1 control therefore does not protect state mutations on any reachable deployment.

### 2. Reset can race with queued SQLite writes and resurrect deleted trades

- **Location:** `backend/app/services/paper_trader.py:112-142,258-261`; `backend/app/api/paper.py:170-172`; `backend/app/main.py:20-26`
- **Triggering scenario:** A scan queues a position upsert while the async persistence worker is delayed. A user then calls the synchronous `/api/paper/reset` endpoint, which FastAPI runs in a worker thread.
- **Actual vs. expected:** `_enqueue_write` sees no running event loop in that thread and calls `clear_all` immediately, outside the ordered queue. The earlier queued upsert may commit after the clear, so the response says reset succeeded while a trade reappears after restart. Reset and all other writes should share one total order and complete durably before success is reported.
- **Suggested solution:** Keep the event loop captured at worker startup and enqueue from other threads with `loop.call_soon_threadsafe`, then await a completion future for reset. An async endpoint with an awaited ordered storage operation is another option:

  ```python
  # Within the owning event loop:
  done = loop.create_future()
  await write_queue.put(("clear_all", None, done))
  await done  # resolve only after SQLite commit
  ```

  Add a test that blocks an upsert, calls reset from a thread, releases the upsert, and verifies the database is empty after flush and reload.
- **Rationale:** The queue currently orders only calls made on its owning event loop; dashboard writes bypass that guarantee.

## 🟡 Suggestions — Improvements to consider

### 3. Portfolio and live scan data are readable without a dashboard session

- **Location:** `backend/app/main.py:80`; `backend/app/api/paper.py:19-21`; `backend/app/api/signals.py:10-15,25-35`; `backend/app/api/auth.py:245-255`
- **Triggering scenario:** The API is reachable through its configured production proxy and a direct client sends `GET /api/paper/portfolio`, `GET /api/signals/state`, or subscribes to `/api/signals/stream` without a session.
- **Actual vs. expected:** The middleware checks only write methods, so these routes return trade history, P&L, scan state, and connection metadata to any reachable client. Private dashboard data should be returned only to an authorized session.
- **Suggested solution:** Apply one session dependency to private GET and SSE routes, including stream subscription, while leaving only genuinely public health information open. For example, `@router.get("/portfolio", dependencies=[Depends(require_dashboard_session)])`. Add anonymous-read and SSE tests through the production proxy.
- **Rationale:** Browser CORS does not stop `curl`, scripts, or server-to-server reads. This finding matters when the dashboard is exposed beyond a trusted local network.

### 4. Cached option-chain prices are stamped as new observations on every scan

- **Location:** `backend/app/services/scanner_worker.py:736-751,1097-1101,1135-1141,120-153`; `backend/app/api/paper.py:125-146`
- **Triggering scenario:** The option-chain fetch returns a quote at time T. Another scan uses that cached chain near T+15 seconds, then the next live fetch fails; a manual close occurs before T+30 seconds.
- **Actual vs. expected:** Each scan calls `record_option_quote`, which stamps the cached price with the current time. The close helper accepts it for another 15 seconds, so a roughly 30-second-old bid can pass a 15-second freshness limit. Freshness should be measured from the original chain observation.
- **Suggested solution:** Save an immutable `observed_at` with the chain cache and pass it into `OptionQuote`; do not refresh the quote timestamp when reading cached data. A close should use `time.time() - observed_at <= 15` and preferably require a current quote source for observed fills. Test cached-chain reuse followed by fetch failure and a close after 15 seconds from the original fetch.
- **Rationale:** Re-reading a cache does not make its market price new.

### 5. The 5-minute option-chart cache can freeze the forming bar and Setup 5 decision

- **Location:** `backend/app/services/scanner_worker.py:1317-1349`; `backend/app/services/option_chart_strategy.py:35-65,77-88`; `backend/tests/test_audit_oct11.py:289-322`
- **Triggering scenario:** The historical API returns an in-progress 5-minute option candle. Its close, high, or volume changes within the same slot while the option chain provides new ticks.
- **Actual vs. expected:** The entire DataFrame, including a forming bar when present, is reused until the next slot. The live-tick candle path runs only if the DataFrame is empty. Setup 5 can miss or retain a breakout for several minutes because indicators use a frozen last row. Completed bars may be cached, but a forming bar should update from current data; alternatively evaluate only completed bars and mark the signal confirmed accordingly.
- **Suggested solution:** Cache only rows whose candle interval has completed, then merge or update the current slot from live quotes before calculating indicators. For example, `completed = df[df.timestamp < current_slot_ts]`, then append a separately maintained live forming candle. Test two quotes in one slot that cross the breakout and volume thresholds while asserting only one historical API call.
- **Rationale:** The performance optimization must not make signal inputs stale inside the very window being scanned.

### 6. The first quote after seeding today's bars drops current-slot volume

- **Location:** `backend/app/services/scanner_worker.py:638-652,658-697`
- **Triggering scenario:** On startup, historical data contains completed bars from today but not the current forming bar. The first live quote reports cumulative session volume greater than the sum of those completed bars.
- **Actual vs. expected:** `has_today_bars` sets the first increment to zero, discarding all trading volume since the last completed bar. The forming candle, VWAP, and volume filters are understated. The baseline should subtract volume already represented by today's history from the first cumulative quote and allocate the remainder to the forming slot.
- **Suggested solution:** Establish a session-volume baseline from today's seeded bars, then compute `max(0, quote_cumulative_volume - seeded_session_volume)`, accounting for any seeded forming bar and provider volume semantics. Add startup tests for both prior-session-only history and today's completed bars with a partial current slot.
- **Rationale:** Today's history being present does not mean the latest quote's cumulative volume is fully represented.

### 7. Storage errors are logged but still reported as flushed

- **Location:** `backend/app/services/paper_trader.py:93-125,156-158`
- **Triggering scenario:** SQLite rejects a write because the disk is full, the database is locked, or a row is invalid.
- **Actual vs. expected:** `_execute_storage_op` catches the error and returns; the worker calls `task_done`, so `flush()` and shutdown proceed as though persistence succeeded. The in-memory portfolio can diverge permanently from disk. A failed write should remain observable and either retry with bounded backoff or make flush/reset report failure.
- **Suggested solution:** Have `_execute_storage_op` return or raise a result to the queue worker, complete an operation future with the exception, and surface unresolved failures in `flush()`. Test with a storage stub that raises and assert the caller receives a failure rather than a successful flush.
- **Rationale:** A durability boundary needs an explicit success or failure signal.

### 8. Public close requests can still alter modeled slippage analytics

- **Location:** `backend/app/api/paper.py:98-108,141-157`; `backend/app/api/signals.py:76-94`; `backend/app/services/paper_trader.py:818-831,451-487`
- **Triggering scenario:** A caller closes an unquoted live position and supplies an arbitrary positive `exit_price` (for example ₹100,000) in either close route.
- **Actual vs. expected:** The live fill remains the last known server price, but the supplied value becomes `theoretical_exit`; it inflates `exit_slippage` and `total_slippage_cost`. All recorded pricing analytics for live trades should come from server-owned observations or an explicitly labeled, validated modeling workflow.
- **Suggested solution:** Remove `exit_price` from the ordinary close schema and derive theoretical exit from the server's last observed price. If modeled exits are a supported feature, make them a separate route or mode and label their analytics separately. Test that changing request price fields cannot change fill, theoretical exit, or slippage.
- **Rationale:** The F2 fill fix closes P&L inflation, but leaves a client-controlled input in trading metrics.

## ✅ Good Practices — What's done well

- `backend/app/services/scanner_worker.py:1204-1220` checks session generation again after the subscription await, protecting the final state publication path during disconnect.
- `backend/app/services/scanner_worker.py:120-153` holds option price, bid, timestamp, and source in one `OptionQuote` record, removing the earlier separate-store mismatch for new observations.
- `backend/app/api/paper.py:52-79` requires a live manual trade to match a current radar signal and rechecks server-side confirmation.
- `backend/app/services/paper_trader.py:112-125` offloads queued SQLite operations from the event loop, and `backend/app/services/scanner_worker.py:1322-1339` avoids repeated successful chart downloads within a slot.
- The new `backend/tests/test_audit_oct11.py` covers direct-client capability handling, forged fills, disconnect barriers, and cache reuse. The cases above identify missing adversarial and lifecycle scenarios.

## Verification and executive summary

- Frontend: 23 tests passed; production build passed.
- Backend: tests did not start because the local offline `uv` cache lacks FastAPI. No backend result is claimed.
- The highest risk is write access via spoofed Origin and a persistence ordering race that can undo reset. Quote-age and chart-cache behavior can also misstate live trading decisions. **Overall risk: 8/10.**
