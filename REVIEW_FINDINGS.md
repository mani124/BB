# Code review findings

Reviewed 9 October 2026. Scope: current repository (clean working tree), with emphasis on signal calculations, broker data, paper trading, and displayed data freshness. No application code was changed.

## High severity

1. **Invented candles feed live-mode indicators and signals.** `backend/app/services/scanner_worker.py:209-234` creates 20 flat candles at the previous close and an opening candle from a day-wide quote when a live instrument is first seen. `scanner_worker.py:447-525` then calculates Bollinger Bands, RSI, ADX, radar state, and signals from them. A valid live quote is enough to trigger this path. Indicators and paper entries can therefore depend on synthetic prices while the mode says live. Seed with actual historical candles, or wait for enough observed bars before evaluating setups.

2. **The opening range includes later day extremes.** `backend/app/services/scanner_worker.py:225-234` assigns the quote's day high and low to a candle timestamped 09:15; `backend/app/services/indicators.py:152-166` treats it as the 09:15–09:30 opening range. If the first scan occurs after 09:30, Setup 4 in `backend/app/services/strategy_engine.py:285-308` compares against a range that can include the rest of the day, suppressing valid breakouts. Build the range from actual 09:15–09:30 candles.

3. **Live candle history does not reset between trading days.** `backend/app/services/scanner_worker.py:208-255` initializes history only when absent and advances an old forming candle by one interval even after an overnight gap. A worker kept running overnight puts new quotes on yesterday's candle timestamps; the signal cutoff at `backend/app/services/strategy_engine.py:70-74` can then suppress new entries. Reset or reload candle history at each session boundary and handle missed intervals.

4. **Live paper P&L and exits can use a made-up option price.** When a spot quote exists but an option quote does not, `backend/app/services/paper_trader.py:263-283` estimates the option premium using a fixed 0.55 delta, then uses it for exits and P&L. `frontend/src/components/PaperPortfolioView.tsx:155-159` calls that value “Current LTP.” Missing option quotes can therefore create synthetic gains, losses, and booked trades in live mode. Track quote provenance and age; require a market option quote for live option-price exits and realized P&L.

5. **A trailed-stop exit rewrites the observed price and P&L.** After Target 1, `backend/app/services/paper_trader.py:339-351` replaces the option's observed price with entry and books zero runner P&L when either a spot or option stop fires. The same pattern occurs for Setup 5 at `paper_trader.py:290-302`. If the observed premium differs from entry, the trade journal records a fictitious exit. Calculate P&L from the actual observed exit price and retain the stop threshold as a separate field.

6. **The stated maximum risk can be exceeded.** At `backend/app/services/paper_trader.py:173-186`, if one lot costs more than `max_risk_per_trade` but no more than twice that amount, `allowed_lots` becomes zero and is forced back to one. For example, a ₹6,000 lot is accepted against a ₹4,000 cap. Manual trades also bypass this sizing path when `lots` is supplied (`paper_trader.py:167-169`; `backend/app/api/paper.py:22-24`). Reject trades that cannot fit the cap and validate manual quantities against the same risk rule.

7. **State-changing routes are unauthenticated while the server binds all interfaces.** `backend/app/core/config.py:8-9` defaults to `0.0.0.0`; `backend/app/api/paper.py:22-49` permits trade, close, settings, and reset requests without authentication, and `backend/app/api/auth.py:28-32` permits disconnect. Anyone able to reach port 8001 can alter the paper portfolio or disconnect the broker session. Bind to loopback for a local-only app or require authorization on these routes.

## Medium severity

8. **“Live Market Feed” is based on credentials, not feed health.** `backend/app/services/scanner_worker.py:344-348` sets live mode whenever credentials exist, even if the quote request fails or returns no quotes (`scanner_worker.py:358-386`). `frontend/src/components/Header.tsx:82-91` then displays “Live Market Feed.” This can misrepresent a disconnected or stale feed. Derive feed status from a successful, recent quote timestamp and show a stale/error state otherwise.

9. **Cached option expiry never refreshes.** `backend/app/services/scanner_worker.py:282-307` fetches the expiry only when `_expiry_cache` lacks a symbol. After that expiry passes, chain requests continue using it until restart, disabling live strike enrichment and Setup 5. Expire the cache by date and refresh on an empty or rejected chain response.

10. **One chart fetch failure disables retries for the contract.** `backend/app/services/scanner_worker.py:662-681` adds an option security ID to `_failed_candle_sec_ids` after one empty response or exception and never removes it. A transient API failure permanently prevents historical chart retries for that process; Setup 5 must rely on locally accumulated ticks. Retry after a bounded backoff.

11. **A fabricated premium can be badged as a live quote.** `backend/app/services/strike_selector.py:323-324` substitutes `estimate_option_entry()` when both ask and LTP are zero, yet sets `is_live_quote=True` at line 360. `frontend/src/components/SignalCard.tsx:148-160` then labels it “Live Ask” and “LIVE NSE_FNO.” Set the live flag only if a positive market price supplied the entry.

12. **Demo trades remain in the live portfolio.** `backend/app/services/scanner_worker.py:143-181` generates demo candles and `scanner_worker.py:557-559` passes their signals to the default-enabled paper trader. Switching to live mode at line 347 preserves the same portfolio. Live-mode performance can therefore include positions opened from simulated data. Tag and separate portfolios or metrics by feed mode.

## Data freshness not verified

`backend/app/data/fno_universe.json` contains 213 bundled contracts and lot sizes, loaded without a refresh or validity check (`backend/app/services/universe_manager.py:101-123`; `backend/app/services/strike_selector.py:50-63`). The repository does not record an exchange-master date. Their current exchange validity was **not** established in this review, so this is a freshness risk rather than a proven stale-data finding. The hard-coded `2026-10-04` through `2026-10-09` requests in `backend/app/main.py:67-101` also make the debug endpoint date-specific after 9 October 2026.

## Verification

- Frontend TypeScript check: passed (`tsc --noEmit -p tsconfig.app.json`).
- Frontend tests: 2 files, 4 tests passed (`npm test -- --run`).
- Backend tests: not run; the available Python lacks `pytest` and `pydantic`.
- Independent Codex CLI read-only review completed with `VERDICT: REVISE`; its nine findings were checked against the cited code. The risk-cap, unauthenticated-route, and feed-health findings above were added after direct inspection.
