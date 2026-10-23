# Dockview shell: parity sign-off

Status: the dock shell (`/?shell=dock`) is feature-complete against spec section 6.3. The legacy terminal is still the default. Switching the default (7.6) and deleting the legacy code (7.7) are waiting for the owner.

Test names below are Vitest (`frontend/src/...`) or Playwright (`frontend/e2e/specs/...`). Backend tests are under `backend/tests/`.

## Parity checklist (spec 6.3)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Signals list with filters (setup, CE/PE, index/stock, timeframe including 3m), sort, watching, selection | Done | `panels/panels.test.tsx`: "signals renders rows", "signals shows a 3m signal when 3m is chosen", "signals selection updates the store"; `e2e/dock_layout.spec.ts`: "the Trading workspace shows signals, focus, positions table and positions" |
| 2 | Focus view for signal, position and candidate | Done | `panels/panels.test.tsx`: "focus follows the selected position and pins", "focus pinned subject ignores later selection"; `components/SignalDetails.test.tsx`, `components/WatchStatus.test.tsx` |
| 3 | Open positions list with close; positions table with columns and close | Done | `panels/panels.test.tsx`: "positions asks for confirmation before closing and calls actions.closePosition", "positions-table close goes through the confirm dialog"; `panels/DataTable.test.tsx`; `e2e/dock_flows.spec.ts`: "closing a position asks first, sends nothing until confirmed, then the audit panel lists it" |
| 4 | Chart for a selected position, replay of closed trades | Done | `panels/panels.test.tsx`: "chart asks for a selection when none"; `components/PositionChartModal.test.tsx`, `components/ReplayControls.test.tsx` (replay lives in the Trades panel) |
| 5 | Trades list and detail, evidence state, chart, receipt, close paper trade, refresh | Done | `panels/panels.test.tsx`: "trades shows rows from the store"; `components/TradesScreen.test.tsx`, `components/TradeDetail.test.tsx`; `panels/phase5.test.tsx`: "trades panel honours the linked filter" |
| 6 | Session timeline with observations and links to trades | Done | `components/SessionScreen.test.tsx`; panel render loop in `panels/panels.test.tsx` |
| 7 | Review: today, trades, setups, costs, telemetry, journal notes, end-of-day report | Done | `panels/panels.test.tsx`: "journal has an end-of-day report button that requests today summary"; `components/CostPanel.test.tsx`, `SetupStatsPanel.test.tsx`, `TelemetryPanel.test.tsx`, `JournalPanel.test.tsx`; `e2e/dock_all_workspaces.spec.ts` (Review) |
| 8 | Earnings book (summary, positions, candidates, calendar CRUD, sync, IV import, run cycle, square off) | Done | `components/EarningsPanel.test.tsx`; `e2e/dock_all_workspaces.spec.ts` (Earnings), `e2e/dock_layout.spec.ts`: "switching to Earnings shows the earnings panel" |
| 9 | Runtime settings with audit and per-key reset | Done | `components/SettingsPanel.test.tsx`; `panels/phase5.test.tsx` audit panel merges settings changes |
| 10 | Live routing: mode, arm, enable, resume, reconcile, broker login/logout, retry exit, orders | Done | `components/LiveRoutingPanel.test.tsx`; `panels/phase5.test.tsx`: "orders panel"; `e2e/dock_all_workspaces.spec.ts` (Execution). No test sends anything to a broker. |
| 11 | Control: auto-enter, kill switch, scan now, dashboard key, setup modes, reset | Done | `panels/panels.test.tsx`: "controls calls actions for auto-enter, scan, setup mode", "controls reset needs confirmation", "controls opens the dashboard key dialog"; `shell/Chrome.test.tsx` kill switch tests; `e2e/dock_flows.spec.ts`: "kill switch: typed phrase is required, failed positions are named" |
| 12 | Header: risk chip, connection pills, scan cycle, theme toggle, Dhan connect, disconnect, token countdown, dashboard key dialog | Done | `shell/Chrome.test.tsx`; `shell/dhan.test.tsx`: "opens the connect dialog and Escape closes it"; `e2e/auth_capability.spec.ts`; `e2e/dock_flows.spec.ts`: "without a dashboard key the capability dialog opens (401 path)" |
| 13 | Index radar strip, connection banner, dashboard status banner, action error banner | Done, with a deviation | Radar: `panels/panels.test.tsx` "market renders". Connection banner and stale pills: `shell/Chrome.test.tsx` "marks a stale source with text"; `e2e/dock_flows.spec.ts` "a silent stream turns the status bar stale...". Deviation: the legacy dashboard-status banner is replaced by the status bar plus a per-panel as-of, stale and error strip with Retry; the action error banner is replaced by toasts and the alerts panel (`panels/PanelFrame.test.tsx`, `features/alerts/alerts.test.ts`) |
| 14 | Screen-reader announcements for new signals and risk state | Done | `features/alerts/announce.test.tsx` |
| 15 | Dhan auto-reconnect in demo mode with a real saved token, sentinels ignored | Done | `shell/dhan.test.tsx`: "Dhan auto reconnect (parity 15)" |
| 16 | Light and dark themes, reduced motion respected | Done | `e2e/a11y_dock.spec.ts` (both themes, all workspaces); `e2e/dock_motion.spec.ts` |
| 17 | Phone layout with four-pane switcher | Done | `shell/MobileShell.test.tsx`; `e2e/dock_mobile.spec.ts` |

## Success criteria (spec section 1)

| ID | Criterion | Evidence |
|---|---|---|
| S1 | Every parity item reachable in the new shell | Table above; `panels/parity.test.ts` checks that every item maps to registered panels |
| S2 | Nothing silently stale: each panel shows its own "as of" and goes visibly stale | `panels/PanelFrame.test.tsx`; "signals marks stale" and "signals shows an error strip" in `panels/panels.test.tsx`; `panels/phase5.test.tsx` error strip with Retry (risk); `e2e/dock_flows.spec.ts` silent-stream test |
| S3 | Layout save, restore, reset, rename, delete, pop-out and floating work; layout survives reload and a second browser | `features/layouts/useLayouts.test.tsx`; `backend/tests/test_ui_layouts.py`; `e2e/dock_workspaces.spec.ts`; `e2e/dock_layout.spec.ts` (drag survives reload); `e2e/dock_popout.spec.ts`; `e2e/dock_flows.spec.ts` "a layout saved in one browser context appears in a second one on the same backend" |
| S4 | Every dock operation has a keyboard path; axe 0 serious or critical on every workspace | `e2e/dock_keyboard.spec.ts`, `e2e/palette.spec.ts`; `e2e/a11y_dock.spec.ts` (7 workspaces, light and dark, colour contrast on); manual script `docs/A11Y_CHECKLIST.md` |
| S5 | Each mutating action writes one `action_audit` row with an outcome | `backend/tests/test_action_audit.py`; UI: `e2e/dock_flows.spec.ts` (audit panel lists the close; the panel refetches after an action) and `data/hooks/useApiData.test.tsx` |
| S6 | Initial JS gzip at most 450 KB; analytics and chart panels lazy; no dropped frames with 300 signals, 200 trades and 10 ticks a second | `npm run check:bundle`: initial JS 147.7 kB gzip, dock shell with its lazy chunks 273.0 kB gzip (budget 450 kB), DockApp is its own lazy chunk; `e2e/perf.spec.ts`: 60 s run, heap 26.7 to 27.6 MB, 0 long tasks over 100 ms |
| S7 | `tsc`, `vite build`, Vitest, Playwright and pytest pass; one full paper session on the new shell with zero console errors | Vitest 507 pass, tsc 14 errors (unchanged pre-existing baseline), build ok, bundle check ok, pytest 879 pass, Playwright 66 pass (4 screenshot specs skipped unless SCREENSHOTS=1). The paper session is **waiting for the owner** (needs a market day) |
| S8 | Rollback to the old terminal is one flag flip, tested | `shell/chooseShell.test.ts`; `e2e/dock_shell.spec.ts`: "the shell flag is remembered and ?shell=legacy rolls back"; `e2e/dock_flows.spec.ts`: "the legacy shell flag rolls back and bb_shell is honoured" |

## Hard rules, checked

- Dockview is the free MIT package `dockview-react` pinned at exactly 8.6.1. `dockview-enterprise` is not installed. Only Dockview is imported in `shell/dockHost.tsx`. Multi-row tabs, pinned tabs, auto-hide, compass drag and drop, smart guides, layout history, spatial keyboard navigation and keyboard docking are not used; our own equivalents are built.
- Only two runtime dependencies were added: `dockview-react` and `@tanstack/react-virtual` (3.10.8).
- Trading logic untouched: no changes in `backend/app/services` scanner, paper, order router, broker, setup or strategy files. Backend work is additive (`ui_store`, `action_audit`, `analytics`, their routers).
- Money actions (kill switch, close position, reset portfolio, live arm and enable) use the accessible confirm dialog, never `window.confirm`, with no optimistic UI and one request in flight. Audit middleware stores no request bodies for `/api/auth/*`, `/api/live/broker/*`, `/api/live/enable`.
- No test uses a live broker or places a live trade. Nothing was deployed and the VM was not touched.

## Waiting for the owner

- **7.6 Cutover**: change the default shell to dock. Needs one full paper session on `?shell=dock` with no console errors and the owner's approval.
- **7.7 Cleanup**: delete the legacy terminal, one release after the cutover.

## Known gaps and decisions

- `signals` stays a card list and `trades` keeps its master-detail `TradesScreen`; the shared virtualised `DataTable` is used by positions blotter, orders, attribution and audit.
- Screenshots and e2e run against a throwaway journal with demo data, so performance and attribution panels show empty states. Re-check them with real paper trades.
- Mobile command palette omits dock and workspace commands.
- Dockview group and our panel frame both expose `role=region`; axe passes, a screen reader may read the name twice.
- Not built (out of scope): opening-gap pause, persistent Dhan login, new setups, Dhan pacing, swing-book UI.

## Evidence files

- Screenshots: `docs/screenshots/institutional/` (all 7 workspaces in light and dark at 1440 by 900, the mobile shell at 390 by 844, the command palette). Regenerate with `SCREENSHOTS=1 npx playwright test e2e/specs/screenshots.spec.ts`.
- Manual accessibility script: `docs/A11Y_CHECKLIST.md`.
- Running notes and decisions: `docs/DOCKVIEW_PROGRESS.md`, `docs/DOCKVIEW_NOTES.md`.
