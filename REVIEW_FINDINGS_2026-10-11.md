# Code review — 11 October 2026

Reviewed `main` at `c76d9ea`, including the fixes since `d215ae8` and their surrounding backend and frontend paths. This is a diagnostic report; application code was not changed. Verification: **247 backend tests passed**, **23 frontend tests passed**, and the frontend production build succeeded.

## 🔴 Critical Issues — Must fix before merge

### 1. Write routes remain callable without authentication

- **Location:** `backend/app/main.py:75-112`; `backend/app/api/paper.py:155-168`; `backend/app/api/auth.py:254-258`
- **Problem:** The origin middleware explicitly allows requests with neither `Origin` nor `Referer`, and no write route requires a session credential. A harmless invalid-body probe reached the route and returned 422 without an origin, while a foreign origin returned 403. A direct HTTP client can therefore reset the portfolio, change settings, close positions, or disconnect the Dhan session if it can reach the API. The new production-origin allowlist and deployment URLs make this boundary especially important when a reverse proxy exposes the loopback service.
- **Suggested solution:** Require an unguessable session capability or authenticated user session for all mutations, independently of Origin checks. Keep Origin validation as browser request protection. For example:

  ```python
  @router.post("/reset", dependencies=[Depends(require_dashboard_session)])
  def reset_portfolio(): ...
  ```

- **Rationale:** `Origin` is not a client identity and is absent or freely settable in non-browser HTTP requests. Add a test that a no-Origin request without a capability is denied, including through the production proxy.

### 2. Both close routes still accept arbitrary caller-supplied fill prices

- **Location:** `backend/app/api/paper.py:89-152`; `backend/app/api/signals.py:76-105`; `backend/app/services/paper_trader.py:375-400`
- **Problem:** The shared helper makes the routes consistent, but it forwards request fields `real_bid_price`, `real_opt_price`, and `exit_price` without verifying them against server-observed quotes. A positive `real_bid_price` skips the modeled label and becomes the fill price directly; for example, a caller can close an option bought at ₹100 using a submitted bid of ₹10,000 and inflate realized paper P&L. Even when a stale `real_opt_price` receives a modeled label, the engine still uses that submitted number as the fill.
- **Suggested solution:** Remove observed-market-price fields from public close requests. Look up the current quote by the position's security ID, validate its age, and pass only that server-owned quote to the engine. If unquoted manual exits are allowed, accept a separately named *modeled* price and persist its source explicitly:

  ```python
  quote = quote_store.get_fresh(position.option_security_id, max_age_s=15)
  engine.close_position(position_id, real_bid_price=quote.bid if quote else None)
  ```

- **Rationale:** A user action may request an exit; it cannot attest to an exchange bid. Test both close routes with a forged bid and a stale submitted option price.

### 3. An explicit `feed_mode=live` can trade old radar signals after logout

- **Location:** `backend/app/api/paper.py:32-84`; `backend/app/services/scanner_worker.py:352-389`
- **Problem:** The route honors `body.feed_mode` before deriving mode from the worker. Disconnect clears credentials and sets demo mode, but does not clear `_state.signals`. A request that explicitly sets `feed_mode="live"` can still find a previously confirmed live signal by ID, pass its stored quote fields, and create a new position labeled live after logout. The route does not require current credentials or a fresh scan/quote when explicit mode is supplied.
- **Suggested solution:** Derive live/demo mode exclusively from server state, reject live entries when credentials or feed health are absent, and expire or clear live radar signals when the session generation changes. For example:

  ```python
  if worker._session_credentials is None or worker.get_state().active_mode != "live":
      raise HTTPException(409, "Live feed unavailable")
  ```

- **Rationale:** Client input must not select the trust level of a paper trade. Test disconnect followed by a POST for an old confirmed signal ID with `feed_mode="live"`.

### 4. Manual close can pair a fresh chain timestamp with an old candle price

- **Location:** `backend/app/services/scanner_worker.py:1033-1043`; `backend/app/api/paper.py:118-126`
- **Problem:** A positive option-chain LTP refreshes `_option_last_quote_time`, but the close helper reads the fill from a different store, `_option_forming_candle[sec_id]["close"]`. The option-chain update does not update that candle. If the candle's last tick is old, a fresh chain response makes its stale close look fresh and records it as an observed fill. Conversely, a fresh chain LTP with no forming candle is ignored.
- **Suggested solution:** Store price, bid, source, and receipt time as one quote record and have manual close consume that same record. If using the candle store, freshness must be tied to the candle's own last update, not to a separate chain timestamp:

  ```python
  latest_quotes[sec_id] = Quote(ltp=ltp, bid=bid, received_at=monotonic())
  ```

- **Rationale:** Freshness and price must describe the same observation. Test a stale candle plus a new positive chain quote at a different price.

### 5. An in-flight scan can publish old-session results after disconnect

- **Location:** `backend/app/services/scanner_worker.py:1113-1138`
- **Problem:** The generation is checked before trade mutation, but the scan then awaits `_subscribe_active_positions` at line 1123. If disconnect happens during that await, the scan resumes and writes its captured live signals, live-only portfolio view, and scan timestamp at lines 1126-1138 without another generation check. The mode remains demo, but its published data can come from the disconnected session. Earlier return branches at lines 1023 and 1092 also leave `is_scanning=True` until a later scan runs.
- **Suggested solution:** Use one abort helper that restores a coherent state and check the generation immediately after every await, especially after the subscription. Put `is_scanning=False` in a `finally` block:

  ```python
  await self._subscribe_active_positions()
  if gen != self._session_generation:
      return self._state
  ```

- **Rationale:** Cancellation and generation guards must cover the final state publication path. Test disconnect while subscription is paused and assert that no old-session signals or portfolio snapshot are published and `is_scanning` is false.

## 🟡 Suggestions — Improvements to consider

### 6. Cumulative volume is lost when history contains only prior-session bars

- **Location:** `backend/app/services/scanner_worker.py:580-586`
- **Problem:** On the first quote after seeding, the code sets the volume increment to zero whenever `_candle_history[symbol]` is nonempty. That history may contain only earlier-session bars from the five-day API window. In that case, the first current-session quote's cumulative volume is omitted from today's forming candle, biasing VWAP and volume filters until later quotes accrue.
- **Suggested solution:** Base the initial volume offset on the sum or final cumulative volume of **current-session** seeded bars. When there are none, initialize today's first bar from the quote's cumulative volume. Test startup at market open with 20 yesterday bars and a first quote with nonzero volume.
- **Rationale:** “History exists” does not mean today's volume is represented.

### 7. Disconnect tests do not establish that in-flight work was aborted

- **Location:** `backend/tests/test_audit_deep_dive.py:632-680`
- **Problem:** The test pauses a scan by disconnecting inside an option-chart mock, but its final assertion checks only that credentials are `None`, which the mock itself set. It does not assert that `update_market_prices` or automatic trading was skipped, that `active_mode` stayed demo, or that `is_scanning` was cleared. The connection-cancellation part also cancels a task before the fake connect is guaranteed to start.
- **Suggested solution:** Use `asyncio.Event` barriers to prove each await was entered, disconnect from the test task, then release it. Assert no trade update, no live state publication, a closed or canceled WebSocket, and coherent scan flags.
- **Rationale:** A race test should fail if the scan ignores the disconnect.

### 8. Database writes still block the WebSocket reader

- **Location:** `backend/app/services/scanner_worker.py:253-258`; `backend/app/services/paper_trader.py:735-738`
- **Problem:** Changed rows are batched, which reduces transactions, but `batch_upsert_positions` still runs synchronously inside an async tick callback. Slow disk commits delay subsequent ticks and stop/target checks.
- **Suggested solution:** Queue changed positions to one ordered persistence worker, or run the transaction in a dedicated executor and flush it on shutdown. Measure tick-to-exit latency with an intentionally delayed SQLite commit.
- **Rationale:** The market-data path should not wait on storage latency.

### 9. Successful option charts are fetched on every scan

- **Location:** `backend/app/services/scanner_worker.py:1227-1243,1277-1283`
- **Problem:** `_can_retry_contract_candle` throttles only failed contract fetches. A successful CE or PE chart is fetched again for every deep-scan instrument on the next cycle. These requests run sequentially inside a nominal three-second scan; as the deep-scan universe grows, repeated five-day chart downloads can dominate the cycle, consume API quota, and delay signals for later instruments.
- **Suggested solution:** Cache successful contract bars by security ID and last completed 5-minute slot, then update the forming bar from live quotes. Refresh historical bars only when a new slot closes or a gap is detected. Add a two-cycle test asserting no duplicate historical requests within one slot.
- **Rationale:** Completed chart history is immutable between slot boundaries; re-downloading it every scan adds latency without new information.

## ✅ Good Practices — What's done well

- **Exact browser origin comparison:** `backend/app/main.py:38-62,73-108` removed the prior wildcard suffix and rejects `Origin: null`, closing the tested browser-origin bypass.
- **Server confirmation recheck:** `backend/app/api/paper.py:43-70` now resolves a matching radar signal and rejects it when the server marks it provisional.
- **Historical bar separation:** `backend/app/services/scanner_worker.py:506-547` parses and deduplicates timestamps, keeps unfinished bars out of completed history, and backs off when fewer than 20 usable bars remain.
- **Visible action errors:** `frontend/src/App.tsx:151-196` now displays rejected trade and close responses instead of silently swallowing them.

## Overall assessment

The latest changes address much of the previous review, and the test suite remains green. The remaining high-impact problems concern authorization, who controls recorded prices and live mode, and asynchronous state publication after logout. The suggestions focus on volume accuracy, race-test quality, and feed responsiveness.
