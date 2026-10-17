# Fit of daily-timeframe equity swing setups in the existing BB options paper-trading dashboard

Repo state read: /home/claude/BB at HEAD 5e61036 (merge of PR #66). Notes read from /mnt/project-files/notes/ (they are not in the repo): architecture_analysis.md (2026-10-14 snapshot, partly stale), improvement_analysis_2026-10-17.md, new_setup_ideas_2026-10-16.md, setups_summary.md, setup3_analysis_2026-10-16.md. Repo citations are file paths (no URLs); line numbers only where I checked them. Read-only on the repo.

## Q1. What of the existing intraday-options architecture can be reused for a daily-timeframe equity swing engine?

### Takeaway
Roughly half the plumbing is reusable as is (indicators, F&O universe and security ids, Dhan client, kill switch, runtime settings, telemetry, per-setup switch, market-hours/holiday logic, recorder DB, test clock). The paper trader itself is option-shaped and intraday-shaped (CE/PE, lots, delta-scaled option SL, 15:20 square-off), so a swing book should be a separate engine in the style of the existing `earnings_engine.py` multi-day paper book, not a new setup number in the intraday trader.

### Cited Findings
- Indicators are generic pandas functions: Bollinger (20, 2.0) plus 2.5 sigma, BandWidth and its 20-bar min, %B, VWAP, Wilder RSI 14, EMA 9, ADX/+DI/-DI 14, opening range. Wilder smoothing is seeded with an SMA and ADX is neutral (20) before bar 28 — `backend/app/services/indicators.py` (`calculate_indicators`), `docs/SETUPS_SPECIFICATION.md` section 1 and 11.4. Session-dependent pieces (session VWAP resetting 09:15, opening range) are meaningless on daily bars; ATR(14) is used by Setups 2/3 and exists as a computation inside strategy code, but check whether it is exported by `indicators.py` before relying on it. Not verified.
- Universe: ~213 F&O stocks with `security_id`, `lot_size`, `exchange_segment` (NSE_EQ) and `instrument_type` EQUITY in `backend/app/data/fno_universe.json`; `UniverseManager.get_fno_stocks()` plus 4 indices and 35 hand-picked momentum stocks — `backend/app/services/universe_manager.py`. Each entry has a `sector` field in `Instrument`, usable for the sector concentration limit that earnings_engine already applies (`earnings_one_per_sector`).
- Dhan client: only `fetch_intraday_candles` (POST /charts/intraday, interval 5, default 5-day lookback, four fallback payload shapes, rate-limit pacing 0.18 s, 429 retry, IST-naive timestamps), plus quotes, expiry list and option chain — `backend/app/services/dhan_client.py` lines 249-372. There is no daily-candle method.
- Quotes already carry previous close and day OHLC (`ohlc.close` is previous close; the ranker derives `change_pct` from it) — `backend/app/services/momentum_ranker.py`, `scanner_worker.py` ~572. So a live daily bar can be formed from the 3 s quote feed if wanted, though an end-of-day scan only needs the final bar.
- Kill switch and loss cap: `paper_risk.py` (kill switch persisted in the `settings` table, engages square-off, notifier events), enforced by `paper_trader`, `order_router.py` and also by `earnings_engine.py` via an injected `kill_switch` callable. The earnings book shows the pattern for a second book honouring the same switch.
- Per-setup switches: `setup_switches.py` — `DEFAULT_MODES` dict keyed by setup number string, modes off/index/stocks/all, `block_reason()` parsed from the string "Setup N: ..." via regex; setups 1-14 exist. A swing setup could be added as key "15" etc., but "index" vs "stocks" semantics are mostly irrelevant for equity swing (use off/all, or off/stocks).
- Runtime settings framework: `runtime_settings.py` `DEFINITIONS` tuple of `SettingDef` (type, min/max, choices, `zero_disables`, group, env default), validated, audited in `settings_audit`, applied without restart; groups include Risk, Sizing, Quality, Telemetry, Earnings, Live, Recorder. Adding a "Swing equity" group is a registry addition and the Settings tab renders from it (`frontend/src/components/SettingsPanel.tsx`; not checked in detail whether it is fully data-driven).
- Charges calculator is option-only: flat 20 per order, STT 0.15% on sell turnover (comment: effective 1 April 2026), exchange 0.03553%, SEBI 0.0001%, stamp 0.003% on buy, GST 18% — `backend/app/services/charges_calculator.py`. Equity delivery or equity futures need different rates.
- Telemetry (`strategy_decisions`, `trade_excursions` MFE/MAE, `error_events`) and the performance report (`by setup`, expectancy, profit factor, drawdown) are reusable if the swing book writes a distinct `book` label — `telemetry.py`, `performance_report.py`, `docs/SETUPS_SPECIFICATION.md` section 16. The earnings book already does this with BOOK = "earnings".
- Market recorder: `market_recorder.py` saves completed 5m/15m spot and option bars into a separate `market_bars.db` (table `bars`: kind, key, tf, ts, OHLCV; 180-day default retention; duplicates ignored; not in the nightly GCS backup). Daily bars could use the same table with tf "1d", but retention at 180 days is too short for indicator warm-up plus a backtest.
- Test clock: `market_hours.override_clock` / `set_clock` allow deterministic time in tests; `tests/test_p3_replay.py` is a clock-stepping replay of repeated signals through the paper engine (an invariant test, not a performance backtest).
- Frontend: tabs for Watch, Review, Settings, Analytics (setup stats), plus `ReplayControls.tsx`; `SetupFilterTabs`, `SetupStatsPanel`, `SetupSwitches` are setup-aware and would need a swing entry.
- Existing multi-day precedent: the earnings paper book (`earnings_engine.py`: own tables `earnings_positions`, `earnings_calendar`, `earnings_iv_history`; scheduled exits in trading days; kill switch squares it off; RMS gates incl. per-sector and max notional) — `docs/SETUPS_SPECIFICATION.md` section 17.

### Inferences
- Because the intraday `PaperPosition` model is option-specific (CE/PE, `strike_symbol`, `option_sl`, `lots`, `lot_size`, delta exits) and `paper_guards.flag_stale_carryover()` plus `square_off_if_due()` actively close or quarantine anything that survives to the next day, forcing swing positions into it would fight the safeguards that were added after the NESTLEIND/frozen-quote incident. A separate `swing_engine` with its own table is the lower-risk fit.
- Reuse list (keep as imports, do not fork): indicators (add a daily-safe variant that skips VWAP/ORB), universe, DhanClient, runtime_settings, telemetry, notifier, market_hours (holiday list, clock), paper_risk kill switch signal, charges (new function alongside).
- Setup number key in `setup_switches` is a poor fit for the existing "index/stocks" semantics; a separate `swing_enabled` runtime setting plus per-strategy on/off settings is simpler, but the user's convention is "per-setup switches", so add keys for compatibility with the Setup switches UI.

### Gaps
- Not checked: whether `indicators.py` exports ATR; whether SettingsPanel renders new groups automatically; how Analytics filters by `book`.
- The Dhan app/instrument master for equity (NSE_EQ) security ids vs futures ids was not examined; if swing is done via stock futures (to short), a futures security-id map is needed and is absent from `fno_universe.json` (it holds equity ids only).

## Q2. What would be new

### Takeaway
Daily candle fetch and cache, an after-close scan job, a multi-day position table with overnight handling, an equity cost model, and a decision on exit mechanics are all new work. None is large; the largest design question is whether shorts are in scope (needs futures, since delivery equity cannot be shorted overnight).

### Cited Findings
- Daily candles: Dhan's python SDK documents `historical_daily_data(security_id, exchange_segment, instrument_type, from_date, to_date, expiry_code=0)` returning timestamp/open/high/low/close/volume; it does not state the REST path or a range limit — [DhanHQ-py Historical Data](https://dhanhq.co/docs/DhanHQ-py/_historical_data/).
- Dhan support page: intraday data goes back 5 years in 1/5/15/25/60-minute candles; daily OHLCV is available "starting from the stock's inception date"; no per-request day limit is stated there — [Dhan support: timeframe data](https://dhan.co/support/platforms/dhanhq-api/what-timeframe-data-is-available-through-dhan-s-historical-data-apis/). The REST docs (dhanhq.co/docs/v2) were not reachable from this environment, so the endpoint path, per-request date cap, and whether daily data is split/bonus adjusted are unconfirmed.
- Current client behaviour on failure: `fetch_intraday_candles` returns an empty DataFrame on any non-200 and tries up to four payload variants; a daily fetcher would need the same defensive handling plus an explicit "short history" check — `dhan_client.py` lines 249-370.
- Today no code stores daily bars: the only candle stores are per-trade `trade_candles` (`paper_storage.py`) and the recorder's 5m/15m `bars` (`market_recorder.py`). Intraday bars only exist after the recorder was added (PR #63, 2026-10-17), so the recorder holds days, not years.
- Scheduling: the scanner loop is a 3 s market-hours loop (`SCAN_INTERVAL_SECONDS`, `scanner_worker.py`); `earnings_engine` has timed actions (`earnings_entry_time`, `earnings_exit_time`) and an NSE sync with a 30-minute retry backoff, which is the closest precedent for a once-a-day job.
- Position persistence: intraday positions persist in `positions` (SQLite via a write queue, `paper_persistence.py`) and are reloaded at start; `flag_stale_carryover()` closes any position from an earlier date as `STALE_CARRYOVER` and quarantines it (`paper_guards.py` 131-153); `square_off_if_due()` closes everything at 15:20 (`EOD_SQUARE_OFF_TIME`). Both must not touch swing positions.
- Gap handling today: `GAP_EXIT_PCT` (default 5) only labels an exit fill that is beyond the intended level; the intraday engine has no overnight concept. Setups 2/3 require 20 bars of the current session specifically to avoid overnight-gap distortion of bands (`docs/SETUPS_SPECIFICATION.md` sections 3, 4) — not applicable to daily bars.
- Cost model: option calculator above; equity delivery charges differ (no 20-rupee flat per the option schedule is assumed to apply; STT on delivery is on both legs; DP charge on sell) — not confirmed against Dhan's current schedule in this research.
- Holiday list covers 2026 only and fails closed (every date in an unlisted year is non-trading) — `market_hours.py`. A swing engine counting trading days (time stops, "N trading days before") needs 2027 dates before 1 January.
- Shorting and carrying: the whole app is long-option-only. Swing shorts in Indian equities would require stock futures (margin, lot size, monthly expiry roll, different charges) — inference from NSE rules, no source fetched.

### Inferences
- New pieces, in order of size: (1) `daily_candles` store + fetcher with adjustment sanity check (compare Dhan daily close vs prior close for corporate-action jumps); (2) `swing_positions` table (symbol, side, qty, entry date/price, stop, target, trailing state, planned exit rule, days held, status, costs, book label); (3) after-close scan job (e.g. 15:45-16:30 IST, after daily bar finalises) that writes next-day orders; (4) next-open fill simulator; (5) equity charges function; (6) swing section in the Settings registry and UI table.
- Entry/exit timing choice drives realism: signal on daily close, entry at next open (with slippage model and a gap-through-stop rule: fill at open, not at stop) is the honest default; exit "at close" on a signal bar is only attainable by using the 15:15-15:25 snapshot, so treat it as a variant, not baseline. Stops that gap are filled at the worse of open and stop.
- Overnight risk controls need new settings: max gap-risk per position, max gross exposure, max positions per sector, earnings-date exclusion (the app already has an NSE earnings calendar — `earnings_calendar_sync.py`, `earnings_registry.py` — reusable to skip names reporting inside the holding window).
- Daily quotes are not tick-driven for swing: stop checks could run on the existing 3 s feed during the day (cheap) or only at the close (simpler, deterministic for replay). Prefer close-based evaluation first so the live engine matches the backtest exactly.

### Gaps
- Dhan REST historical daily endpoint path, max range per call, adjustment for splits/bonus, and its rate limits: not retrievable (docs host blocked); must be tested with one real call on the Mac/VM.
- Equity delivery vs futures cost schedules and current margin figures: not researched here.

## Q3. Prior failed experiments and decisions to respect

### Takeaway
Respect: Setups 1 and 5 logic is frozen; new ideas ship as new setups with their own switch and a same-PR update to the spec; plain RSI divergence was replayed and has no edge; every idea must be replayed with pessimistic assumptions before shipping; paper only and kill-switch aware.

### Cited Findings
- "Not duplicated: existing Setups 1-9 and plain RSI divergence (replayed, no edge, PR #14 closed)" — `/mnt/project-files/notes/new_setup_ideas_2026-10-16.md`. The replay was on spot with pessimistic exits, then costs added, using Fyers 5m CSVs on the user's Mac (6 months on 5 stocks, 2.75 years on NIFTY/BANKNIFTY) — same file.
- Common rules for any shipped idea: completed bars, spot levels, T1 1.5R / T2 2.5R unless stated, 20-bar session warm-up where bands/RSI are used, per-setup switch, docs update in the same PR — same file.
- "Setups 1 and 5 logic is untouched by every proposal; anything that would touch them is marked DECISION"; Setup 11 is already a shadow of Setup 5; shadows are the pattern for A/B — `/mnt/project-files/notes/improvement_analysis_2026-10-17.md`.
- Setup 3 (W/M with RSI divergence) analysis: the 1.5-point RSI margin is immaterial, median RSI2-RSI1 is +7.5 and only 6% of signals fall at or below 1.5, so divergence is "a filter in name"; no regime filter; enabled on stocks by default; revisit index-only planned about 2026-10-23 — `/mnt/project-files/notes/setup3_analysis_2026-10-16.md`, improvement_analysis (Decisions section).
- Setups 1 and 2 lost money on stock options; the default switch is index only — `setup_switches.py` comment on `DEFAULT_MODES`.
- Setup 1's "squeeze" was always true on 5m bars (5% absolute BandWidth); Setups 6-8 never fired for the same reason until the 2026-10-16 fix; any BandWidth thresholds must be calibrated on real data, not assumed. Daily-bar BandWidth is much larger than 5m, so intraday thresholds (1.3x of the 20-bar min is relative and portable; the absolute 5% is not) must not be copied blindly — `docs/SETUPS_SPECIFICATION.md` 11.1/11.4, architecture_analysis W3.
- Index VWAP was not a VWAP (no volume); fixed to session-cumulative mean typical price — architecture_analysis W4, spec 11.4. Not relevant to daily setups but a reminder that indicator semantics differ by instrument type.
- Measurement lessons: 33-trade, one-day samples produced Setup 5 conclusions treated only as hypotheses; `setup_stats.avg_r` is biased upward because stops move to entry after T1 (fixed by `initial_option_sl`, PR #64); add confidence ranges and minimum-sample flags — improvement_analysis sections 1 and 7.
- Journal integrity incident: ~50 identical NESTLEIND Setup 5 trades from one signal replayed on a frozen after-hours quote led to the session guard, holiday list, square-off and stale-carryover logic — `/mnt/project-files/notes/deep_audit_and_mitigation_plan_2026-10-14.md`. A swing engine runs after hours by design, so it needs its own explicit session logic and must not weaken those guards.
- Limits on spec fidelity: spec drift (5 setups vs code 14, top-5 vs top-10) was itself flagged as a defect, hence the same-PR spec rule — architecture_analysis section 4/6, spec section 11.
- Live routing is Definedge, option-oriented, with dry-run default and a deploy script that blocks while a live position is open; swing positions held overnight interact with the deploy gate (it checks `positions` and `live_positions`, not a new table) — improvement_analysis section 5, commit 2c77e5e.

### Inferences
- Treat plain Bollinger/RSI-divergence swing variants with skepticism: the only direct evidence the user has is a no-edge result for RSI divergence intraday, and Setup 3's divergence filter adds little discrimination. Divergence should not be a headline swing entry; use it only as a tagged feature.
- A swing book should ship paper-only, off by default (like `earnings_enabled`), with its own deploy-gate check for open swing positions, because a mid-hold restart is the new failure mode.
- Respect "new ideas go in as new setups": numbering continues from 15 (spec ends at section 19, Setup 14); spec sections 20+ for each, and Setup summaries file updated.

### Gaps
- PR #14's actual replay output (numbers, window, cost assumptions) is not in the repo or notes; only the verdict is recorded. The Fyers CSVs live on the user's Mac and were not accessible here.
- Whether a repo-level instruction file (CLAUDE.md) exists: none found at repo root; the "Setups 1 and 5 untouched / spec in same PR" rules come from the notes and the user's instructions.

## Q4. Suggested minimal architecture and replay/backtest harness

### Takeaway
Build a pure, stateless signal module on daily DataFrames, a thin swing paper book that reuses the settings, kill switch, telemetry and notifier, and an offline backtest that calls the identical signal function with next-open fills, gap-aware stops, equity costs and a pessimistic tie-break; gate shipping on out-of-sample, cost-inclusive results across multiple regimes.

### Cited Findings
- Existing module pattern to copy: new setups live in their own file with a pure evaluator (`setup11.py` to `setup14.py`, `relative_strength.py`, `straddle_squeeze.py`, `earnings_strategy.py` rules separate from `earnings_engine.py` book) with tests per setup (`tests/test_setup11.py` to `test_setup14.py`, `test_earnings.py`) — repo listing.
- Existing offline tools: `backend/scripts/compare_squeeze.py`, `liquidity_analysis.py`; `/api/recorder/bars` and the SQLite file readable from pandas — spec line on recorder, `scripts/`.
- Test clock and replay precedent: `tests/test_p3_replay.py`, `market_hours.override_clock`.
- The user's prior replay method: spot, pessimistic exits, then add costs — new_setup_ideas_2026-10-16.md.
- The notes warn against deciding on tiny samples and recommend confidence ranges and minimum-sample flags — improvement_analysis sections 1/7.

### Inferences
Proposed minimal layout (new files only; no edit to Setup 1/5 code):
1. `services/daily_candles.py`: `DailyCandleStore` (SQLite table `daily_bars(symbol, date, o,h,l,c,v, adj_flag)` in `market_bars.db` or its own file) and `fetch_daily(security_id, from, to)` in `DhanClient`. Nightly incremental top-up after 16:00 IST; initial backfill 2-3 years for ~213 names (about 213 calls at 0.18 s pacing, under a minute if the range limit allows). Detect corporate-action jumps (|close/prev_close-1| beyond a threshold with volume regime change) and flag instead of silently using.
2. `services/swing_signals.py`: pure `evaluate_swing(df_daily, symbol, params) -> list[SwingSignal]` using `calculate_indicators` (minus session fields) with signal date, planned entry rule (next open), initial stop (ATR-based), target/trailing rule, time stop, and metrics for telemetry. One function per setup, enum e.g. `SETUP_15_...`.
3. `services/swing_engine.py`: modelled on `earnings_engine.py`: own `swing_positions` table; `run_eod_scan()` once after the daily bar closes (guarded by `market_hours` and a trading-day check); `process_open()` at next open to fill pending orders and at each close to evaluate stops/targets/time exits; gap rule: stop fills at open if open is through it; gates: kill switch (injected callable), daily loss limit, max open positions, max gross notional, one per sector, earnings-window exclusion via the existing earnings calendar; all decisions to `strategy_decisions` with book "swing".
4. `services/charges_calculator.py`: add `calculate_equity_delivery_charges(...)` (keep the option function untouched); parameterise intraday vs delivery vs futures.
5. Settings: `swing_enabled` (default off), `swing_max_positions`, `swing_risk_per_trade`, `swing_max_hold_days`, per-setup switches `swing_setup_15_enabled` etc., slippage bps, earnings-exclusion days; new `G_SWING` group. Also add keys to `setup_switches.DEFAULT_MODES` only if the UI should list them there.
6. Guards: exclude swing rows from `flag_stale_carryover` / `square_off_if_due` by keeping them in a separate table; extend deploy gate and readiness check to count open swing positions; extend `bb-backup` coverage (trades.db already backed up; `market_bars.db` is not, so keep daily bars rebuildable or add them to backup).
7. UI: a "Swing" panel (open positions with days held, pending orders for tomorrow's open, last scan time, per-setup stats) mirroring the Earnings panel.

Replay/backtest harness (offline, `backend/scripts/swing_backtest.py` plus tests):
- Input: daily bars for the F&O universe (Dhan backfill; cross-check a handful of names against the user's Fyers CSVs resampled to daily where available).
- Loop by date: compute signals on data up to and including day t only (assert no lookahead: truncate frame, re-evaluate, compare), queue orders, fill at t+1 open with slippage; evaluate stops/targets from day t+1 high/low; when stop and target are both inside one bar assume stop first (pessimistic, as in the RSI-divergence test); gap-through fills at the open; time exit at close or next open; apply the new equity cost function; enforce the same max-position/sector/kill-switch gates by calling the engine's gate functions rather than reimplementing them.
- Better still, run the real `swing_engine` against the replay clock (`override_clock`) with a fake candle provider so the backtest exercises production code, mirroring `test_p3_replay`; add invariants (never open on holiday, positions persisted across simulated restarts, no fills outside the bar's range).
- Reports: trades, win rate with Wilson interval, expectancy in R with bootstrap CI, profit factor, max drawdown, exposure, turnover, per-year and per-regime splits, benchmark vs buy-and-hold NIFTY and vs a random-entry same-exit control, sensitivity to slippage and to +/-1 day delay.
- Shipping gate (suggested): positive cost-inclusive expectancy in both halves of a walk-forward split, enough trades (a minimum count, like 100+, flagged by the harness), robust to doubled slippage, and survivorship-bias note (current F&O list used for history is survivor-biased; the repo has no point-in-time membership data).
- Then forward test as paper shadow for N weeks via the same engine before enabling any real routing (the notes' shadow-setup precedent).

### Gaps
- Survivorship: no historical F&O membership list in the repo or notes.
- Daily data adjustment and available years from Dhan unconfirmed (see Q2).
- Which specific swing setups to build is out of scope here; this note covers fit only.
