# Institutional Dockview Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed terminal shell with a Dockview (free MIT edition) workspace, port every existing capability into panels, and add Risk, Performance, Execution, Audit, Alerts and Operations views, without changing trading logic.

**Architecture:** A framework-light external store owns all server data (one SSE stream plus pollers) and all mutating actions; panels are thin consumers registered in one registry; `shell/dockHost.tsx` is the only file that imports Dockview; layouts are our own serialisable spec stored on the server; phones use a separate single-pane shell. The legacy terminal stays selectable behind `?shell=legacy` until cutover.

**Tech Stack:** React 18, TypeScript 5, Vite 5, Tailwind 3 (CSS variables), `dockview-react` (exact pinned version), `@tanstack/react-virtual`, `lightweight-charts` 4, Vitest + Testing Library + axe-core, Playwright; FastAPI, SQLite (WAL via `services/db.connect`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-institutional-dockview-dashboard-design.md` (read it first; requirement IDs R1.1…R8.6, S1…S8 and parity items refer to it).

## Global Constraints

- Free edition only: never install or import `dockview-enterprise`. Do not use: multi-row tabs, pinned tabs, auto-hide/dock-to-edge groups, DnD compass, smart guides, layout history, spatial keyboard navigation, keyboard docking.
- Do not modify scanner, setups, paper trader, exits, risk engine, order router, broker adapters (`backend/app/services/{scanner_*,paper_*,order_router,broker_*,setup*,strategy_engine}.py`). Backend work is additive: new files plus one middleware registration in `main.py` and router registrations.
- Pin Dockview with an exact version (no `^`/`~`). New runtime dependencies allowed: `dockview-react`, `@tanstack/react-virtual` only.
- Capability enforcement already covers all non-health `/api` routes (middleware in `backend/app/main.py`); new routers inherit it. Never log or store secrets; never store request bodies for `/api/auth/*`, `/api/live/broker/*`, `/api/live/enable`.
- Money actions: no optimistic UI; no `window.confirm`; one in-flight request per action key; result message from server `detail`.
- Times shown in IST; rupees Indian grouping, 0 dp; premiums 1–2 dp; P&L always signed; status never colour alone.
- Initial JS (gzip) ≤ 450 KB; analytics, chart, earnings and settings panels lazy-loaded.
- Breakpoint: Dockview shell at ≥ 1024 px; `MobileShell` below.
- Never deploy. Owner deploys (merge locally, push, `fyers-algo` VM) outside 09:15–15:30 IST. Backend phases need a service restart; frontend-only phases do not.
- Commit after every task. Commit footer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Commands: frontend `cd frontend && npx vitest run`, `npx tsc -p tsconfig.app.json --noEmit`, `npm run build`, `npm run test:e2e`; backend `cd backend && .venv/bin/pytest -q`.
- Work on branch `feat/dockview-shell` from `main`; one PR per phase merged to `main` (each phase must leave `main` green and the legacy shell default).

## Review Focus

1. Saved layout is corrupt, from a newer schema, or references a panel id that no longer exists → app opens the preset and raises an alert; never a blank screen (Task 3.1, 3.3).
2. Empty database or zero closed trades → every analytics endpoint returns empty arrays and zeros (no 500, no NaN/Infinity in JSON) (Task 4.4).
3. SSE delivers malformed JSON, duplicate events, or reconnect storms → store keeps the last good state and marks the slice stale/reconnecting (Task 1.3).
4. Pop-out blocked by the browser, or the pop-out window closed mid-action → visible message, panel returns to the main window, no crash (Task 3.5).
5. Kill switch returns `failed[]` (some positions not closed) or the request times out → dialog result lists the symbols / states "outcome unknown, check positions" and the store re-fetches (Task 1.5).

## File Structure

```
frontend/src/
  data/        store.ts  appStore.ts  stream.ts  pollers.ts  actions.ts  auth.ts  selection.ts  types.ts  api/
  features/    confirm/  alerts/  commands/  layouts/  audit/  shortcuts.ts
  lib/         time.ts  numbers.ts  csv.ts  useTable.ts  (existing: connectionState.ts, format helpers stay)
  panels/      registry.ts  PanelFrame.tsx  <one folder per panel id>/index.tsx
  shell/       DockApp.tsx  Chrome.tsx  StatusBar.tsx  ModeBanner.tsx  dockHost.tsx  MobileShell.tsx  WorkspaceSwitcher.tsx
  theme/       tokens.css  dockview-theme.css
  index.css    (imports theme files; legacy classes untouched)
backend/app/
  api/ui_layouts.py  api/analytics.py  api/audit.py
  core/audit_middleware.py
  services/ui_store.py  services/action_audit.py  services/analytics.py
backend/tests/  test_ui_layouts.py  test_action_audit.py  test_analytics_*.py
docs/DOCKVIEW_NOTES.md  docs/screenshots/institutional/
```
Existing components under `frontend/src/components/` are reused in place by panel wrappers; they are not moved until the cleanup task.

---

# Phase 0 — Baseline and Dockview spike (throwaway code, durable notes)

### Task 0.1: Branch and baseline measurements

**Files:** Create `docs/DOCKVIEW_NOTES.md`.

- [ ] **Step 1:** `git checkout -b feat/dockview-shell main`; run all five commands from Global Constraints; record counts (Vitest tests, Playwright specs, pytest tests) and `vite build` output sizes (raw and gzip of each chunk) in `docs/DOCKVIEW_NOTES.md` under "Baseline".
- [ ] **Step 2:** Expected: everything passes. If anything fails on a clean `main`, stop and report; do not proceed.
- [ ] **Step 3:** Commit `docs: record dockview migration baseline`.

### Task 0.2: Dockview spike and verification (decides section 15 rules)

**Files:** Create `frontend/src/spike/*` (deleted at end of task), update `docs/DOCKVIEW_NOTES.md`; Modify `frontend/package.json`.

**Interfaces — Produces:** `docs/DOCKVIEW_NOTES.md` sections with exact, copy-pasteable answers: installed version; licence file text of `dockview-react` and `dockview-core` (confirm MIT); exact API names for add panel, serialise, deserialise, layout-change event, floating, pop-out, theming CSS variables; decisions D1–D6 below.

- [ ] **Step 1:** `npm i --save-exact dockview-react@latest`; read `node_modules/dockview-react/LICENCE*`, `node_modules/dockview-core/LICENCE*`; paste verbatim into notes. If either is not MIT, stop and report to the owner.
- [ ] **Step 2:** Build `frontend/src/spike/Spike.tsx` mounted at `?spike=1` with 4 dummy panels that read a shared counter from a module-level store. Probe and record pass/fail with evidence:
  - **D1 pop-out context:** open a pop-out; does the counter keep updating there (same JS realm)? Are stylesheets present? Does it work in Chromium, Firefox, Safari? What happens when the browser blocks it?
  - **D2 serialisation:** `toJSON` → `fromJSON` round trip preserves sizes, tabs, floating, pop-out groups; what happens when JSON references an unknown component id.
  - **D3 accessibility:** run axe on the dock; list roles Dockview renders for tab strip; record keyboard behaviour (Tab, arrows, Enter); decide how to add `role="tablist"/"tab"`, `aria-selected`.
  - **D4 theming:** list the CSS variables Dockview exposes; confirm mapping to our tokens in light and dark.
  - **D5 bundle:** gzip delta of `dockview-react` + CSS.
  - **D6 jsdom:** can `DockviewReact` mount in Vitest? Record what breaks.
- [ ] **Step 3:** Write decisions: pop-out strategy (portal / `BroadcastChannel` bridge / drop pop-out per spec section 15), tab-semantics approach, test strategy, bundle delta.
- [ ] **Step 4:** `rm -rf frontend/src/spike`; revert any spike-only edits to `main.tsx`; `npm run build` passes.
- [ ] **Step 5:** Commit `docs: dockview spike findings and decisions` (package.json change included).

**Gate:** if D1 and D2 both fail, or licence is not MIT, stop and report; the rest of the plan depends on them.

---

# Phase 1 — Foundations (no visible change; legacy default)

### Task 1.1: Design tokens, density, Dockview theme

**Files:** Create `frontend/src/theme/tokens.css`, `frontend/src/theme/dockview-theme.css`; Modify `frontend/src/index.css` (import both; keep every existing rule); Modify `frontend/tailwind.config.js` (add `stale`, `modePaper`, `modeDry`, `modeLive` colours).

**Interfaces — Produces:** CSS variables `--density-row` (24px compact / 32px comfortable via `:root[data-density]`), `--density-pad`, `--focus-ring`, `--mode-paper|dry|live`, `--stale`; Dockview variables mapped using the names recorded in notes D4.

- [ ] **Step 1:** Test `frontend/src/theme/theme.test.ts`: reads both CSS files as text and asserts every variable named in a fixed list is defined for `:root` and `:root.dark`; assert contrast helper `contrast(fg,bg) >= 4.5` for `--fg`/`--panel`, `--muted`/`--panel`, `--up`/`--panel`, `--down`/`--panel`, `--warn`/`--panel`, `--accent`/`--panel`, `--mode-live` text on its fill, in both themes (write `lib/contrast.ts` with `contrast(a: string, b: string): number`).
- [ ] **Step 2:** Run `npx vitest run src/theme` → FAIL.
- [ ] **Step 3:** Add the CSS; adjust any failing token values (dark and light) minimally until the contrast test passes; existing visual rules unchanged.
- [ ] **Step 4:** Run vitest for theme + `npm run build` → PASS.
- [ ] **Step 5:** Commit `feat(theme): density, mode and dockview tokens`.

### Task 1.2: Store core

**Files:** Create `frontend/src/data/store.ts`, `frontend/src/data/store.test.ts`.

**Interfaces — Produces:**
```ts
export interface Store<T> { getState(): T; setState(patch: Partial<T> | ((s: T) => Partial<T>)): void; subscribe(fn: () => void): () => void }
export function createStore<T extends object>(initial: T): Store<T>;
export function useStore<T, S>(store: Store<T>, selector: (s: T) => S, isEqual?: (a: S, b: S) => boolean): S; // useSyncExternalStore based
export function shallowEqual<T>(a: T, b: T): boolean;
export function keepIdentity<T>(prev: T, next: T): T; // returns prev when deep-equal, else next with unchanged subtrees reused
```
- [ ] **Step 1:** Tests: `setState` notifies once per call; unsubscribe stops notifications; selector re-renders only when selected value changes (render-count assertion with a test component); `keepIdentity` returns the same reference for equal input and reuses unchanged child references; `shallowEqual` basics.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat(data): external store with selectors`.

### Task 1.3: App store, SSE stream and slices

**Files:** Create `frontend/src/data/appStore.ts`, `frontend/src/data/stream.ts`, `frontend/src/data/types.ts`, tests `appStore.test.ts`, `stream.test.ts`.

**Interfaces — Produces:**
```ts
export type SliceName = 'stream'|'scanner'|'portfolio'|'closedTrades'|'watch'|'trades'|'live'|'health'|'analytics';
export interface SliceMeta { asOf: number|null; status: 'idle'|'loading'|'ready'|'stale'|'error'; error?: string }
export interface AppState { scanner: ScannerState; closedTrades: PaperPosition[]; watch: DashboardWatch|null; trades: DashboardTrade[]; stream: StreamStatus; meta: Record<SliceName, SliceMeta>; ui: {density:'compact'|'comfortable'; workspace:string}; selection: Selection; /* plus slices added in later tasks */ }
export const appStore: Store<AppState>;
export function useApp<S>(selector: (s: AppState) => S, isEqual?): S;
export function useSliceMeta(name: SliceName): SliceMeta & { stale: boolean; ageSec: number };
export function setSlice<K extends SliceName>(name: K, patch: Partial<SliceMeta>): void;
// stream.ts
export function startStream(opts?: { url?: string; staleAfterMs?: number; reconnectMs?: number; flushMs?: number }): () => void; // returns stop()
```
Behaviour (from current `App.tsx`): default `message` events carry a full `ScannerState` snapshot; named `tick` events update `scanner.radar[sym].close` for non-option ticks; named `portfolio` events carry `{paper_portfolio}`; stale after 15 s without a message; `onerror` closes, marks `reconnecting`, retries after 3 s; ticks are buffered and flushed to state at most every 250 ms; snapshot signals keep previous identity when deep-equal (`keepIdentity`); initial `GET /api/signals` snapshot is fetched first; a 401 sets `ui.needsCapability = true`; closed trades refetched from `/api/paper/portfolio` when `paper_portfolio.closed_trades_count` changes or `active_mode` changes. Use a fake `EventSource` in tests.

- [ ] **Step 1:** Tests in `stream.test.ts`: (a) snapshot message populates `scanner` and sets `meta.scanner.status='ready'` and `stream.state='live'`; (b) `tick` events are coalesced (50 ticks in 100 ms → ≤ 1 flush, last value wins); (c) option ticks (`is_option`) ignored; (d) **malformed JSON message** leaves previous state untouched and increments `meta.stream.error`, no throw; (e) **duplicate identical snapshots** keep object identity (`scanner.signals === previous`); (f) no message for 16 s (fake timers) → `stream.state='stale'`, `useSliceMeta('stream').stale===true`; (g) `onerror` → `reconnecting`, new `EventSource` after 3 s, repeated errors do not create more than one live source (storm test: 20 errors in 1 s → 1 timer); (h) closed-trades refetch only when count changes; (i) `stop()` closes the source and clears timers.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `stream.ts` and `appStore.ts`; port logic from `frontend/src/App.tsx:128-300` (do not edit `App.tsx`). **Step 4:** Run → PASS. **Step 5:** Commit `feat(data): app store and sse stream`.

### Task 1.4: Pollers

**Files:** Create `frontend/src/data/pollers.ts`, `pollers.test.ts`.

**Interfaces — Produces:** `startPollers(opts?: { intervals?: Partial<Record<PollKey, number>> }): () => void` where `PollKey = 'trades'|'watch'|'live'|'readiness'|'rateLimit'|'recorder'|'errors'|'analytics'`. Defaults: trades 30 s, watch 30 s, live 15 s (only while `live.status.mode !== 'off'`, otherwise once per 60 s), readiness 60 s, rateLimit 60 s, recorder 60 s, errors 60 s, analytics 120 s and on closed-count change. Each poller sets `meta[slice]` `{asOf,status,error}`; on failure keeps last data with `status='error'`. Pause while `document.hidden`; on `visibilitychange` visible → immediate fetch.

- [ ] **Step 1:** Tests: fetch called at interval with fake timers; failure keeps previous data and sets `error`; hidden document pauses (no calls) and resumes with immediate call; `live` poll interval switches by mode; `stop()` clears all timers; one failing poller does not stop others.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(data): pollers with visibility pause`.

### Task 1.5: Actions, auth and confirmation

**Files:** Create `frontend/src/data/actions.ts`, `frontend/src/data/auth.ts`, `frontend/src/features/confirm/ConfirmProvider.tsx`, tests for each.

**Interfaces — Produces:**
```ts
export interface ActionResult { ok: boolean; message: string; detail?: unknown }
export const actions: {
  scanNow(): Promise<ActionResult>;
  paperBuy(signal: Signal): Promise<ActionResult>;           // lots from portfolio.default_lots, fallback 2
  closePosition(id: string): Promise<ActionResult>;
  toggleAutoTrade(enabled: boolean): Promise<ActionResult>;  // verifies by refetching /api/paper/portfolio
  setSetupMode(setup: string, mode: SetupMode): Promise<ActionResult>;
  killSwitch(engage: boolean): Promise<ActionResult & { failed: string[] }>;
  resetPortfolio(): Promise<ActionResult>;
  updateSettings(changes: Record<string, unknown>): Promise<ActionResult>;
  resetSetting(key: string): Promise<ActionResult>;
  live: { setMode; arm; enable; resume; reconcile; retryExit; brokerLogin; brokerLogout };
  earnings: { syncCalendar; saveCalendarRow; deleteCalendarRow; runCycle; squareOff; importIv };
  journal: { save(id: string, body: unknown): Promise<ActionResult> };
};
export function useInFlight(key: string): boolean;
// confirm
export interface ConfirmOptions { title: string; body: React.ReactNode; confirmLabel: string; danger?: boolean; phrase?: string }
export function useConfirm(): (o: ConfirmOptions) => Promise<boolean>;
export const ConfirmProvider: React.FC<{children: React.ReactNode}>;
```
Behaviour: each action keeps an in-flight flag keyed by name (second call while in flight returns `{ok:false,message:'Already running'}`); 401 sets `ui.needsCapability`; server `detail` string becomes `message`; after success refetch the owning slice (`/api/paper/portfolio` etc.); network error or timeout (10 s) → `{ok:false,message:'No answer from the server. Outcome unknown; check positions.'}` and triggers refetch; each action raises an info/critical alert through `alerts.push` (Task 5.9 supplies it; until then a no-op hook `data/alertsHook.ts`).
Dialog: `role="dialog"` `aria-modal`, focus trap, `Esc` cancels, initial focus on Cancel when `danger`, confirm button disabled until `phrase` typed exactly (case-sensitive).

- [ ] **Step 1:** Tests: success path per action (mock `apiFetch`); 401 path; server `detail` surfaced; double-submit guard; `killSwitch(true)` with `{failed:['NIFTY 24500 CE']}` → `ok:true`, `failed` array, message contains the symbol; **timeout** → unknown-outcome message and refetch called; `toggleAutoTrade` fails if refetch shows state not changed; confirm dialog: Esc cancels (resolves false), phrase gating, focus trap, axe clean.
- [ ] **Steps 2–5:** fail → implement (port bodies from `App.tsx:178-420`) → pass → commit `feat(data): central actions and accessible confirmation`.

### Task 1.6: Selection slice

**Files:** Create `frontend/src/data/selection.ts`, test.

**Interfaces — Produces:** `type Selection = {kind:'signal'|'position'|'candidate'|'trade'; id:string}|null`; `select(sel: Selection)`, `useSelection(opts?: {pinned?: boolean})` returning the selection or the pinned copy; `resolveSelection(state): {signal?, position?, candidate?, trade?}` (lookup by id so refreshed data never leaves stale copies); default selection rule from `Terminal.tsx` (first open position, else newest signal) available as `defaultSelection(state)`.

- [ ] **Steps 1–5:** tests: select/clear; resolve by id after snapshot refresh; pinned panel ignores changes; default rule; commit `feat(data): linked selection`.

### Task 1.7: Lib: time, numbers, CSV, table hook

**Files:** Create `frontend/src/lib/{time.ts,numbers.ts,csv.ts,useTable.ts}` + tests.

**Interfaces — Produces:**
```ts
export const toIst(d: string|number|Date): Date-like parts; formatIst(d, 'time'|'date'|'datetime'): string; ageSeconds(asOf: number, now?: number): number; marketSession(now?: Date): 'pre-open'|'open'|'closed'|'weekend'; // 09:15–15:30 IST Mon–Fri
export const inr(n: number, opts?: {sign?: boolean}): string; pct(n: number, dp?: number): string; points(n: number, dp?: number): string; signedClass(n: number): 'desk-up'|'desk-down'|'';
export function toCsv(rows: Record<string, unknown>[], columns: {key: string; label: string}[]): string; // RFC 4180 quoting, formula-injection guard (prefix cells starting with = + - @ with ')
export function downloadCsv(name: string, csv: string): void;
export function useTable<T>(rows: T[], opts: { columns: ColumnDef<T>[]; storageKey: string; initialSort?: {key: string; dir: 'asc'|'desc'}; pageWindow?: number }): { visibleRows: T[]; sort; setSort; columns; toggleColumn; exportCsv(): void; activeIndex; onKeyDown };
```
- [ ] **Step 1:** Tests: `formatIst` for a UTC string → IST wall time; `marketSession` at 09:14 / 09:15 / 15:30 / 15:31 / Saturday; `inr(1234567)` → `₹12,34,567`; `inr(-5,{sign:true})`; CSV quoting of commas/quotes/newlines and `=SUM(A1)` prefixed; `useTable` sort toggle, column hide persisted in `localStorage` (wrapped in try/catch; works when storage throws), Arrow/Home/End/Enter row navigation, windowing flag above 150 rows.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(lib): time, numbers, csv, table hook`.

### Task 1.8: PanelFrame and registry skeleton

**Files:** Create `frontend/src/panels/PanelFrame.tsx`, `frontend/src/panels/registry.ts`, tests.

**Interfaces — Produces:** `PanelDefinition`, `PanelProps = { id: string; params: Record<string, unknown>; setParams(p: Record<string, unknown>): void; api?: DockPanelApi }` per spec 5.4; `PANELS: PanelDefinition[]` (empty at this task; each later task appends), `getPanel(id)`, `PanelFrame: React.FC<{ title: string; sources: SliceName[]; actions?: React.ReactNode; exportCsv?: () => void; children }>` rendering a title row with as-of time (`HH:MM:SS IST`), `Stale 47 s` badge with icon when any source is stale, error strip with Retry when `status==='error'`, panel menu button (items provided by shell through context `PanelMenuContext`).

- [ ] **Steps 1–5:** tests: shows as-of; shows stale badge text + icon (not colour only) after threshold; error strip keeps children visible; `data-frozen` set on root when stream stale; axe clean; registry rejects duplicate ids (throws in dev). Commit `feat(panels): frame and registry`.

### Task 1.9: Shell flag, Chrome, status bar, mode banner

**Files:** Create `frontend/src/shell/{DockApp.tsx,Chrome.tsx,StatusBar.tsx,ModeBanner.tsx}`; Modify `frontend/src/main.tsx` (choose shell), tests.

**Interfaces — Produces:** `chooseShell(search: string, storage): 'legacy'|'dock'` (`?shell=` wins, persisted to `localStorage.bb_shell`, default `'legacy'`); `<DockApp />` starts `startStream()` and `startPollers()` on mount and stops on unmount, wraps `ThemeProvider`, `DhanAuthProvider`, `ConfirmProvider`; `Chrome` contains brand, workspace switcher slot, `RiskControls`-equivalent (day P&L vs cap meter, open count, **kill switch button always rendered** using `actions.killSwitch` through `useConfirm` with phrase `KILL`), `ConnectionStatus`, IST market-session clock, scan now, command-palette trigger slot, density toggle, theme toggle, Dhan connect (reuse `Header` dialogs by extracting them into `components/DhanConnectDialog.tsx` without changing `Header` behaviour), dashboard-key dialog; `ModeBanner` per R1.3 from `live` slice and portfolio; `StatusBar` shows per-source freshness (text + icon), scan cycle and last scan, build id (`import.meta.env.VITE_BUILD_ID ?? 'dev'`).

- [ ] **Step 1:** Tests: `chooseShell` precedence and storage failure; Chrome always renders kill switch even with empty store; kill-switch click opens confirm, typing `KILL` enables the confirm button, confirm calls `actions.killSwitch(true)`; shortcut `Ctrl+Shift+K` opens the dialog but never calls the action; ModeBanner texts `LIVE ARMED` / `LIVE DRY RUN` and hidden for paper (paper pill remains); StatusBar marks stale source with text; axe clean.
- [ ] **Step 2–5:** fail → implement (DockApp renders `<main>` placeholder "Workspace loading" until Task 3.3) → pass; manual: `npm run dev`, open `/?shell=dock`, confirm Chrome and live data appear, `/?shell=legacy` unchanged → commit `feat(shell): flag, chrome, status bar, mode banner`.

---

# Phase 2 — Panel parity (each panel wraps existing components)

General rule for tasks 2.1–2.9: create `frontend/src/panels/<id>/index.tsx` exporting a default component of type `PanelProps`, read data with `useApp` selectors, call `actions.*` (never `apiFetch` for mutations), wrap in `PanelFrame`, append a definition to `PANELS` (lazy for earnings, settings, live, telemetry, journal, chart). Each panel gets `index.test.tsx` covering: renders with fixture state, empty state, stale state badge, error state, and its actions calling `actions.*` with the right arguments; plus axe. Existing component tests stay untouched.

### Task 2.1: `signals` panel
Wraps `SignalsPane` + `SignalTable`. Params persisted: `{ filters: WatchFilters; mode: 'signals'|'watching'; sortBy; bookFilter; statusFilter }`. Filtering moves from `App.tsx:filteredSignals` into `data/selectors.ts: selectFilteredSignals(state, filters)`. **Parity item:** add `'3m'` to the timeframe options (Codex finding) and test that a 3m signal is visible when `3m` is chosen. Selecting a row calls `select({kind:'signal', id})`.
### Task 2.2: `focus` panel
Wraps `FocusPane`/`SignalDetails`/`PositionChartModal inline`/`WatchCandidateDetail`; subject from `useSelection({pinned})`; params `{pinned: boolean; subject?: Selection}`; header button "Pin"/"Unpin"; actions `paperBuy`, `closePosition` (through `useConfirm` showing symbol, P&L, `est_net_pnl`), "Open trade" selects trade and opens `trades` panel (command `openPanel('trades')` from Task 3.4 via context `PanelCommands`).
### Task 2.3: `positions` and `positions-table` panels
`positions` wraps `PositionsPane` (+ `TodaySummary`); `positions-table` wraps Blotter `PositionsTable` using `useTable` (column chooser, sort, CSV `positions_<date>.csv`, windowing). Auto-enter toggle via `actions.toggleAutoTrade`. Close uses `useConfirm`.
### Task 2.4: `chart` panel
Wraps `PositionChartModal` inline for open positions and `TradeChart` + `ReplayControls` for closed trades; follows selection; text summary and "Show data table" toggle (R accessibility); lazy-loads `lightweight-charts`; disposes chart on unmount (test with spy).
### Task 2.5: `market` panel
Expanded `IndexHeroRadar`; click selects the index; also export `MarketStrip` for Chrome use (reused in `StatusBar`? No: strip sits under Chrome on desktop; test that it renders every index in `radar`).
### Task 2.6: `trades`, `session`, `journal` panels
`trades` wraps `TradesScreen` (initial trade from selection `kind:'trade'`), `session` wraps `SessionScreen` (`loadSession` from `api/dashboard`), `journal` wraps `JournalPanel`; save notes through `actions.journal.save`. `ReceiptModal` opened via existing component. The `journal` panel also has an "End-of-day report" button (R6.3) that downloads `/api/journal/export.csv?start=<day>&end=<day>` and opens `/api/journal/summary.html` for the chosen day; test: button builds both URLs with the IST day.
### Task 2.7: `earnings` panel
Wraps `EarningsPanel` unchanged; its internal `apiFetch` mutations are routed through `actions.earnings.*` (replace the local `call()` helper to use actions so they are audited and confirmed with `useConfirm` for square-off).
### Task 2.8: `settings`, `live`, `controls`, `telemetry`, `costs`, `setup-stats` panels
`settings` wraps `SettingsPanel`; changing a setting whose group is risk-related (groups containing `Risk`, `Loss`, `Quality`; confirm group names in `runtime_settings.py`) shows old → new in `useConfirm`. `live` wraps `LiveRoutingPanel` (all calls via `actions.live.*`). `controls` merges `ControlScreen` with the setup-mode matrix from `PaperPortfolioView` and Reset portfolio (confirm with the server text). `telemetry` wraps `TelemetryPanel`; `costs` wraps `CostPanel`; `setup-stats` wraps `SetupStatsPanel`.
### Task 2.9: Parity test and registry completeness
Create `frontend/src/panels/parity.test.ts`: a table of the 17 parity items in spec 6.3, each mapped to a panel id and a testable selector; assert every referenced id exists in `PANELS`; assert every `PanelDefinition` has title, category, sources.

For each of 2.1–2.9: **Step 1** write the panel tests (names `<id> renders rows`, `<id> shows empty state`, `<id> marks stale`, `<id> action calls actions.<name> with …`); **Step 2** run → FAIL; **Step 3** implement panel + register; **Step 4** run vitest for the folder and `npx tsc -p tsconfig.app.json --noEmit` → PASS; **Step 5** commit `feat(panels): <ids>`.

---

# Phase 3 — Dock host, layouts, keyboard parity, mobile

### Task 3.1: Layout model (pure)

**Files:** Create `frontend/src/features/layouts/{layoutModel.ts,presets.ts}`, test `layoutModel.test.ts`.

**Interfaces — Produces:**
```ts
export const LAYOUT_SCHEMA_VERSION = 1;
export type LayoutNode = { type:'split'; direction:'row'|'column'; sizes:number[]; children:LayoutNode[] } | { type:'group'; panels:{id:PanelId; params?:Record<string,unknown>}[]; active?:PanelId };
export interface LayoutSpec { schema_version:number; name:string; based_on?:string; preset_version?:number; root:LayoutNode; floating?:{panelId:PanelId; x:number;y:number;w:number;h:number}[]; popouts?:PanelId[] }
export const PRESETS: Record<WorkspaceName, LayoutSpec>;      // Trading, Risk, Performance, Execution, Review, Operations, Earnings — shapes exactly as spec section 7
export function validateLayout(raw: unknown, registry: PanelDefinition[]): { ok: true; layout: LayoutSpec; dropped: string[] } | { ok: false; reason: string };
export function migrateLayout(raw: unknown): unknown;                 // append-only migrations by schema_version
export function toDockviewJson(spec: LayoutSpec): unknown;            // shape confirmed in notes D2
export function fromDockviewJson(json: unknown, based?: LayoutSpec): LayoutSpec;
export function ensureSingletons(spec: LayoutSpec, registry): LayoutSpec;
```
- [ ] **Step 1:** Tests: every preset validates against the registry (fails if a preset references an unregistered panel — this test grows as panels register); **corrupt JSON string, `null`, array, wrong types → `{ok:false}`**; layout from `schema_version: 99` → `{ok:false, reason:'newer schema'}`; unknown panel id is dropped and listed in `dropped`, remaining layout valid; a group left empty after dropping is removed and sizes renormalised to sum 1; duplicate singleton panel de-duplicated; `fromDockviewJson(toDockviewJson(x))` round-trips each preset; migration fixture v0→v1.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(layouts): pure layout model and presets`.

### Task 3.2: Layout persistence client

**Files:** Create `frontend/src/features/layouts/layoutApi.ts`, test.

**Interfaces — Produces:** `loadLayouts(): Promise<Record<string, LayoutSpec>>` (server first; fall back to `localStorage.bb_layouts`; both wrapped in try/catch), `saveLayout(spec): void` (debounced 800 ms, max one write per second, writes cache first), `deleteLayout(name)`, `listSnapshots(name)`, `restoreSnapshot(name,id)`, `exportLayout(name): string`, `importLayout(json: string): LayoutSpec` (uses `validateLayout`). Conflict rule: newest `updated_at` wins.
- [ ] **Steps 1–5:** tests with fake timers and mocked `apiFetch`: debounce collapses 10 changes into 1 PUT; server down → cache used and no throw; import of invalid JSON → error result, nothing saved; storage throwing does not break load. Commit `feat(layouts): persistence client`.

### Task 3.3: DockHost

**Files:** Create `frontend/src/shell/{dockHost.tsx,WorkspaceSwitcher.tsx}`; Modify `DockApp.tsx`.

**Interfaces — Consumes:** `PANELS`, `LayoutSpec`, `toDockviewJson`, `fromDockviewJson`, `saveLayout`. **Produces:** `DockHost: React.FC<{ layout: LayoutSpec; onLayoutChange(spec: LayoutSpec): void; commandsRef: React.MutableRefObject<DockCommands> }>`; `DockCommands = { openPanel(id, opts?); focusGroup(dir:1|-1); nextTab(); prevTab(); movePanelToGroup(dir:1|-1); split(dir:'right'|'down'); float(); dock(); popOut(); maximise(); close(); resetWorkspace() }`. Only this file imports `dockview-react`. Registry-driven `components`; our header menu component implementing `PanelMenuContext`; tab semantics from decision D3; watermark with "Empty group: open a panel from the command palette (Ctrl+K)".
**Startup rule:** load layouts → `validateLayout` → on `{ok:false}` use the preset and `alerts.push({severity:'warning', message:'Saved layout was invalid; default restored'})`.
- [ ] **Step 1:** Playwright spec `e2e/specs/dock_layout.spec.ts` (against `/?shell=dock&workspace=Trading`): default Trading layout shows `signals`, `focus`, `positions-table`, `positions` panels; switching to Risk shows `risk`; a **corrupted layout in `localStorage.bb_layouts` and a 500 from `/api/ui/layouts` still opens Trading** and shows the warning alert; dragging the Signals tab by mouse into the Positions group (via `page.mouse`) changes the layout and survives reload.
- [ ] **Step 2:** Run `npm run test:e2e -- dock_layout` → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat(shell): dock host and workspace switcher`.

### Task 3.4: Dock keyboard parity and shortcuts

**Files:** Create `frontend/src/features/shortcuts.ts`, `frontend/src/features/commands/{commands.ts,ShortcutHelp.tsx}`, tests.

**Interfaces — Produces:** `SHORTCUTS: {id; keys; description; when?}[]` containing exactly the spec 11.3 list plus `Ctrl+K` (palette), `Ctrl+Shift+K` (kill-switch confirmation), `?` (help); `matchShortcut(e: KeyboardEvent): string|null` (ignores events from inputs/textareas/contenteditable); `hasConflicts(): string[]` (must be empty).
- [ ] **Step 1:** Tests: no duplicate key combos; `matchShortcut` ignores typing in `<input>`; every dock command in `DockCommands` has a shortcut or palette entry (table-driven); help dialog lists all with axe clean.
- [ ] **Step 2–5:** fail → implement and wire to `commandsRef` → pass; Playwright `dock_keyboard.spec.ts`: using only the keyboard move a panel to the next group, maximise, restore, float, dock, close, reopen from palette → commit `feat(shell): keyboard parity for dock operations`.

### Task 3.5: Floating and pop-out

**Files:** Modify `dockHost.tsx`, `DockApp.tsx`; add `e2e/specs/dock_popout.spec.ts`.
Behaviour per notes D1 decision. `popOut()` must be invoked from a user gesture; if `window.open` is blocked or fails, show `alerts.push` + toast "Pop-out was blocked by the browser. Allow pop-ups for this site." and leave the panel docked. Closing the pop-out window returns its panel to the main dock (not lost). Persist popout panel ids in the layout; on reload, pop-outs are restored as **floating** panels (browsers block automatic windows) with a one-click "Re-open pop-outs" banner.
- [ ] **Step 1:** Playwright: stub `window.open` to return `null` → message shown, panel still docked; open real pop-out (Chromium, if D1 passed) → live value updates there; close popup via `popup.close()` → panel returns to main dock; reload → panel floats and banner appears.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(shell): floating panels and pop-out with fallbacks`.

### Task 3.6: Workspace management UI

**Files:** Modify `WorkspaceSwitcher.tsx`; Create `features/layouts/LayoutMenu.tsx`.
Menu: switch workspace, Save layout as…, Rename, Delete (custom only; confirm), Reset workspace (confirm), Revert to snapshot…, Export, Import, "Update to new default" when `preset_version` is older. `?workspace=` honoured; last workspace remembered in `ui.workspace` (localStorage cache).
- [ ] **Steps 1–5:** unit tests for menu logic with mocked `layoutApi`; Playwright: save custom layout, reload, appears; reset restores preset; import invalid JSON shows error. Commit `feat(layouts): workspace management`.

### Task 3.7: MobileShell

**Files:** Create `frontend/src/shell/MobileShell.tsx`, test; Modify `DockApp.tsx` (choose by `matchMedia('(min-width: 1024px)')`, listen for change).
Bottom nav Signals / Detail / Positions / Tables / More; "More" lists every registered panel by category; chosen panel fills the screen with a back button; Chrome shows mode banner, kill switch (compact), connection pill, Tools sheet. Selection from Signals/Positions switches to Detail (current behaviour in `Terminal.tsx`).
- [ ] **Steps 1–5:** unit tests (nav switching, selection → Detail, More lists all panels, kill switch present); Playwright at 390×844: no horizontal scroll, kill switch visible, axe clean. Commit `feat(shell): mobile shell`.

---

# Phase 4 — Backend (additive; deploy after 15:30 IST)

### Task 4.1: Layout store and API

**Files:** Create `backend/app/services/ui_store.py`, `backend/app/api/ui_layouts.py`; Modify `backend/app/main.py` (register router with `settings.API_PREFIX`); Test `backend/tests/test_ui_layouts.py`.

**Interfaces — Produces:** `class UiStore: __init__(self, db_path: str)`, `list() -> list[dict]`, `put(name: str, body: dict, schema_version: int) -> dict` (inserts snapshot, keeps last 20 per name), `delete(name)`, `snapshots(name) -> list[dict]`, `restore(name, snapshot_id) -> dict`. Routes per spec 8.3. Validation: body JSON ≤ 256 KB → else 413; `schema_version` int → else 422; delete only allowed for `custom:*` names → else 403; names ≤ 80 chars, restricted to `[A-Za-z0-9 :_.-]`.
- [ ] **Step 1:** Tests (use a tmp db and `TestClient`; follow `backend/tests/conftest.py`): put/get round trip; 21st snapshot evicts the oldest; oversize → 413; bad version → 422; deleting `workspace:Trading` → 403; invalid name chars → 422; restore returns body and writes a new snapshot; **unauthorised request → 401** like other routes.
- [ ] **Steps 2–5:** fail → implement (tables per spec 8.1, `db.connect`) → pass → commit `feat(api): server-side layout store`.

### Task 4.2: Action audit service and middleware

**Files:** Create `backend/app/services/action_audit.py`, `backend/app/core/audit_middleware.py`, `backend/app/api/audit.py`; Modify `main.py`; Test `backend/tests/test_action_audit.py`.

**Interfaces — Produces:** `ACTION_MAP: list[tuple[str, re.Pattern, str]]` mapping `(METHOD, route regex) → action verb` for every existing mutating route (list them from section 2.4 of the spec: `paper.trade`, `paper.close`, `paper.settings`, `paper.reset`, `kill_switch.engage`, `kill_switch.release`, `signals.scan_now`, `settings.update`, `settings.reset`, `live.mode`, `live.arm`, `live.enable`, `live.resume`, `live.reconcile`, `live.retry_exit`, `live.broker_login`, `live.broker_logout`, `earnings.*`, `journal.save`, `auth.*`, `telemetry.purge`, `ui.layout.*`); `record(method, route, action, target, outcome, status, detail, client)`; `list_actions(limit, since, action, outcome) -> list[dict]`; `AuditMiddleware(app)` records after the response; unknown mutating routes → `unknown.<route>`; `GET /api/audit/actions`.
- [ ] **Step 1:** Tests: closing a position writes `paper.close` with target = id and outcome `ok`; a 4xx writes `outcome='error'` and the `detail` message; **bodies of `/api/auth/*`, `/api/live/broker/*`, `/api/live/enable` never stored** (assert row text does not contain a sentinel secret posted in the body); a failing DB write does not change the response status; unknown mutating route recorded as `unknown.*`; GET routes are not recorded; unauthenticated 401 attempts are recorded as `outcome='denied'`; `list_actions` filters and limit; layout `PUT` recorded as `ui.layout.save`.
- [ ] **Steps 2–5:** fail → implement (write after response via background task; swallow and log errors) → pass → run full pytest → commit `feat(audit): action audit log and middleware`.

### Task 4.3: Analytics service — shared helpers and equity

**Files:** Create `backend/app/services/analytics.py`, test `backend/tests/test_analytics_equity.py`.

**Interfaces — Produces:** `parse_range(from_: str|None, to: str|None) -> tuple[date|None, date|None]` (IST dates, inclusive); `filter_trades(trades, *, rng, book, setup, side) -> tuple[list, int]` (excludes `quarantine_reason`, returns excluded count); `equity_report(trades) -> dict` shaped per spec 8.4 (`points[{t,equity,day_pnl,drawdown}]`, `summary{net,max_drawdown,current_drawdown,longest_drawdown_days,drawdowns[top5 {start,trough,end,depth}]}`, `generated_at`, `excluded`). Outcome per trade uses `performance_report._outcome` (import, do not duplicate). JSON must never contain NaN/Infinity (helper `clean(x)`).
- [ ] **Step 1:** Tests with `types.SimpleNamespace` trades: golden equity for 5 trades with a known drawdown (assert numbers); empty list → `points==[]`, zeros, no NaN; all-winners → `max_drawdown==0`; ongoing drawdown has `end=None`; range filter inclusive of both IST dates and handles trades near midnight UTC; quarantined trades excluded and counted.
- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(analytics): equity and drawdown`.

### Task 4.4: Analytics — attribution, distribution, execution, risk

**Files:** Modify `analytics.py`; Create `backend/app/api/analytics.py`; Modify `main.py`; tests `test_analytics_attribution.py`, `test_analytics_distribution.py`, `test_analytics_execution.py`, `test_analytics_risk.py`, `test_analytics_api.py`.

**Interfaces — Produces:** `attribution_report(trades, excursions, group: str) -> dict` (group ∈ setup, symbol, side, hour, weekday, exit_reason; each bucket = `performance_report._bucket` fields + `cost_drag_pct` = (charges+slippage)/|gross| ×100 or `None` when gross is 0, + `low_sample: trades < 20`); `distribution_report(trades, excursions, bins) -> dict` (`pnl`, `r`, `hold_minutes` bins `{lo,hi,count}`, `mfe_mae`, `medians{p10,p50,p90}`); `execution_report(trades) -> dict` per spec 8.4 including `not_recorded` (list of fields absent on all trades); `risk_snapshot(positions, settings) -> dict` (rupee risk = `quantity × (option_entry − option_sl)` floored at 0; `max_open` and its settings key read from runtime settings — find the key in `runtime_settings.py`, do not hardcode a guess; pool via the same `pool_of` helper used by risk code: import it, do not reimplement). Routes `GET /api/analytics/{equity,attribution,distribution,execution,risk}` using `_resolve_view` and `paper_trader.get_portfolio(view)` like `telemetry.performance`; query params `from`, `to`, `book`, `setup`, `side`, `group`, `bins`.
- [ ] **Step 1:** Tests: each report golden-number test with a 6-trade fixture; **empty input for every report returns empty collections and zeros, JSON-serialisable with `allow_nan=False`**; bucket `low_sample` flag at 19 vs 20 trades; zero-gross trade gives `cost_drag_pct=None`; hour bucket for entry at 09:15 IST; weekday buckets use IST; execution `not_recorded` lists `entry_spread_pct` when no trade has it; risk snapshot totals equal sum of rows and ignores closed positions; API: 401 without capability, 422 for bad `group`, 200 with data, response ≤ 1 s for 5,000 synthetic trades.
- [ ] **Steps 2–5:** fail → implement → pass → full pytest → commit `feat(analytics): attribution, distribution, execution, risk endpoints`.

### Task 4.5: Backend docs and deploy note

**Files:** Modify `docs/SETUPS_SPECIFICATION.md`? **No.** Create `docs/DASHBOARD_API_ADDITIONS.md` listing new routes, tables and the audit allowlist; add one paragraph to `deploy/vm/README.md` ("new tables are created on first start; no migration step").
- [ ] **Step 1:** Write docs. **Step 2:** `.venv/bin/pytest -q` passes. **Step 3:** Commit `docs: dashboard api additions`.

---

# Phase 5 — New panels (spec section 6.2)

General rule (as Phase 2). Data hooks live in `frontend/src/data/hooks/*.ts` calling `apiFetch` GETs and writing slice `analytics` or local state with `meta`; every chart has a text summary and a "Show data table" toggle; every number follows the format rules; low-sample (< 20 trades) shows the badge and neutral colour.

### Task 5.1: `risk` panel
Data: `analytics/risk` + `portfolio.risk` + settings. Renders: day P&L vs cap meter (text value + `role="meter"` with `aria-valuenow/min/max`; "Loss cap off" when `daily_loss_limit===0`), entries state Allowed/Blocked with ordered reasons (kill switch, loss cap, capped pools, auto-enter off, max open reached, market closed via `marketSession`, stream stale), open-position risk table (columns: instrument, setup, pool, qty, entry, stop, risk ₹, distance %, T1), totals row, open count vs max with the setting key. Tests: each blocked reason renders; Allowed state; empty positions text; stale state; meter attributes.
### Task 5.2: `exposure` panel
Four tables (underlying, side, pool, setup) from `analytics/risk`; concentration banner at ≥ threshold (param `concentrationPct`, default 50, validated 10–100); bars are `desk-bar` with text values. Tests: banner appears at 50 % boundary (49 vs 50), param validation, empty state.
### Task 5.3: `perf-summary` panel
Range selector (Today, 5D, 20D, All, Custom) and book selector stored in panel params; KPI row from `analytics/attribution?group=setup` totals and `analytics/equity` summary; low-sample note. Tests: range → correct `from`/`to` query strings (IST), custom range validation (from ≤ to), low-sample note under 20 trades.
### Task 5.4: `equity` panel (lazy)
`lightweight-charts` equity line + drawdown area; hover readout; deepest-five drawdowns table; data-table toggle; disposes chart on unmount. Tests: renders table from fixture, chart disposed, empty state "No closed trades in this range".
### Task 5.5: `attribution` panel
Group-by selector, sortable table with R3.2 metrics, inline bars, low-sample badge, row click sets selection `filter` (adds `selection.filter?: {group:string; key:string}` to the store) that `trades` and `perf-summary` honour. Tests: group switch refetches with `group=`, sort, filter propagates, CSV export content.
### Task 5.6: `distributions` panel
SVG histograms (pnl, R, hold time) + MFE/MAE scatter, bin-size control (validated 1–50 bins), summary sentence (median, p10, p90) as text. Tests: bin count honoured, summary text, empty state, no NaN rendered.
### Task 5.7: `execution` panel (lazy)
Slippage by setup/hour bars, entry vs exit histograms, spread vs slippage scatter, liquidity quartile table, charges stacked bar + table, cost drag per setup; `not_recorded` fields rendered as "Not recorded: …" and the dependent chart hidden. Tests: not-recorded message, charges table totals equal breakdown sums, empty state.
### Task 5.8: `orders`, `audit`, `readiness`, `recorder`, `universe` panels
`orders`: table over `/api/live/orders` (status colouring + text), CSV. `audit`: unified table merging `/api/audit/actions`, `/api/settings/audit`, `/api/live/audit`, filters (source, outcome, text, date), expandable row (old → new for settings), CSV, **no delete controls**. `readiness`, `recorder`, `universe`: read-only views with as-of and stale handling. Tests: merge order newest first across sources; one failing source shows an inline error strip but other sources still list; CSV excludes nothing and escapes formulas.
### Task 5.9: Alerts engine and `alerts` panel
**Files:** `frontend/src/features/alerts/{rules.ts,alertsStore.ts}`, `panels/alerts/index.tsx`.
**Interfaces — Produces:** `type Alert = { id: string; ts: number; severity:'info'|'warning'|'critical'; source: string; message: string; acked: boolean }`; `evaluateRules(prev: AppState, next: AppState): Alert[]` (rules listed in spec 11.1, each a pure function exported separately); `alerts.push(a)`; `alerts.ack(id)`, `ackAll()`, `useAlerts()`; keep last 200; persist acked ids in `localStorage` (try/catch); critical alerts call `LiveAnnouncer`; Chrome shows unacked-critical count badge; browser notifications and sound off by default (`ui.notifications`).
- [ ] **Step 1:** Tests, one per rule with before/after states (kill switch on, loss cap tripped, pool capped, stream stale → recovered, Dhan token < 1 h, readiness failed, order rejected, new high-severity error event); no duplicate alert for an unchanged condition across 100 evaluations; cap at 200; ack persistence when storage throws.
- [ ] **Steps 2–5:** fail → implement; subscribe `evaluateRules` in `DockApp` → pass → commit `feat(alerts): rules engine and alerts panel`.
### Task 5.10: `health` panel
Tiles: Stream, Feed, Dhan token (countdown from `DhanAuthContext`), Rate limit (`/telemetry/dhan-rate-limit`), Scanner (cycle, last scan), Recorder, Readiness, Live broker, Errors (last 5), Build id; each has state word + icon + as-of + link command to the owning panel; "Copy diagnostics" copies JSON (assert no tokens/keys are in it). Tests: each tile state mapping, diagnostics JSON contains no field named like `token|secret|key`.
### Task 5.11: Register presets and verify
Append all new panels to `PANELS`; ensure `layoutModel.test.ts` preset validation passes for all seven workspaces; Playwright `dock_workspaces.spec.ts` visits every workspace and asserts each expected panel title is visible and axe reports 0 serious/critical.

For each of 5.1–5.10: Step 1 tests (names as above) → Step 2 run FAIL → Step 3 implement and register → Step 4 run PASS + `tsc` → Step 5 commit `feat(panels): <ids>`.

---

# Phase 6 — Command palette and polish features

### Task 6.1: Command palette
**Files:** `frontend/src/features/commands/{CommandPalette.tsx,commandRegistry.ts}`, test, `e2e/specs/palette.spec.ts`.
**Interfaces — Produces:** `registerCommands(): Command[]` where `Command = {id; title; keywords: string[]; hint?: string; danger?: boolean; run(ctx: CommandContext): void|Promise<void>}`; fuzzy scorer `scoreCommand(query, command): number`. Includes: open each panel, switch workspace, save/reset layout, go to symbol (searches signals, positions, universe), scan now, refresh data, theme, density, shortcuts help, kill switch (opens confirmation only), close all positions (opens confirmation only), reset portfolio (opens confirmation only), every `DockCommands` entry.
- [ ] **Steps 1–5:** tests: ranking (exact > prefix > fuzzy), danger commands never call `actions.*` directly (spy), `Ctrl+K` opens/closes, `Esc` closes and restores focus, `aria-activedescendant` updates with arrows, axe clean. Commit `feat(commands): command palette`.

### Task 6.2: Tables rollout
Apply `useTable` (column chooser, sort memory, CSV, keyboard rows, windowing > 150 rows with `@tanstack/react-virtual`) to `signals`, `positions-table`, `trades`, `audit`, `orders`, `attribution`. Test: 300-row fixture renders ≤ 60 DOM rows; Arrow/Enter navigation selects; column choice persists; CSV downloaded content matches visible columns.
- [ ] **Steps 1–5:** commit `feat(tables): institutional table behaviour`.

### Task 6.3: Density, announcements, reduced motion
`ui.density` toggle persists; `LiveAnnouncer` receives new-signal and risk-state messages from the store (port logic from `App.tsx:470-500`); verify `prefers-reduced-motion` disables the live-banner pulse. Tests for each.
- [ ] **Steps 1–5:** commit `feat(ui): density and announcements`.

---

# Phase 7 — Hardening, parity proof, cutover

### Task 7.1: Accessibility suite
`frontend/e2e/specs/a11y_dock.spec.ts`: for every workspace in light and dark run `@axe-core/playwright`-style checks using the existing `axe-core` dependency injected via `page.addScriptTag`; assert 0 `serious`/`critical`. Manual script `docs/A11Y_CHECKLIST.md` (keyboard-only trading-day walkthrough; VoiceOver smoke; target size; zoom 200 %; reflow at 320 px for MobileShell). Fix findings.
### Task 7.2: Performance and bundle gates
`frontend/e2e/specs/perf.spec.ts` feeds a mocked SSE (Playwright `route`) with 300 signals, 200 trades and 10 ticks/s for 60 s; asserts no `longtask` > 100 ms more than 3 times and JS heap growth < 30 MB; `scripts/check-bundle.mjs` fails if initial gzip > 450 KB or any lazy chunk imported eagerly; add `npm run check:bundle`.
### Task 7.3: Full e2e flows
Extend `frontend/e2e/pages/DashboardPage.ts` with dock locators; specs: auth capability dialog on 401; kill switch typed-phrase flow shows `failed[]` symbols; close position through confirm then audit row appears in `audit` panel; stale stream (route-block SSE for 20 s) shows global banner and stale badges; workspace persistence across two browser contexts using the same backend; mobile viewport flow; shell flag rollback (`?shell=legacy` renders old `Terminal`, `localStorage.bb_shell` honoured).
### Task 7.4: Visual evidence
Playwright screenshots of all seven workspaces, light and dark, at 1440×900, and MobileShell at 390×844 → `docs/screenshots/institutional/`. Add a gallery to `docs/DOCKVIEW_NOTES.md`.
### Task 7.5: Parity sign-off
Run `panels/parity.test.ts`, all vitest, `tsc`, build, bundle check, e2e, backend pytest; write `docs/DOCKVIEW_PARITY.md` with the 17 items ticked, each linking its test name, plus success criteria S1–S8 with evidence. Commit `docs: parity sign-off`.
### Task 7.6: Cutover (owner approval required)
Precondition: owner has run one full paper session on `?shell=dock` with no console errors (`read_console_messages` log attached to the PR) and approved. Change `chooseShell` default to `'dock'`; keep `?shell=legacy`; test updated; release note in `README.md` (shortcuts, workspaces, flag). Commit `feat: dockview shell is the default`.
### Task 7.7: Cleanup (one release later, owner-triggered)
Delete legacy `Terminal.tsx`, `Blotter.tsx`, `Header.tsx` desk-only parts, `App.tsx` logic (keep `<App>` as the shell chooser), `ControlScreen` duplicates, unused tests; move reused components from `components/` into `panels/<id>/` where single-use; update `docs`; run everything again. Commit `chore: remove legacy terminal shell`.

---

## Self-review (against the spec)

- **Coverage:** R1.1–R1.5 → 1.5, 1.9, 5.1, 5.10, 6.1; R2.x → 1.3, 1.4, 1.7, 1.8, 5.x frames; R3.x → 4.3, 4.4, 5.3–5.6; R4.x → 4.4, 5.7, 5.8, 2.8; R5.x → 4.4, 5.1, 5.2; R6.x → 4.2, 5.8, 2.8, 7.5 (EOD report: reuse `/api/journal/export.csv` and `summary.html` via the `journal` panel — **add a button in Task 2.6**); R7.x → 5.9, 5.10, 1.9; R8.x → 3.x, 6.x. Parity items 1–17 → Phase 2 and 2.9. S1–S8 → 7.5.
- **Gap fixed inline:** Task 2.6 must include an "End-of-day report" button in `journal` that downloads `/api/journal/export.csv?start=&end=` and opens `/api/journal/summary.html` (R6.3), with a test.
- **Types:** `Selection`, `SliceName`, `PanelProps`, `DockCommands`, `LayoutSpec`, `ActionResult`, `Alert` are defined once (Tasks 1.3, 1.6, 1.8, 3.1, 3.3, 1.5, 5.9) and referenced by name elsewhere.
- **Dependencies between tasks:** 1.x before 2.x; 3.1 before 3.3; 4.x independent of 3.x and may run in parallel (different files); 5.x needs 4.4 and 1.8; 6.1 needs 3.4 and 5.x; 7.x last.
