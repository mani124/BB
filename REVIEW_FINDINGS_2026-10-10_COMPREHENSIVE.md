# Comprehensive dashboard code review — 10 October 2026

Reviewed the full platform at commit `4b299d1`: backend APIs, Dhan HTTP and WebSocket integrations, scanner, indicators, strategies, option selection, paper trading and persistence, frontend integration, launcher, and tests. The prior 15-finding fix commit was included. This review is read-only; no application code was changed. Findings below are present in the current code and ordered by impact.

## Critical

### C1. The default launcher exposes unauthenticated portfolio controls on the local network

**Locations:** `run_dashboard.sh:126-130`; `frontend/vite.config.ts:7-14`; `backend/app/api/paper.py:19-79`; `backend/app/api/auth.py:221-225`.

`npm run dev -- --host` makes Vite listen on all interfaces and its `/api` proxy forwards requests to the backend. The portfolio trade, close, settings, and reset endpoints require no user authentication. Another device that can reach port 5174 can change or erase the paper journal; it can also disconnect the shared Dhan session. The backend's loopback bind does not prevent access through Vite's proxy. Bind the frontend to loopback by default and protect state-changing endpoints if network access is intended.

## High

### H1. Live trades can still start from an invented option entry price

**Locations:** `backend/app/services/strike_selector.py:376-387,433-444`; `backend/app/services/scanner_worker.py:870-912`; `backend/app/services/paper_trader.py:238-275`.

When the selected contract is missing from a live option chain, strike resolution returns the estimated recommendation. The scanner retains the signal and the live auto-trader can open a position whose `option_entry` is that estimate. Even when a contract is present, a zero ask and zero LTP lead to `estimate_option_entry`. Later live valuation no longer synthesizes ticks, but initial risk and eventual P&L remain anchored to an unobserved entry. Require a resolved contract and a usable live quote before recording a live fill.

### H2. `WS_LIVE` scanning drops the current WebSocket candle when HTTP quotes fail

**Locations:** `backend/app/services/scanner_worker.py:256-267,445-448,618-638,729-745`.

WebSocket ticks update the forming candle, but `get_or_update_live_candles` returns only completed history whenever that scan has no HTTP quote. WebSocket health still selects `WS_LIVE`, so indicators and signals omit the newest tick-driven bar; radar values may regress to the last completed close. With no completed bar yet, the scan sees an empty frame despite active WebSocket ticks. Include the forming candle in the WebSocket-backed scan path and track quote freshness for each instrument.

### H3. Target 1 can book a live partial exit at a stale option price

**Locations:** `backend/app/services/scanner_worker.py:274-281`; `backend/app/services/paper_trader.py:601-617,662-679`.

A spot tick calls `update_market_prices` without an option quote. If spot crosses Target 1, the code marks `TARGET_1`, sells lots at `pos.current_option_price`, books realized P&L, and trails the stop. It does not check `has_fresh_quote`, unlike the stop and Target 2 branches. The recorded sale can use the entry price or a much older option tick. Hold a pending Target 1 trigger until a fresh bid or explicitly modeled quote is available.

### H4. Live underlying strategies cannot run promptly after launch or restart

**Locations:** `backend/app/services/scanner_worker.py:452-495,729-814`; `backend/app/services/strategy_engine.py:48-50`.

Underlying candle history starts empty and is built only from ticks or polled LTP; the scanner never seeds it with the historical-candle method already available in `dhan_client.py`. All underlying setups require at least 20 bars. After an intraday restart, 5-minute symbols need about 95 minutes of new bars before the scanner can emit a signal, and 15-minute symbols need about 285 minutes. Seed valid current-session historical OHLCV bars before evaluating strategies.

### H5. The OAuth app secret is sent in an HTTP GET URL

**Locations:** `frontend/src/context/DhanAuthContext.tsx:148-162`; `backend/app/api/auth.py:24-40`; `run_dashboard.sh:126-130`.

The browser places `app_secret` in the `/api/auth/oauth/login-url?...` query string. Request URLs are routinely captured by server and proxy logs and can be observed in transit when the dashboard is served over plain HTTP, including the launcher’s network-facing Vite server. The secret is used only to generate consent and need not be in the URL. Send it in a POST body over a protected local or HTTPS channel and avoid logging upstream error bodies that may echo request details.

### H6. A new candle is marked confirmed because the previous candle closed

**Locations:** `backend/app/services/scanner_worker.py:477-495,809-825,899-912`; `backend/app/services/strategy_engine.py:419-460`.

When a bar rolls over, `get_or_update_live_candles` appends the old bar, creates a new one from the first tick, and sets `_bar_completed_symbols`. The scanner evaluates `evaluate_signals` on the *new forming bar* but marks its Setups 6–8 signals `is_confirmed=True` because the symbol appears in that set. A first tick that crosses the previous inside bar's high or low can thus confirm Setup 7 immediately, even if the new candle later closes back inside. The auto-trader can enter on an unconfirmed new bar despite the confirmation gate. Evaluate the just-closed bar for confirmation, or defer the forming-bar signal until its own close.

## Medium

### M1. Restart drops pending live exits and partial-exit slippage

**Locations:** `backend/app/services/paper_trader.py:40-45,390-396,482-500`; `backend/app/services/paper_storage.py:27-85,107-156,159-197`.

`PaperPosition` has `pending_spot_exit` and `booked_slippage_cost`, but neither is a SQLite column or upserted value. A restart forgets a live spot exit waiting for an option quote and resets booked slippage to zero, understating final slippage accounting. Add both fields to the schema, migrations, insert/update, and load path.

### M2. Manual Paper Buy accepts provisional signals and can misclassify live trades as demo

**Locations:** `frontend/src/components/SignalCard.tsx:212-217`; `backend/app/api/paper.py:9-40`; `backend/app/services/scanner_worker.py:335,809-825`; `backend/app/services/paper_trader.py:338-350`.

The automatic trader skips `is_confirmed=False`, but the manual route accepts the client-supplied signal without that check. Its mode fallback reads `worker.active_mode`, which does not exist; the real value is `worker._state.active_mode`. An unquoted live signal can therefore be saved as a demo position, while the visible Paper Buy button can bypass candle confirmation. Resolve the signal and mode from server state and apply the same confirmation and live-quote checks to manual entry.

### M3. Live underlying bars carry zero volume, so computed VWAP is not a session VWAP

**Locations:** `backend/app/services/scanner_worker.py:456-493,736-748`; `backend/app/services/indicators.py:77-88`.

New and rolled underlying bars set `volume` to zero and the update branch never reads the quote or tick volume. `calculate_indicators` then divides by zero cumulative volume and replaces VWAP with each candle's typical price. The latest row is corrected only when the HTTP quote contains a positive `average_price`; WebSocket-only or missing-average-price scans keep the fabricated VWAP. VWAP filters and market bias can change as a result. Populate actual per-bar volume or mark VWAP unavailable until a verified source provides it.

### M4. Missing opening-range candles are replaced by unrelated bars

**Locations:** `backend/app/services/indicators.py:150-174`; `backend/app/services/strategy_engine.py:273-327`.

If the latest session has no 09:15–09:30 bars, the indicator function sets opening-range high and low from the first three rows of the entire frame. Following a late start or partial history, those rows may be from another time or day, yet Setup 4 treats them as a valid opening range during its 09:30–11:30 window. Return unavailable opening-range values when the actual session window is missing and suppress ORB signals until the range is observed.

### M5. Manual live close can record the last observed option price as a fresh fill

**Locations:** `frontend/src/App.tsx:163-170`; `backend/app/api/paper.py:49-63`; `backend/app/services/paper_trader.py:362-374,685-711`.

The dashboard's Close action sends no quote. `close_position` therefore uses `pos.current_option_price`, and `_finalize_closed_position` records that value for a live position even when no fresh bid or LTP is supplied. A manual close during an option feed outage can produce a realized fill at a stale price. Ask for an explicit simulation price or obtain a fresh market quote before recording a live paper fill, and label any modeled price accordingly.

## Verification and limits

- Backend: 214 tests passed with the existing offline dependency cache; one Starlette/httpx deprecation warning.
- Frontend: 23 tests passed; `npm run build` succeeded.
- No live Dhan credentials or exchange feed were used. Feed findings come from current control flow, and external order execution is outside this paper-trading platform.
- The bundled F&O universe and lot-size file were inspected for static-data risk, but individual current contract sizes were not independently verified against the live NSE master. No unverified stale-lot claim is made here.

**Codex review verdict:** REVISE. The review and this consolidated report made no application-code changes.
