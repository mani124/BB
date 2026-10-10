# Code review findings — 10 October 2026

Scope: current `d452602` compared with the prior review baseline `3c21eef`, including the Dhan OAuth and WebSocket feed, paper trade accounting, and Setups 6–8. This is a findings report; application code was not changed. Severity reflects likely effect on market data, trade records, or build behavior. The findings below are reproducible from code inspection unless a source specification is cited.

## Critical

### 1. Dhan v2 WebSocket subscriptions use the wrong wire protocol

**Location:** `backend/app/services/dhan_websocket.py:108-118,155-162`; `backend/app/services/dhan_packet_codec.py:33-56`; `backend/app/services/scanner_worker.py:161-166,605-615`.

After opening the v2 socket, the client sends a binary login frame and binary subscription frames. Dhan's [v2 live market feed specification](https://dhanhq.co/docs/v2/live-market-feed/) authenticates via the connection URL and requires JSON request messages with `RequestCode`, `InstrumentCount`, and `InstrumentList`. A socket can connect while subscriptions fail, yet the scanner marks it `WS_LIVE` and uses connection state as evidence of fresh quotes. Live instruments may never receive ticks while the dashboard says the feed is live. Send documented v2 requests and only mark the subscription healthy after data or an acknowledged subscription is observed.

### 2. Valid v2 ticker and quote frames decode to incorrect prices

**Location:** `backend/app/services/dhan_packet_codec.py:86-128`.

The decoder treats bytes 1–2 as a one-byte segment and a two-byte length, then reads ticker time before price. Dhan's [packet layout](https://dhanhq.co/docs/v2/live-market-feed/) uses a two-byte length, one-byte segment, four-byte security ID, then ticker LTP and last traded time. Quote field types and offsets also differ. For example, a valid 16-byte ticker for segment 1, security ID 1333, LTP 123.45 and time 1791630000 decodes here with segment 16 and LTP about `1.22e26`. This can corrupt candles, signals, and paper exits even after subscriptions are fixed. Decode each documented packet layout and verify against known v2 frames.

## High

### 3. Security ID collisions route index ticks to equities

**Location:** `backend/app/services/scanner_worker.py:90-92,201-203,251-269`; `backend/app/services/universe_manager.py:16-33,85`.

The tick lookup is keyed only by `security_id`, ignoring `exchange_segment`. `IDX_I` NIFTY 50 uses ID 13, which collides with `NSE_EQ` ABB ID 13; NIFTY BANK ID 25 collides with ADANIENT ID 25. The later equity entries overwrite the index entries, so index ticks update the equity candle and may drive the wrong paper position. Use `(exchange_segment, security_id)` as the key throughout the live tick path. Dhan documents segment IDs in its [annexure](https://dhanhq.co/docs/v2/annexure/).

### 4. A feed outage generates synthetic market data and paper trades

**Location:** `backend/app/services/scanner_worker.py:384-436,605-637,723-735,880-895`; `backend/app/services/paper_trader.py:330-338`.

Synthetic candles are blocked only when `active_mode == "live"`. When credentials exist but quotes fail for long enough, mode becomes `stale` or `error`; the missing-quote path then generates deterministic sine-wave candles and evaluates them as signals. `on_signals_cycle` can automatically open trades tagged `stale` or `error`. An outage therefore creates fabricated prices, indicators, signals, and trade history rather than preserving known quotes. Restrict synthetic candles and automated demo trades to explicit demo mode; keep stale/error data sourced from last real observations.

### 5. Unresolved option chains still produce synthetic premiums in live positions

**Location:** `backend/app/services/strike_selector.py:433-444`; `backend/app/services/scanner_worker.py:846-886`; `backend/app/services/paper_trader.py:437-455`.

If a live option chain cannot resolve a contract, `resolve_live_strike_from_chain` falls back to an estimated recommendation without `option_security_id`. The paper trader's no-ID path estimates a new option premium from spot movement even when `feed_mode` is live. It can display invented LTP and P&L and trigger option-level exits. Keep an unresolved live contract unpriced and prevent live paper valuation or exits from using estimated premiums.

### 6. Spot-triggered live exits can record a price never quoted

**Location:** `backend/app/services/paper_trader.py:350-360,513-545,561-608`.

A spot stop or target can close a live option position without a current option bid or LTP. `_finalize_closed_position` then books the theoretical option stop or target as the execution price. The trade journal and realized P&L therefore imply an observed fill that did not exist. Require a fresh option quote for a live paper fill, or retain a pending spot trigger until a quote arrives.

### 7. Option STT uses the expired rate

**Location:** `backend/app/services/charges_calculator.py:67-68`.

The calculator charges 0.10% of option sell premium. The [NSE STT schedule](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies) states that sale of options is charged 0.15% from 1 April 2026. Current net paper P&L is overstated by 0.05% of sell turnover, before any downstream rounding. Use the effective-date rate for trades on or after that date.

### 8. Snapback targets can be behind the entry price

**Location:** `backend/app/services/strategy_engine.py:348-385,434-439,518-561`; `backend/app/services/strike_selector.py:228-250`; `backend/app/services/paper_trader.py:547-559,596-608`.

Setups 6–8 assign the Bollinger midpoint as Target 1 without checking that it lies in the expected trade direction. A valid PE signal can close below the midpoint, making Target 1 above entry; a CE signal can close above it. `recommend_strike` uses `abs(entry - target)`, masking the reversed target as a positive premium gain, while spot target checks can mark Target 1 reached immediately. Validate `PE: target < entry` and `CE: target > entry`, or suppress the signal when the geometric target has already been crossed.

## Medium

### 9. Setup 7 can fire without an inside-bar breakout

**Location:** `backend/app/services/strategy_engine.py:412-418,457-463`.

The bearish branch accepts an inside candle that closes at its *own* low (`curr_close <= curr_low + 1e-4`); the bullish branch accepts a close at its own high. Neither condition proves a breakout of the inside candle or mother candle. A contained bar can therefore trigger a Setup 7 signal and paper entry. Require a later price or completed bar crossing the selected trigger boundary.

### 10. Setup 8 can report RSI divergence without divergence at the second swing

**Location:** `backend/app/services/strategy_engine.py:518-523,552-557`.

The RSI condition accepts a comparison between the first swing's RSI and the *current* candle's RSI as an alternative to comparing the two identified swing extrema. A later RSI reversal can satisfy this test even when swing two did not diverge from swing one. Compare RSI at the two swing highs or lows; apply any later reversal as a separate confirmation rule.

### 11. New candle-pattern setups can auto-trade before bar close

**Location:** `backend/app/services/scanner_worker.py:481-482,795,880-886`.

The indicator frame includes the forming live candle, and Setups 6–8 use its current OHLC and RSI. An intrabar pin bar, inside bar, or swing condition can disappear before bar close, but its signal ID may already have opened a paper position. Evaluate candle-confirmed patterns on completed bars, or defer automatic entry until a provisional signal is confirmed.

### 12. Final exit slippage is applied to lots sold at Target 1

**Location:** `backend/app/services/paper_trader.py:376-378,494-503,547-557,596-606`.

At Target 1 the trader reduces `pos.quantity`; finalization later multiplies the final exit's per-unit slippage by `initial_quantity`. It therefore charges runner exit slippage to lots already sold, and does not separately account for those earlier sale legs. Total slippage cost and net P&L can be wrong after partial exits. Sum entry and each exit leg using the quantity and fill of that leg.

### 13. Manually opened live trades are stored as demo trades

**Location:** `backend/app/api/paper.py:22-24`; `backend/app/services/paper_trader.py:184-188`; `backend/app/services/scanner_worker.py:98-103,895`.

The manual `/paper/trade` route omits `feed_mode`, so `open_position_from_signal` defaults to `demo` even for a signal seen in the live scanner. The position is absent from the scanner's mode-filtered live portfolio and does not trigger the live option WebSocket subscription callback. Resolve and pass the signal's trusted feed mode when opening it manually.

### 14. OAuth countdown ignores Dhan's absolute expiry

**Location:** `backend/app/api/auth.py:153-180`; `frontend/src/context/DhanAuthContext.tsx:204-210`.

Dhan's [OAuth consent response](https://dhanhq.co/docs/v2/authentication/) supplies `expiryTime` as an absolute IST timestamp. The backend ignores it, defaults to 24 hours, and the frontend starts that interval at the time of exchange. Any elapsed time between issuance and exchange, or a token with a different remaining lifetime, makes the displayed expiry inaccurate and can leave the UI showing an active session after actual expiry. Parse and pass through the absolute expiry.

### 15. Mode-filtered portfolio omits realized profit from active partial exits

**Location:** `backend/app/services/paper_trader.py:116-147,648-659`; `backend/app/services/scanner_worker.py:895`.

The unfiltered portfolio counts `booked_pnl_rupees` on active positions as realized P&L, but `get_portfolio(mode=...)` sums realized P&L only from closed trades and includes the entire active `pnl_rupees` under unrealized. After a Target 1 partial sale, the live or demo dashboard misclassifies booked profit as unrealized until the runner closes. Include active positions' booked profit in mode-filtered realized metrics and keep unrealized metrics limited to remaining quantity.

## Validation

- Backend: `212 passed, 1 warning` with `pytest -q -p no:cacheprovider backend/tests` using dependencies from `backend/requirements.txt`.
- Frontend: `23 passed` with `npm test -- --run`; `npm run build` succeeds.
- Direct `tsc --noEmit -p frontend/tsconfig.app.json` reports six type errors in test files; the configured production build does not include those tests and succeeds. This is a separate test type-checking issue, not evidence of a failed production build.
- No live Dhan account or exchange feed was used. Feed findings rely on the documented protocol and local packet reproduction.
