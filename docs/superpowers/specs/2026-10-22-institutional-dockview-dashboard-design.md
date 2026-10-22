# Institutional-grade dashboard on Dockview (free edition): design

Date: 2026-10-22
Status: written for user review; implementation not started
Path: architectural (replaces the whole frontend shell, adds read-only backend endpoints)
Companion plan: `docs/superpowers/plans/2026-10-22-institutional-dockview-dashboard.md`

---

## 0. Intent and shared understanding

**What the owner asked for (their words):** redesign the entire dashboard on the free Dockview edition, make it institutional grade, analyse everything, and write a complete spec and plan that a cloud session can execute without leaving anything out.

**Who it is for:** one user (the owner), who runs the paper scanner and the optional live-routing path on a single VM and watches it from a laptop, often on a second monitor, sometimes from a phone.

**Priorities the owner chose earlier (brainstorming session):** (1) risk and compliance, (2) performance analytics, (3) execution quality. Architectural path, not a facelift.

**Assumptions I made (change any of them before approval):**

| # | Assumption | Why |
|---|---|---|
| A1 | "Free version" means the MIT-licensed `dockview-react` core only. The commercial `dockview-enterprise` package is never installed. | Owner said free. |
| A2 | Trading logic (scanner, setups, paper engine, risk engine, order router) is **not** changed by this project. The backend gets additive, read-only analytics endpoints, one UI-layout store, and one action-audit log. | A redesign must not change what trades. |
| A3 | Layouts are stored on the server (SQLite), so a layout made on the laptop appears on every browser. localStorage is only a cache. | Single user, several screens. |
| A4 | Phones and small tablets (< 1024 px) keep a single-pane, tab-bar shell that reuses the same panel components. Dockview is desktop-only. | Docking is a poor fit for a phone. |
| A5 | The old terminal stays selectable behind a flag until the new shell passes a parity checklist and one full paper session. Then it is deleted. | Cheap rollback. |
| A6 | "Institutional grade" is defined by measurable requirements in section 4, not by look alone. | So the cloud session can verify it. |
| A7 | No claim here about SEBI or broker rules is treated as fact. Compliance features are built as general-purpose audit and control features. | Rules were only read in blogs; verify with the broker. |

---

## 1. Goals, non-goals, success criteria

### Goals
1. Replace the fixed three-column terminal with a Dockview workspace: tabbed groups, splits, floating panels, pop-out windows, named and saved layouts.
2. Add three new capability areas the current dashboard lacks: **Risk**, **Performance analytics**, **Execution quality**, plus an **audit trail**, **alerts center** and **operations health** view.
3. Keep every capability the current dashboard has (parity list in section 6.3).
4. Make every number on screen answer three questions: *how old is it, where did it come from, can I trust it right now*.
5. Make the dangerous actions (kill switch, close position, reset portfolio, live arming) hard to do by accident and impossible to do without a record.
6. Meet WCAG 2.2 AA for everything the owner can operate, including a keyboard route for every Dockview drag operation (Dockview's keyboard docking is a paid feature, so we provide our own).

### Non-goals
- No change to scanner, setups, exits, risk limits, sizing, order router or broker adapters.
- No new trading features (for example the opening-gap pause, persistent Dhan login) in this project. They are separate specs. The UI must simply have room to show them later.
- No multi-user accounts, roles or permissions model. The existing dashboard capability key stays the one gate.
- No native app. No Dockview Enterprise. No new charting library (stay on `lightweight-charts`).
- No rewrite of the CSS design tokens; extend them.

### Success criteria (the cloud session proves each with evidence)
| ID | Criterion | Evidence |
|---|---|---|
| S1 | Every item in the parity checklist (6.3) is reachable in the new shell. | Checklist ticked with e2e test names. |
| S2 | Nothing the user sees is silently stale: each panel shows its own "as of" and goes visibly stale. | Unit tests per panel + e2e with frozen stream. |
| S3 | Layout save, restore, reset, rename, delete, pop-out and floating work; layout survives reload and a second browser. | Playwright specs. |
| S4 | Every dock operation has a keyboard path. axe reports 0 serious or critical violations on every workspace. | axe tests + manual keyboard script in plan. |
| S5 | Each mutating action writes one `action_audit` row with outcome. | Backend tests + UI test that audit panel shows it. |
| S6 | Initial JS (gzip) ≤ 450 KB; analytics and chart panels lazy-loaded; no dropped frames at 1 Hz stream plus 4 Hz tick coalescing with 300 signals and 200 trades. | Build report + performance test. |
| S7 | `tsc`, `vite build`, Vitest, Playwright, backend pytest all pass. One full paper session on the new shell with zero console errors. | CI-style run log + session log. |
| S8 | Rollback to the old terminal takes one flag flip, tested. | e2e. |

---

## 2. Current-state analysis (read from the repo on 2026-10-22)

### 2.1 Stack
- Frontend: React 18, Vite 5, TypeScript 5, Tailwind 3 with CSS variables (`frontend/src/index.css`), custom `desk-*` component classes, `lucide-react` icons, `lightweight-charts` 4, IBM Plex fonts. About 9,500 lines under `frontend/src` including tests. Tests: Vitest + Testing Library + axe-core; Playwright (4 specs under `frontend/e2e/specs`). At the last review (2026-10-20): 147 Vitest tests, 11 Playwright tests. Re-measure at start.
- Backend: FastAPI under `backend/app`, SQLite (WAL) via `services/db.connect`, ~87 test files. Served on 127.0.0.1:8001 by `bb-options.service`; the built frontend (`frontend/dist`) is served by caddy; deploy script replaces `backend/app` and `frontend/dist` and restarts only `bb-options.service`.
- Auth: a dashboard capability key kept in `localStorage` (`dashboard_capability`), exchanged at `POST /api/auth/session` for a cookie; `apiFetch` also sends `X-Dashboard-Capability`. Dhan token lives only in server memory; the browser stores a sentinel (`server_active` / `oauth_connected`) so it never holds a real token.

### 2.2 Shell today
`App.tsx` (636 lines) is a god component. It owns, in one place: the SSE connection to `GET /api/signals/stream` (default snapshot messages plus named `tick` and `portfolio` events), the initial `GET /api/signals` snapshot, 30 s polls for `/api/dashboard/trades` and `/api/dashboard/watch`, a closed-trades fetch keyed on closed count, stream-health timer (live / stale after 15 s / reconnecting), auth bootstrap, Dhan auto-reconnect, every action handler (scan now, paper buy, close, auto-trade toggle, kill switch, setup mode, reset portfolio), signal filtering, screen-reader announcements and the capability dialog. It then passes ~30 props into `Terminal`.

`Terminal.tsx` lays out three columns (Signals 19rem | Focus | Positions 20rem) over a "Blotter" with eight tabs (Positions, Signals, Trades, Session, Review, Earnings, Settings, Control). On < lg it becomes a four-pane switcher. `Header.tsx` (307 lines) carries brand, risk chip + kill switch, connection pills, scan, theme, dashboard key, Dhan connect dialog with OAuth/manual forms. `IndexHeroRadar` is the market strip. `ConnectionBanner` and `DashboardStatus` are alert bands.

### 2.3 Components worth keeping as panels
`SignalsPane`, `SignalTable`, `SignalDetails`, `FocusPane`, `PositionsPane`, `OpenPositionsPanel`, `PositionChartModal` (inline mode), `TradeChart` + `ReplayControls`, `TradesScreen` + `TradeDetail` + `TradeParts`, `SessionScreen` + `SessionTimeline` + `SessionInsights`, `JournalPanel`, `ReviewScreen` + `PaperPortfolioView` + `PortfolioStrips` + `SetupStatsPanel` + `CostPanel`, `TelemetryPanel`, `SettingsPanel`, `LiveRoutingPanel`, `EarningsPanel`, `ControlScreen`, `RiskControls`, `ConnectionStatus`, `DashboardStatus`, `IndexHeroRadar`, `ReceiptModal`, `Dialog` + `useDialog`, `Tabs` (roving tabindex), `LiveAnnouncer`, `BookFrame`, `format.ts`, `setupCode.ts`, `connectionState.ts`.

### 2.4 Backend surface (all under `/api`)
- `auth`: `POST session`, `GET/POST oauth/login-url`, `POST oauth/token`, `POST verify`, `GET status`, `POST disconnect`.
- `signals`: `GET ""`, `GET snapshot`, `GET state`, `POST scan-now`, `GET stream` (SSE), `POST close/{id}`.
- `paper`: `GET portfolio`, `GET daily`, `GET setup-stats`, `GET costs`, `POST trade`, `POST close/{id}`, `POST settings`, `POST reset`, `POST kill-switch`, `POST kill-switch/release`, `GET positions/{id}/chart`.
- `dashboard` (read model): `GET watch`, `GET trades`, `GET session?day=`, `GET trades/{book}/{id}`, `GET trades/{book}/{id}/chart`.
- `telemetry`: `GET dhan-rate-limit`, `insights`, `decisions`, `errors`, `excursions`, `performance`, `POST purge`.
- `journal`: `GET trades`, `PUT trades/{id}`, `GET export.csv`, `GET summary`, `GET summary.html`.
- `settings` (runtime): `GET ""`, `PUT ""`, `POST {key}/reset`, `GET audit`.
- `live`: `GET status`, `orders`, `audit`; `POST mode`, `arm`, `enable`, `resume`, `reconcile`, `positions/{id}/retry-exit`, `broker/login`, `broker/logout`.
- `earnings`: `GET summary`, `positions`, `candidates`, `calendar`; `POST calendar/sync`, `calendar`, `run-cycle`, `square-off`, `iv-history`; `DELETE calendar/{symbol}/{date}`.
- `swing` (backend only, no UI today), `readiness` (`GET ""`), `recorder` (`status`, `bars`), `universe` (`GET ""`).
- Existing data useful for the new analytics: `trades.db` tables `positions`, `trade_candles`, `trade_excursions` (MFE/MAE), `strategy_decisions`, `error_events`, `trade_journal`, `dashboard_trade_evidence`, `live_orders`, `live_audit`, `settings_audit`, `processed_signals`. `performance_report.build_report` already yields per-setup/symbol/side/hour/exit-reason buckets and an equity curve.

### 2.4.1 Fields present on a closed trade (usable for analytics)
`entry_slippage`, `exit_slippage`, `total_slippage_cost`, `theoretical_entry/exit`, `gross_pnl`, `total_charges`, `charges_breakdown`, `net_pnl`, `booked_pnl_rupees`, `entry_bid`, `entry_spread_pct`, `option_volume`, `option_oi`, `bid_qty`, `ask_qty`, `entry_estimated`, `exit_reason`, `quarantine_reason`, `initial_lots`, `booked_lots`, plus MFE/MAE from `trade_excursions`. Anything not recorded (for example signal-to-fill delay) is shown as "not recorded", never estimated.

### 2.5 Gaps versus an institutional desk
1. **No risk view.** Only a header chip (day P&L vs cap) and the kill switch. No open-risk in rupees, no exposure by underlying/side/pool, no "why entries are blocked" panel.
2. **No performance analytics UI** beyond tables: no equity curve with drawdown, no distributions, no attribution drill-down, no date-range control.
3. **No execution-quality view.** Slippage and charges are totals; no distribution, no per-setup/hour breakdown, no spread-at-entry analysis.
4. **No action audit.** Settings changes and live-routing events are logged; paper close, kill switch, toggle, reset, scan, mode changes are not.
5. **Per-panel freshness is missing.** One stream pill; polled sections do not show their own age.
6. **Alerts are bands and a screen-reader announcer**, not an acknowledged, history-keeping alerts list.
7. **Layout is fixed**, one monitor, no pop-out, no saved views; navigation by hidden tabs inside a single "Blotter".
8. **`App.tsx` is a god component**; data, actions and layout are tangled, so adding views multiplies props.
9. **Browser `window.confirm`** is used for dangerous actions (kill switch, reset): not accessible, no audit, no typed confirmation.
10. **Tables lack institutional behaviour**: no column chooser, sort memory, CSV export, row keyboard navigation, virtualisation.

---

## 3. Dockview: what we can and cannot rely on

Facts fetched on 2026-10-22 from `dockview.dev` (licence and overview pages) and the GitHub README:

- Repository is MIT except `dockview-enterprise`, which is proprietary under a commercial licence (30-day trial). Each published package ships its own `LICENCE.md`, which is authoritative.
- Package `dockview-react` has peer dependency React 16.8–19. Our React 18.2 is supported.
- In the **free MIT core**: docking and tabs, splitting, floating groups, pop-out windows, save and restore of layouts ("serialization / deserialization with full layout management"), theming.
- **Paid only** (we must not use or assume them): advanced tab overflow with search, multi-row tabs, pinned tabs, auto-hide edge groups, dock-to-edge groups, DnD compass, smart guides, layout history, **spatial keyboard navigation, keyboard docking**.
- Not stated on the fetched pages, so **Phase 0 must verify in the installed version**: exact serialization method names, accessibility semantics of tabs (roles, focus), whether pop-out windows copy stylesheets and keep React context, bundle size, behaviour of pop-out in Safari and when blocked, theming variable names.

### Consequences for the design
1. **Keyboard parity is ours to build.** Every operation Dockview offers by mouse gets a command (section 11.3) that calls the Dockview API: focus next/previous group, move panel to group N, split right/down, float, pop out, close, maximise, restore. Available from the command palette and the panel's header menu.
2. **Layout history** (paid) is replaced by our own server-side snapshots: automatic snapshot on layout change (debounced, last 20 per workspace) plus "Revert to…".
3. **Pop-out context.** If pop-out panels render into the opener's React tree through portals (to be verified), the store and handlers keep working in the pop-out. If not, Phase 0 picks one of: (a) a `BroadcastChannel` bridge, or (b) disable pop-out and keep floating groups. The decision rule is written in the plan.
4. **We do not wrap Dockview in an abstraction we do not need.** One module (`shell/dockHost.tsx`) touches Dockview; panels never import it.
5. **Pin the exact Dockview version** in `package.json` (no caret) and record it in `docs/DOCKVIEW_NOTES.md`.

---

## 4. What "institutional grade" means here (requirements)

Eight pillars, each with a testable rule. IDs are referenced by the plan.

### P1. Controls and safety (pre-trade and emergency)
- **R1.1** Kill switch is visible in the top chrome on every workspace, on every viewport, and never inside a dock panel (so it cannot be closed, floated away or hidden).
- **R1.2** Kill switch, "Close all", close-position, reset portfolio, live arm/enable, live mode change and settings that change risk limits use a shared accessible confirmation dialog (no `window.confirm`). Kill switch and live enable require a typed phrase or code (live enable already does server-side; the UI keeps it).
- **R1.3** A mode banner is always visible: `PAPER`, `LIVE DRY RUN`, or `LIVE ARMED` (distinct colour **and** text **and** icon). Source: `/api/live/status` + `paper_portfolio`.
- **R1.4** A "why are entries blocked?" explanation is one click from the chrome: kill switch, daily loss cap, pool caps (`capped_pools`), auto-enter off, max open positions, market closed, feed stale. Source: `RiskStatus` plus portfolio fields.
- **R1.5** Every mutating UI action is sent once (button disabled in flight, idempotent where the API allows), shows the server's result (success or the server's `detail`), refreshes canonical state, and is audited (R6.1). No optimistic updates for money actions.

### P2. Data integrity and freshness
- **R2.1** Every panel header shows "as of HH:MM:SS IST" for its data and a stale badge when older than that source's threshold (stream 15 s, polled 2× interval, snapshots by source). Stale means visible text, not colour alone.
- **R2.2** When the stream is `reconnecting` or `stale`, a global banner appears and price-bearing panels dim and label their numbers "frozen" (reuse `connectionState`).
- **R2.3** One source of truth per datum. Panels never fetch what the store already has; the store never duplicates server state in two shapes.
- **R2.4** Unrecorded evidence is rendered "not recorded", never blank and never estimated. Estimated values are labelled "est." (existing `entry_estimated`, `net_kind`).
- **R2.5** Times are IST with the zone shown on first use per panel; numbers use Indian digit grouping for rupees, tabular monospace, fixed decimals per field type (premium 1–2 dp, percent 1–2 dp, rupees 0 dp).

### P3. Performance analytics
- **R3.1** Equity curve with drawdown shading, max drawdown, current drawdown, longest drawdown (days), for a chosen date range and book.
- **R3.2** Attribution by setup, symbol, side (CE/PE), entry hour, weekday, exit reason; each bucket shows trades, win rate, net, gross, charges, slippage, profit factor, expectancy, average R, payoff, max consecutive losses.
- **R3.3** Distributions: net P&L histogram, R-multiple histogram, holding-time histogram, MFE vs MAE scatter, "winners that gave back" and "losers that were green" (data exists in `PerfBucket`).
- **R3.4** Cost drag: charges and slippage as a percentage of gross P&L, per setup and in total.
- **R3.5** Small samples are flagged: any bucket with fewer than 20 trades carries a "low sample" badge and no confident colouring. A visible note says metrics on short histories are unreliable.
- **R3.6** All analytics are computed server-side from stored trades, are read-only, and take `from`, `to`, `book`, `setup` filters.

### P4. Execution quality
- **R4.1** Slippage distribution (entry, exit, in points and rupees), by setup, hour, and symbol type (index/stock).
- **R4.2** Spread-at-entry analysis (`entry_spread_pct`), with cost impact; relation between spread and slippage.
- **R4.3** Liquidity at entry (volume, OI, bid/ask quantity) versus slippage.
- **R4.4** Charges breakdown (brokerage, STT, exchange, SEBI, stamp, GST) as stacked totals and per trade.
- **R4.5** Live-routing view (orders, fills, state per position, last error, retry exit) when routing is on; empty state explains how to enable.
- **R4.6** If signal-to-fill delay is not recorded, the panel says so and offers no number. (Recording it is a separate backend task; see out of scope.)

### P5. Risk monitoring (read-only)
- **R5.1** Rupee risk at stop for each open position and in total (`quantity × (entry − stop)` on the option premium, using the stored stop), loss-cap used %, remaining headroom.
- **R5.2** Exposure by underlying, side, pool (`main`, `s11`, `f21`–`f23`) and setup; concentration warning when one underlying or side exceeds a configurable display threshold (UI-only, stored with the layout, default 50 % of open count).
- **R5.3** Open positions count versus the configured maximum, with the setting key shown.
- **R5.4** Pool caps and `capped_pools` shown with the reason.

### P6. Audit and compliance
- **R6.1** New `action_audit` table records every non-GET API call that changes state: timestamp (IST), route, method, summarised target (position id, setting key, mode), outcome (`ok`/`error`), HTTP status, message, client address. Secrets are never stored (no bodies for `/auth/*`, `/live/broker/*`, `/live/enable`).
- **R6.2** One "Audit trail" panel merges `action_audit`, `settings_audit`, `live_audit`, and `live_orders`, filterable by source, text, date; exportable to CSV.
- **R6.3** End-of-day report: one button produces the day's blotter CSV and the existing `/api/journal/summary.html`; includes charges, slippage, risk events.
- **R6.4** Settings panel shows the audit rows for the selected setting and who changed it (existing `actor`).
- **R6.5** Records are retained; the UI has no delete for audit rows.

### P7. Operability
- **R7.1** Health panel aggregates: stream age, feed mode, Dhan token expiry countdown, Dhan 429 count and cooldown (`/api/telemetry/dhan-rate-limit`), scanner cycle and last scan, readiness checks (`/api/readiness`), recorder status (`/api/recorder/status`), live broker session, last errors (`/api/telemetry/errors`), build id.
- **R7.2** Alerts center: an ordered, acknowledgeable list of events raised by state transitions (kill switch on/off, loss cap tripped, pool capped, feed stale, stream reconnect, Dhan disconnect, readiness fail, order rejected, new error events). Persists acknowledgements in `localStorage`; keeps the last 200.
- **R7.3** Status bar at the bottom of the chrome: per-source freshness dots (text + icon), scan cycle, session clock, market session state (pre-open / open / closed) in IST.

### P8. Ergonomics
- **R8.1** Workspaces: Trading, Risk, Performance, Execution, Review, Operations, Earnings. User can save, rename, delete, reset, export and import layouts.
- **R8.2** Command palette (`Ctrl/Cmd+K`): open any panel, switch workspace, run safe actions, change filters, jump to a symbol. Dangerous commands go through the confirmation dialog.
- **R8.3** Linked selection: choosing a signal, position, candidate or trade in any panel updates Focus and Chart panels. A panel can be pinned to ignore selection changes.
- **R8.4** Tables: sortable, column chooser, sticky header, row keyboard navigation (arrows, Enter), CSV export, filters remembered per panel, windowing for > 150 rows.
- **R8.5** Density: compact (default on desktop) and comfortable.
- **R8.6** Both light and dark themes retained; Dockview themed through our tokens.

---

## 5. Architecture

### 5.1 Layering (one-way dependencies, top uses bottom)

```
 shell/     Chrome (top bar, mode banner, status bar, workspace switcher)
            DockHost (the only Dockview import), MobileShell
 panels/    one folder per panel, each registered in panels/registry.ts
 features/  alerts, audit, commands (palette), confirm, layouts, selection
 data/      store (SSE + polling + selectors), actions (the only code that calls mutating APIs), api clients
 lib/       format, time, connectionState, csv, table hooks, a11y helpers
 theme/     tokens.css, dockview-theme.css, density
```

Rules: panels import from `data`, `features`, `lib`; **never** from `shell`. `shell` imports `panels/registry`. `data` imports nothing from React UI. This is what lets pop-out windows and the mobile shell reuse panels unchanged.

### 5.2 Data store (replaces the logic in `App.tsx`)
- A framework-light external store (`createStore` + `useSyncExternalStore` selectors) in `frontend/src/data/store.ts`. No new state library.
- **Slices:** `stream` (health), `scanner` (signals, radar, mode, feed, scan progress), `portfolio` (paper portfolio incl. open positions and risk), `closedTrades`, `watch`, `trades`, `live`, `health`, `selection`, `alerts`, `ui` (density, theme, active workspace).
- **Sources:** one `EventSource` to `/api/signals/stream` (default snapshots + `tick` + `portfolio` events), reconnect after 3 s (current behaviour), stale after 15 s; timers for polled endpoints (`/dashboard/trades` 30 s, `/dashboard/watch` 30 s, `/live/status` 15 s while routing is not `off`, `/readiness` 60 s, `/telemetry/dhan-rate-limit` 60 s, `/recorder/status` 60 s). Polls pause when the tab is hidden and resume with an immediate fetch.
- **Tick coalescing:** `tick` events update a mutable buffer; the store flushes the buffer to state at most every 250 ms (`requestAnimationFrame` + timestamp guard).
- **Equality:** snapshots keep prior object identity for unchanged sub-trees (generalising today's `sameJson` for signals) so selectors do not re-render.
- **Per-slice metadata:** `{ asOf, status: 'idle'|'loading'|'ready'|'stale'|'error', error? }`. Panels read it through `useSliceMeta(name)` and render `PanelFrame` badges from it.
- **One owner of the connection:** if a pop-out window exists, it shares the store of the opener (same JS realm). If Phase 0 shows pop-outs cannot share it, `data/bridge.ts` mirrors the store through `BroadcastChannel`; panels do not change.
- **Auth:** `data/auth.ts` keeps `bootstrapDashboardSession`, capability storage and the 401 → capability dialog behaviour; the Dhan context (`DhanAuthContext`) stays as is.

### 5.3 Actions (`data/actions.ts`)
The only module that performs mutating calls. Each action: validates input, sets an in-flight flag in the store, calls `apiFetch`, handles 401 (opens the capability dialog), maps server `detail` to a message, refreshes the canonical slice, returns `{ok, message}`. Actions: `scanNow`, `paperBuy`, `closePosition`, `toggleAutoTrade`, `setSetupMode`, `killSwitch(engage)`, `resetPortfolio`, `updateSettings`, `resetSetting`, `liveMode/arm/enable/resume/reconcile/retryExit/brokerLogin/brokerLogout`, `earnings.*`, `journal.save`, `layouts.*`. UI components call actions; they never call `apiFetch` for a mutation.

### 5.4 Panel contract
```ts
interface PanelDefinition {
  id: PanelId;                      // stable, never reused
  title: string;
  icon: IconName;
  component: React.LazyExoticComponent<React.FC<PanelProps>> | React.FC<PanelProps>;
  category: 'trading'|'risk'|'performance'|'execution'|'operations'|'books';
  singleton: boolean;               // only one allowed in a layout
  defaultSize?: { w: number; h: number };   // floating default
  sources: SliceName[];             // freshness shown in the frame
  paramsSchema?: ZodLike;           // validation of saved per-panel params
  minWidth?: number; minHeight?: number;
}
```
Every panel renders inside `PanelFrame` (title row with as-of/stale badge, panel menu: Float, Pop out, Move to group…, Maximise, Close, Export CSV when relevant, Help). Panels get `{ api, params, setParams }`; `setParams` persists per-panel UI state (filters, sort, tab, range) into the layout.

### 5.5 Layout service
- `layoutModel.ts` (pure, fully unit-tested): `PRESETS` (one `LayoutSpec` per workspace, expressed in our own simple tree: groups, splits, sizes, panel ids, params), `validate(layout, registry)`, `migrate(layout)`, `fromDockview(json)`, `toDockview(spec)`, `diff`. Unknown panel ids are dropped with a warning; if validation fails the preset is used and an alert is raised.
- `layoutApi.ts`: server persistence (`/api/ui/layouts`), `localStorage` cache, debounce 800 ms, snapshots, conflict rule "last write wins, newest `updated_at`".
- `schema_version` in every stored layout. Migration functions are append-only and tested with fixtures.

### 5.6 Shell
- `Chrome` (fixed, outside Dockview): brand, workspace switcher, mode banner, day P&L and loss-cap meter, open count, kill switch, connection pills, market session clock (IST), scan now, command palette trigger, density, theme, Dhan connect / token countdown, dashboard key. Status bar below the dock.
- `DockHost`: the `DockviewReact` instance, registry-driven `components`, header actions (our panel menu), watermark (empty-group help), floating groups bounded to the dock, pop-out management, layout events → `layoutApi`.
- `MobileShell` (< 1024 px): bottom tab bar (Signals, Detail, Positions, Tables, More); "More" lists every registered panel (full-screen, one at a time). Chrome collapses to the same essentials plus a "Tools" sheet (current mobile behaviour). The mode banner and kill switch stay visible.

### 5.7 Theming
`theme/tokens.css` keeps current variables (`--bg`, `--panel`, `--line`, `--accent`, `--up`, `--down`, `--warn`, …) and adds: `--density-row`, `--density-pad`, `--focus-ring`, `--mode-paper`, `--mode-dry`, `--mode-live`, `--stale`. `theme/dockview-theme.css` maps Dockview's CSS variables (names confirmed in Phase 0) to our tokens for both `:root` and `:root.dark`. Tailwind config unchanged except new colour tokens.

### 5.8 Routing and URLs
No router library. Query flags: `?shell=legacy|dock`, `?workspace=<name>`. Hash `#panel=<id>` opens a panel (used by "open in new window" links and by pop-out).

---

## 6. Panel catalogue

### 6.1 Catalogue

| Panel id | Title | Cat. | Built from | Primary data (slice) | Actions |
|---|---|---|---|---|---|
| `signals` | Signals and watch | trading | `SignalsPane`, `SignalTable` | scanner, watch | select, filters |
| `focus` | Focus | trading | `FocusPane`, `SignalDetails`, `WatchCandidateDetail` | scanner, portfolio, watch | paper buy, close, open trade, pin |
| `positions` | Open positions | trading | `PositionsPane`, `TodaySummary` | portfolio | close, auto-enter |
| `positions-table` | Positions blotter | trading | Blotter `PositionsTable` + `OpenPositionsPanel` | portfolio | close, export |
| `chart` | Chart | trading | `PositionChartModal` inline, `TradeChart`, `ReplayControls` | selection, chart API | replay |
| `market` | Market radar | trading | `IndexHeroRadar` (expanded) | scanner.radar | select index |
| `trades` | Trades | trading | `TradesScreen`, `TradeDetail`, `TradeParts`, `ReceiptModal` | trades | close paper trade, export |
| `session` | Session timeline | trading | `SessionScreen`, `SessionTimeline`, `SessionInsights` | `/dashboard/session` | open trade |
| `journal` | Journal | review | `JournalPanel` | `/journal/*` | save notes, export |
| `risk` | Risk overview | risk | new | portfolio.risk, positions, settings | explain block, kill switch (chrome) |
| `exposure` | Exposure | risk | new | portfolio.active_positions | none |
| `controls` | Entry controls | risk | `ControlScreen` + setup switches from `PaperPortfolioView` | portfolio | auto-enter, setup modes, scan now, reset |
| `live` | Live routing | execution | `LiveRoutingPanel` | `/live/*` | mode, arm, enable, reconcile, retry |
| `orders` | Orders and fills | execution | new view over `/live/orders` | live | none |
| `audit` | Audit trail | risk | new | `/audit/actions`, `/settings/audit`, `/live/audit` | export |
| `settings` | Runtime settings | risk | `SettingsPanel` | `/settings` | update, reset |
| `perf-summary` | Performance summary | performance | new + `PortfolioStrips` | `/analytics/*` | date range |
| `equity` | Equity and drawdown | performance | new (lightweight-charts) | `/analytics/equity` | range |
| `attribution` | Attribution | performance | new, uses `PerfBucket` | `/analytics/attribution` | group-by, drill |
| `distributions` | Distributions | performance | new | `/analytics/distribution` | none |
| `setup-stats` | Setup stats | performance | `SetupStatsPanel` | `/paper/setup-stats` | none |
| `costs` | Costs | execution | `CostPanel` | `/paper/costs` | none |
| `execution` | Execution quality | execution | new | `/analytics/execution` | filters |
| `health` | System health | operations | new | health slice | none |
| `alerts` | Alerts | operations | new | alerts slice | acknowledge, clear |
| `telemetry` | Decisions and errors | operations | `TelemetryPanel` | `/telemetry/*` | none |
| `readiness` | Readiness | operations | new view over `/readiness` | health | none |
| `recorder` | Recorder | operations | new view over `/recorder/status` | health | none |
| `universe` | Universe | operations | new view over `/universe` | `/universe` | none |
| `earnings` | Earnings book | books | `EarningsPanel` | `/earnings/*` | existing actions |

Notes: `swing` has backend routes but no UI today; it is out of scope for the UI (listed in section 14).

### 6.2 New panel behaviours (the ones with real design content)

**`risk` (Risk overview).** Top row: mode banner state, day P&L vs cap as a labelled meter (`day_pnl` / `daily_loss_limit`; text value always shown; disabled cap shows "Loss cap off"), entries state (Allowed / Blocked) with the ordered list of block reasons. Below: table of open positions with rupee risk at stop, distance to stop in %, T1 status, pool. Footer: open count versus configured maximum (key shown), capped pools with reasons. Empty state: "No open positions. Entries are Allowed." Every value has a tooltip naming its source field.

**`exposure`.** Four small tables (by underlying, side, pool, setup) with count, quantity, premium at risk, share of total. A concentration banner appears when the display threshold is exceeded. No charts needed; bars are inline `desk-bar` elements with text values.

**`perf-summary`.** KPI row (net, gross, charges, slippage, trades, win rate, profit factor, expectancy, average R, max drawdown) with range selector (Today, 5D, 20D, All, Custom) and book selector. Low-sample note per R3.5.

**`equity`.** Equity line + drawdown area (lightweight-charts, two panes or area series on a second scale), range selector, hover readout with date, equity, drawdown. Table of the five deepest drawdowns (start, trough, recovery, depth).

**`attribution`.** Group-by selector (setup, symbol, side, hour, weekday, exit reason). Sortable table with the R3.2 metrics, inline bars for net and win rate, low-sample badge, row click filters `trades` panel and `perf-summary` (linked filter stored in selection slice as `filter`).

**`distributions`.** Four compact histograms (SVG, no chart library needed): net P&L, R-multiple, hold time; and MFE vs MAE scatter. Each has a bin-size control and a text summary (median, 10th and 90th percentile) for screen readers.

**`execution`.** Slippage by setup/hour (bars), entry vs exit slippage histogram, spread-at-entry vs slippage scatter, liquidity quartiles vs slippage table, charges stacked bar, cost drag per setup. All show "not recorded" where fields are missing.

**`audit`.** Unified table (time, source, actor, action, target, outcome, detail). Filters: source, outcome, text, date. Row expands to show before/after for settings. CSV export. No delete.

**`health`.** Grid of status tiles (Stream, Feed, Dhan token, Rate limit, Scanner, Recorder, Readiness, Live broker, Errors). Each tile: state word + icon, as-of, one-line detail, link to the owning panel. "Copy diagnostics" button copies a JSON blob of the health slice.

**`alerts`.** List newest first, severity (info / warning / critical), source, message, time, Acknowledge, Acknowledge all. Rules table at the bottom (read-only list of what raises alerts). Critical alerts also announce through `LiveAnnouncer` and are mirrored to the chrome as a count badge. Optional browser notifications and sound are off by default (setting in `ui` slice).

**`controls`.** Merged `ControlScreen` and setup switches: auto-enter toggle with state sentence, setup mode matrix (per setup: off / index / stocks / all / nifty / banknifty as supported), scan now, reset portfolio (confirmation), dashboard key.

### 6.3 Parity checklist (every row must be reachable in the new shell)
1. Signals list with filters (setup, CE/PE, index/stock, timeframe incl. new 3m), sorting, "watching" candidates, selection.
2. Focus view for signal (levels, indicators, rationale, paper buy), position (levels, stats, close), candidate (checks, block reason, open trade).
3. Open positions list with close; positions table with columns and close.
4. Chart for a selected position with indicators per setup and replay of closed trades.
5. Trades list and detail with evidence state, chart, receipt, close paper trade, refresh.
6. Session timeline for a chosen day with observations and links to trades.
7. Review: today, trades, setups, costs, analytics (`TelemetryPanel`), journal notes.
8. Earnings book: summary, positions, candidates, calendar CRUD, sync, IV import, run cycle, square off.
9. Runtime settings with audit; reset per key.
10. Live routing panel: mode, arm, enable, resume, reconcile, broker login/logout, retry exit, orders.
11. Control: auto-enter, kill switch, scan now, dashboard key, setup modes, reset.
12. Header: risk chip, connection pills, scan cycle, theme toggle, Dhan connect (OAuth and manual forms), disconnect, token countdown, dashboard key dialog.
13. Index radar strip; connection banner; dashboard status banner; action error banner.
14. Screen-reader announcements for new signals and risk state; `LiveAnnouncer` kept.
15. Dhan auto-reconnect when mode is demo and a real saved token exists (sentinel filtering preserved).
16. Light and dark themes; reduced-motion respected.
17. Phone layout with four-pane switcher.

---

## 7. Workspaces (default layouts)

Layouts are our own tree; sizes are proportions. `|` = side by side, `/` = stacked, `[a b c]` = tabs in one group.

| Workspace | Layout |
|---|---|
| **Trading** (default) | `[ [signals, earnings-watch*] 22% | ( [focus, chart] 56% / [positions-table, trades, session] 34% ) | [positions, risk] 22% )`. *`earnings-watch` is the `signals` panel with the `watching` mode and earnings filter; not a separate panel.* |
| **Risk** | `( [risk] 40% | [exposure] 30% | [controls] 30% ) / ( [positions-table] 55% | [audit, alerts] 45% )` |
| **Performance** | `( [perf-summary] full width, 14% ) / ( [equity] 55% | [attribution] 45% ) / ( [distributions] 50% | [setup-stats, costs] 50% )` |
| **Execution** | `( [execution] 55% | [live, orders] 45% ) / ( [costs] 40% | [trades] 60% )` |
| **Review** | `( [session] 40% | [journal] 30% | [trades] 30% ) / ( [telemetry] full )` |
| **Operations** | `( [health] 40% | [alerts] 30% | [readiness, recorder] 30% ) / ( [telemetry] 60% | [universe, settings] 40% )` |
| **Earnings** | `[earnings] full` |

Every workspace is editable; **Reset workspace** returns to the preset. Presets live in code (`layoutModel.PRESETS`) and are versioned; a user layout stores `based_on` and `preset_version`, so a preset upgrade can offer "Update to new default" without overwriting changes.

---

## 8. Backend additions (additive only; trading code untouched)

All new routes sit under existing routers' conventions (`/api` prefix, capability dependency as other routes), pydantic response models, and tests in `backend/tests`.

### 8.1 Tables (created with `CREATE TABLE IF NOT EXISTS` in a new `services/ui_store.py` and `services/action_audit.py`, same style as other services, using `db.connect`)
```sql
CREATE TABLE IF NOT EXISTS ui_layouts (
  name TEXT PRIMARY KEY,            -- e.g. 'workspace:Trading', 'custom:My view'
  kind TEXT NOT NULL,               -- 'workspace' | 'custom'
  schema_version INTEGER NOT NULL,
  body TEXT NOT NULL,               -- JSON
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ui_layout_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, body TEXT NOT NULL, taken_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ui_snap_name ON ui_layout_snapshots(name, id);
CREATE TABLE IF NOT EXISTS action_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, method TEXT NOT NULL, route TEXT NOT NULL,
  action TEXT NOT NULL,             -- stable verb: 'paper.close', 'kill_switch.engage', ...
  target TEXT, outcome TEXT NOT NULL, status INTEGER NOT NULL,
  detail TEXT, client TEXT
);
CREATE INDEX IF NOT EXISTS idx_action_audit_ts ON action_audit(ts);
```

### 8.2 Action audit
FastAPI middleware (`app/core/audit_middleware.py`) records every `POST/PUT/DELETE` under `/api` **after** the response is known, with an allowlist map `route pattern → (action, target extractor)`. Unknown mutating routes are recorded as `unknown.<route>` so nothing is silently missed. Never stores request bodies; for `/auth/*`, `/live/broker/*`, `/live/enable` stores action and outcome only. Write failures are logged and swallowed (audit must never break an action). Retention: keep all rows; add a read-only `GET /api/audit/actions?limit=&since=&action=&outcome=`.

### 8.3 Layout API
`GET /api/ui/layouts` (list + bodies), `PUT /api/ui/layouts/{name}` (validates JSON size ≤ 256 KB and `schema_version` integer; inserts snapshot, keeps last 20 per name), `DELETE /api/ui/layouts/{name}` (custom only), `GET /api/ui/layouts/{name}/snapshots`, `POST /api/ui/layouts/{name}/restore/{snapshot_id}`.

### 8.4 Analytics API (read-only; computed from closed trades, excursions)
New `services/analytics.py` and `api/analytics.py`. All accept `from`, `to` (IST dates), `book` (`paper` default; `all`), `setup`, `side`.
- `GET /api/analytics/equity` → `{points:[{t, equity, day_pnl, drawdown}], summary:{net, max_drawdown, current_drawdown, longest_drawdown_days, drawdowns:[{start,trough,end,depth}]}}`.
- `GET /api/analytics/attribution?group=setup|symbol|side|hour|weekday|exit_reason` → `{group, buckets:[PerfBucket + cost_drag_pct + low_sample]}`.
- `GET /api/analytics/distribution` → `{pnl:[bins], r:[bins], hold_minutes:[bins], mfe_mae:[{id, mfe, mae, final}], medians:{...}}`.
- `GET /api/analytics/execution` → `{slippage:{entry:[..], exit:[..], by_setup:[..], by_hour:[..]}, spread:{points:[{spread_pct, slippage}], buckets:[..]}, liquidity:{quartiles:[..]}, charges:{totals:{brokerage,stt,exchange_fee,sebi_fee,stamp_duty,gst}, by_setup:[..]}, not_recorded:[fields absent]}`.
- `GET /api/analytics/risk` → `{open:[{id, symbol, setup, pool, qty, entry, stop, risk_rupees, distance_pct, t1}], totals:{risk_rupees, notional, count, max_open, max_open_key}, by_underlying:[..], by_side:[..], by_pool:[..], by_setup:[..]}`.
Reuse `performance_report._bucket` for bucket maths (move shared helpers into `analytics.py` without changing `performance_report` behaviour; keep its tests green). Quarantined trades (`quarantine_reason`) are excluded and counted in `excluded`.

### 8.5 Not added
No ops-health endpoint (aggregate existing endpoints in the store). No write endpoints for analytics. No changes to order router, paper trader or scanner.

---

## 9. Action safety standard

1. **Confirmation dialog** (`features/confirm`): accessible modal (focus trap, `Esc` to cancel, initial focus on Cancel for destructive actions), title states the effect, body lists what will change (for kill switch: number of open positions and their symbols), optional typed phrase (`KILL`, or the live-enable code/phrase the server already requires).
2. **Kill switch** engage: confirm + typed phrase; release: confirm. Result lists any `failed` closes with symbols (current server response `failed[]`).
3. **Close position**: single confirmation showing symbol, current P&L and "Net if closed" (`est_net_pnl`); batch "Close all" uses the kill-switch standard minus the entry block.
4. **Reset portfolio**: confirm with the server's explanatory text (archived, not deleted; loss cap stays; refused while a live position is open).
5. **Risk-limit settings**: changing any setting in groups tagged risk shows old → new in the confirm dialog.
6. Each action returns an outcome toast (non-blocking, announced) and a row in the audit trail.
7. Double-submit guard and in-flight state per action key.
8. Keyboard: kill switch has a documented shortcut (`Ctrl+Shift+K`) that **opens** the confirmation, never executes.

---

## 10. Freshness and connection model

- `connectionState()` is reused unchanged as the single source for the global pill and banner.
- Slice thresholds: stream 15 s; `/dashboard/*` 2× 30 s; `/live/status` 2× 15 s; readiness/rate-limit/recorder 2× 60 s; analytics are "computed at" the server timestamp returned in each response (`generated_at`) and refreshed when closed-trade count changes or every 120 s.
- A panel is *stale* when `now − asOf > threshold`; its header shows "Stale 47 s" with icon, and price cells get `data-frozen` (dimmed, dashed underline). A panel in `error` keeps the last good data under an error strip rather than blanking.
- Pop-out windows show the same state; if the opener's stream dies, they show the global banner.

---

## 11. Alerts, command palette, hotkeys, keyboard parity

### 11.1 Alert rules (client, in `features/alerts/rules.ts`, each a pure function of two consecutive store states, unit-tested)
kill switch on/off; loss cap tripped; pool capped; entries blocked reason changed; stream reconnecting/stale/recovered; feed state error/stale; Dhan disconnected / token under 1 h; rate-limit cooldown active; readiness check failed; live halted; order rejected or failed (from `/live/orders`); position closed by stop (info) and by quarantine (warning); new `error_events` since last poll (critical when severity high).

### 11.2 Command palette
Fuzzy search over: open panel (every registry entry), switch workspace, save/reset layout, selection jump ("go to NIFTY…"), safe actions (scan now, refresh), dangerous actions (kill switch, close all, reset: open confirmation only), theme, density, shortcuts help. Results show a keyboard hint. Implemented as an accessible combobox dialog (`role="dialog"`, `aria-activedescendant`).

### 11.3 Dock keyboard parity (our replacement for Dockview Enterprise keyboard docking)
Commands (palette + panel menu + shortcuts; names are final):
`Focus next group` `Alt+]`, `Focus previous group` `Alt+[`, `Next tab` `Ctrl+Alt+→`, `Previous tab` `Ctrl+Alt+←`, `Move panel to next group` `Alt+Shift+]`, `Move panel to previous group` `Alt+Shift+[`, `Split right` / `Split down` (palette), `Float panel`, `Dock floating panel`, `Pop out`, `Maximise / restore group` `Alt+M`, `Close panel` `Alt+W`, `Reset workspace`. Shortcut table is visible in a help dialog (`?`). Shortcuts are ignored while typing in inputs and never collide with the kill-switch shortcut. All shortcut definitions live in one file so conflicts are testable.

### 11.4 Accessibility specifics
- Chrome landmarks: `header`, `nav` (workspaces), `main` (dock), status bar as `role="status"` region. Each panel is `role="region"` with `aria-labelledby` its title.
- Dockview's own tab strip must expose tab semantics; if the free edition does not, `dockHost` adds `role`/`aria-selected` via header components (decided in Phase 0).
- Colour is never the only signal: pills carry symbols (existing pattern), stale/blocked/error use words and icons.
- Contrast ≥ 4.5:1 for text, ≥ 3:1 for UI parts in both themes (axe + manual token check).
- Targets ≥ 24×24 px on desktop (WCAG 2.2 target size minimum), 44 px on coarse pointers (existing media rule).
- Charts: every chart has a text summary and a data table toggle.
- Reduced motion: no transitions beyond focus (existing rule).

---

## 12. Visual and interaction design

- Retain the current visual identity (IBM Plex, flat panels, accent blue); change hierarchy and density, not brand.
- Density tokens: row height 24 px compact / 32 px comfortable; font sizes remain `--fs-*`.
- Panel chrome: 28 px tab strip, 24 px title/status row. Group borders 1 px `--line`; active group border `--accent` 1 px (not colour alone: the active tab also has an underline and bold).
- Numbers: monospace tabular, right-aligned, sign always shown for P&L, unit suffix in header not cell.
- Empty, loading, error states are designed for every panel: skeleton (existing `desk-skel`), "No data for this range", error strip with Retry.
- Mode banner: 24 px strip above the chrome, hidden only for plain `PAPER` (a small `PAPER` pill remains in the chrome); `LIVE DRY RUN` amber with icon + text; `LIVE ARMED` red with icon + text and pulsing disabled under reduced motion.

---

## 13. Performance budgets and technical risks

| Topic | Budget / rule |
|---|---|
| Initial JS (gzip) | ≤ 450 KB. Lazy-load: analytics panels, `lightweight-charts` panels, earnings, settings. Measure with `vite build` report at Phase 0 and each phase. |
| Stream handling | 1 Hz snapshots + sub-second ticks; ticks coalesced to ≤ 4 flushes/s; unchanged sub-trees keep identity. |
| Render cost | Selector-based subscriptions; no panel re-renders on unrelated slices (tested with render counters). |
| Tables | Windowing above 150 rows (`@tanstack/react-virtual`, MIT, the only new runtime dependency besides Dockview). |
| Layout writes | Debounced 800 ms; max 1 write/s; snapshots at most every 60 s. |
| Memory | Alert list capped 200; audit panel pages 200 rows; charts dispose on unmount. |
| Dockview in jsdom | Layout needs real sizes: unit-test panels and `layoutModel` in Vitest; test the dock itself in Playwright. |

Technical risks and mitigations are in section 15.

---

## 14. Out of scope (explicitly)
Opening-gap pause, persistent Dhan login, any new setup or exit logic, recording signal-to-fill delay, per-endpoint Dhan pacing, swing book UI, multi-user, native mobile, charts beyond `lightweight-charts`, backtesting UI, SEBI/broker compliance claims, 2027 holiday list (separate reminder), and any change to deploy scripts beyond serving the new `dist`.

---

## 15. Risks and decisions

| Risk | Likelihood | Mitigation / decision rule |
|---|---|---|
| Pop-out windows lose the store or styles | Medium | Phase 0 test. If panels render into the opener's React tree (portal), proceed. Else use `BroadcastChannel` bridge. If neither is reliable in two days of effort, ship without pop-out and keep floating groups. |
| Dockview free tab strip lacks accessible semantics | Medium | Add roles through header components; if impossible, use Dockview with `tabComponent` replaced by our `Tabs` look-alike. Acceptance is axe = 0 serious. |
| Layout JSON from Dockview changes between versions | Medium | Pin exact version; store our own `LayoutSpec` plus Dockview JSON; migration tests; fallback to presets. |
| Bundle growth | Low–Medium | Lazy panels; budget gate in the plan; drop `lucide-react` unused icons via named imports (already). |
| Scope: ~30 panels | High | Phase order delivers value early (parity first, then Risk, Performance, Execution, Operations). Each phase ends deployable behind the flag. |
| Regressions in money-handling UI | Medium | Actions centralised and unit-tested; e2e on kill switch and close; no UI test places a live trade; old shell remains until cutover. |
| Audit middleware impacts latency | Low | Write after response in a background task, `db.connect` WAL, swallow errors. |
| Analytics misread on tiny samples | High | R3.5 low-sample badges and copy; no confident colouring below 20 trades. |
| Deploy restarts service during market hours | Operational | Frontend-only phases need no restart; backend phases deploy only after 15:30 IST when the owner asks. |

**Decisions made (owner may override):** server-side layouts; pinned Dockview version; own `LayoutSpec`; no router; no state library; `@tanstack/react-virtual` allowed; mobile shell separate from Dockview; legacy shell removed after cutover criteria in the plan.

---

## 16. Rollout and rollback
1. Build behind `?shell=dock` (persisted in `localStorage` `bb_shell`). Default stays `legacy`.
2. Each phase merges to main and may deploy: frontend-only deploy replaces `dist` (no restart). Backend additions (audit, layouts, analytics) deploy after market hours.
3. Cutover when: parity checklist 100 %, e2e + axe green, one full paper session on `dock` with no console errors, bundle budget met, rollback flag tested.
4. After cutover the default flips to `dock`; `?shell=legacy` remains one release; then legacy files and tests are deleted in a cleanup PR.
5. Rollback at any time: `?shell=legacy` or clearing `bb_shell`; backend additions are inert if unused.

---

## 17. Verification strategy (summary; details in plan)
- Unit: store reducers/selectors, actions (mock fetch), alert rules, layout model (presets, validate, migrate), format/time helpers, each panel (render, empty, error, stale), confirmation dialog, command palette, shortcuts table.
- Accessibility: axe on each panel and each workspace in Playwright; keyboard walkthrough script; manual screen-reader smoke list.
- E2E (Playwright, demo-mode backend): auth, stream, workspace switch, drag a tab (mouse), keyboard move (shortcut), float, pop-out (where the browser allows), save/reload/second context, reset, kill-switch confirmation flow with typed phrase, close position, audit row appears, alert on stale stream (route-blocked SSE), mobile viewport shell.
- Backend: pytest for middleware (allowlist, secrets never stored, failure swallowed), layout API (validation, snapshots cap), each analytics endpoint on a seeded SQLite fixture (golden numbers), empty database, quarantined exclusion.
- Visual: Playwright screenshots of every workspace in light/dark at 1440×900 and 390×844, stored under `docs/screenshots/institutional/`.
- Performance: Vitest/Playwright script that feeds 300 signals and 200 trades and 10 ticks/s for 60 s; assert no long tasks over 100 ms and bounded heap growth.

## 18. Hand-off notes for the executing session
Read, in order: this spec, the plan, `docs/SETUPS_SPECIFICATION.md` (only for terminology), `frontend/src/App.tsx`, `frontend/src/components/Terminal.tsx`, `Blotter.tsx`, `backend/app/api/signals.py`, `backend/app/api/dashboard.py`, `backend/app/services/performance_report.py`. Do not modify scanner, paper trader, risk, order router. Do not deploy; the owner deploys when asked (merge locally, push, deploy to the `fyers-algo` VM outside 09:15–15:30 IST).
