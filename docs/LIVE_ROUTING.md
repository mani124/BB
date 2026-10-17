# Live broker routing

Status: **off by default.** Nothing in this feature places an order until you switch it on. It does not change any
trading setup's rules; the paper engine still decides every entry and exit. Routing mirrors those decisions to a
real broker.

Broker: **Definedge Securities** (Integrate API). The router talks to a small adapter interface
(`services/broker_adapter.py`); Definedge is the first adapter (`services/broker_definedge.py`). Dhan stays the
market-data feed. Another broker is one more adapter class.

## What it does

* **Entry.** When a paper entry opens on the **real feed** (never demo), the router runs its checks and, in live
  mode, sends a BUY of the same contract and quantity. A LIMIT is priced at the ask plus `live_entry_limit_buffer_pct`.
  An unfilled entry is cancelled after `live_order_timeout_seconds`; a partial fill is kept and later exits are
  scaled to what was actually bought.
* **Exit.** Whenever the paper position shrinks (Target 1 half) or closes (stop, Target 2, manual, kill switch,
  end of day, reset), the router sells whatever the broker still holds for it (a LIMIT below the bid by default; MARKET is a setting). Exits are
  **never blocked** by the kill switch, a halt, the loss cap, the caps below, or the mode being switched off. A
  position bought for real is always exited for real.
* **Reconcile.** Every `live_reconcile_seconds` the router refreshes unsettled orders from the broker and compares
  net positions with what it expects. A difference raises an alert and halts new entries until you resume.

## Modes

| Mode | What happens |
|---|---|
| `off` (default) | Hooks return at once. Paper trading is unchanged. |
| `dry_run` | Every check runs, the exact order is built and written to the order log, **nothing is sent**. Exits are logged too. |
| `live` | Orders go to the broker. |

Live is not a setting. To enable it all of these must hold: the server has `LIVE_TRADING_CONFIRM=CONFIRMED`; the
Algo ID, allowed setups and a daily loss limit are set; the kill switch is off; no halt; a broker session is logged
in and accepted by the broker; **step 1** `Go live...` issues a one-time 6-digit code (valid 2 minutes); **step 2**
you type that code and the phrase `ENABLE LIVE TRADING`. Live drops back to `dry_run` on every restart, and every
mode change is written to the audit log (`GET /api/live/audit`).

## Entry checks (all fail closed)

In order: mode, halt, kill switch / loss cap / loss streak (the existing paper risk gate), entry window, setup
allow-list, broker session (live), Algo ID, inputs present and consistent (lots, quantity, lot size, price, strike,
expiry), daily loss limit, then the caps below, contract lookup (lot size must match the broker's), and finally an
idempotent order tag. A refused entry is logged as `BLOCKED` with its code (visible in the order log and as a
`LIVE_*` skip in telemetry).

Caps (Settings > Live broker routing, all changeable without a restart, all validated and written to the settings
audit): setups allowed, max lots per order, max value per entry order, max entry orders per day, max orders per
day (all sides), max open live positions, live daily loss limit (0 uses the general limit; if both are 0 live
entries are refused), order types and limit buffers, product type (INTRADAY or NORMAL), Algo ID, fill wait,
reconcile interval, halt on mismatch.

Only entries are limited by the caps. Exits are exempt.

## Safety behaviour

* **Idempotent orders.** A tag is reserved in the database before any send and survives restarts. It is released
  only when the broker definitely did not accept the order. On a timeout it stays reserved, the order is looked up
  at the broker by tag, and if it still cannot be found the router **halts entries and alerts CRITICAL instead of
  sending again**.
* **Rejects, partial fills, timeouts, expired sessions.** A reject releases the tag, marks the position failed
  (entry) or alerts and retries up to 3 times (exit; then use `retry-exit`). An expired session halts entries,
  alerts, and keeps trying exits once you log in again. Alerts go to Telegram (if configured) and the error table
  (`LIVE_*` codes in Telemetry).
* **No secrets in the repo, logs or API.** The Definedge API token and secret come from the server environment; the
  session key exists only in memory; the login URL is hidden from the HTTP client's request log.
* **Paper reset** while a live position is open exits that position at the broker within one reconcile interval (exits always go through).

## Setting it up (server)

1. Environment (never commit these): `DEFINEDGE_API_TOKEN`, `DEFINEDGE_API_SECRET` (from the Definedge portal,
   My Account > Show My API Secret), and, only when you are ready for live, `LIVE_TRADING_CONFIRM=CONFIRMED`.
2. Enable the external TOTP on your Definedge account. The dashboard asks for the 6-digit code each morning; the
   session key lasts the trading day.
3. Register your algo with the broker as required and put its identifier in `live_algo_id`.

## Verify with a dry run on a market day (before any live order)

1. Do **not** set `LIVE_TRADING_CONFIRM`. Set `live_allowed_setups` to one setup (for example `5`), `live_algo_id`
   to your real Algo ID, `live_max_lots_per_order` to 1 or 2.
2. Settings > Live broker routing: `Dry run`. Log in to the broker with the TOTP (also proves login works).
3. Let the session run. For every paper entry on the real feed, check the order log: the contract
   (`trading_symbol`), quantity, price and payload should be exactly what you would key in by hand. Compare a few
   symbols against the broker's terminal, including a weekly expiry and one BSE (SENSEX) contract if you trade it.
4. Confirm exits appear as dry-run SELL rows at Target 1 (half) and at the stop/target.
5. Fields to confirm against the broker's real responses before going live: the order and position field names the
   adapter reads (`broker_definedge.py`, `parse_order_row` and `net_positions`). They are read through alias lists
   because the vendor client does not document them. Place one 1-lot order by hand in the broker app, then use
   **Reconcile now** and check the router sees the position and fill price.
6. Only then set `LIVE_TRADING_CONFIRM=CONFIRMED`, restart outside market hours, log in, and use `Go live...` with
   1 lot on one setup. Watch the first trade end to end.

## Regulatory checklist (SEBI / NSE retail algo framework)

Summarised from public broker write-ups of the NSE retail algo circular and the rules that apply from 1 April 2026
([Zerodha](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework),
[Fyers](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)).
This is not legal advice and nothing here is Definedge-specific: confirm each point with Definedge before going live.

* **Static IP.** Orders are accepted only from an API key mapped to a whitelisted static public IP. Give the server a
  reserved static external IP and register it with Definedge. If the IP changes, every order, including exits, is
  rejected; the router will alert and keep retrying exits, but you would have to square off by hand.
* **Order rate.** Up to 10 orders per second counts as an unregistered algo, tagged by the broker with a generic algo
  ID. BB sends a handful of orders a day and the daily caps keep it far below that.
* **Algo ID.** Ask Definedge what value their API expects in `algo_id` for a self-run strategy under the threshold.
  `live_algo_id` must be non-empty or every live order is refused.
* **Daily login.** 2FA once per trading day, no long-lived sessions. The TOTP login in the dashboard matches this.
* **Market orders.** Brokers now convert market orders to market-price-protection orders and exchanges often refuse
  plain market orders on options. The default exit type is therefore LIMIT, priced below the bid by `live_exit_limit_buffer_pct`
  (an unfilled one is cancelled and re-sent). Test one exit in the 1-lot check; only switch `live_exit_order_type`
  to MARKET if Definedge accepts it for options.
* **Your own account only.** Do not route orders for anyone else's account from this app.

## Not covered

* The earnings book and Setup 11 shadow book are not routed (Setup 11 can be allowed explicitly via
  `live_allowed_setups`; the earnings book is a separate engine and is never routed).
* Exchange freeze-quantity splitting: keep `live_max_lots_per_order` below the freeze limit for your index.
* Charges, taxes and slippage differ from the paper model; compare the routed P&L (`/api/live/status`) with paper.

## API

`GET /api/live/status`, `GET /api/live/orders`, `GET /api/live/audit`, `POST /api/live/mode` (off or dry_run only),
`POST /api/live/arm`, `POST /api/live/enable`, `POST /api/live/resume`, `POST /api/live/reconcile`,
`POST /api/live/positions/{id}/retry-exit`, `POST /api/live/broker/login`, `POST /api/live/broker/logout`.
All mutations need the dashboard capability like every other endpoint.
