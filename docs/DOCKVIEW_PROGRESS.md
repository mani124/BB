# Dockview dashboard: progress

Read this first when resuming. Spec: `docs/superpowers/specs/2026-10-22-institutional-dockview-dashboard-design.md`. Plan: `docs/superpowers/plans/2026-10-22-institutional-dockview-dashboard.md`. Findings: `docs/DOCKVIEW_NOTES.md`.

## Where I am
- Branch: `feat/dockview-p3-dock-host` (Phase 3, stacked on `feat/dockview-p2-panels`). Next branch per phase is stacked on the previous one: `feat/dockview-p1-foundations`, `feat/dockview-p2-panels`, ...
- Local test setup (cloud container): `export PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome DASHBOARD_CAPABILITY=$(cat backend/data/dashboard_key)`; backend venv at `backend/.venv` (git-excluded). Do not commit `frontend/test-results` or `frontend/playwright-report` changes (`git checkout` them before committing).

## Phase status
| Phase | Status | PR |
|---|---|---|
| 0 Baseline and spike | done, gate passed (MIT, D1 pass, D2 pass) | (see below) |
| 1 Foundations | done (tasks 1.1-1.9) | #83 |
| 2 Panel parity | done (tasks 2.1-2.9) | #84 |
| 3 Dock host, layouts, keyboard, mobile | done (3.1-3.7) | PR pending |
| 4 Backend additions | not started | |
| 5 New panels | not started | |
| 6 Palette and polish | not started | |
| 7 Hardening and parity proof (7.1-7.5) | not started | |
| 7.6 Cutover, 7.7 Cleanup | waiting for owner | |

## Tasks done
- 3.1-3.7: `features/layouts` (layoutModel, presets, layoutApi, useLayouts), `shell/dockHost.tsx` (only Dockview import), `WorkspaceSwitcher` with layout menu, `features/shortcuts.ts`, `commands/{dockCommands,ShortcutHelp}`, floating and pop-out with fallbacks and re-open banner, `MobileShell` (below 1024 px).
- 2.1-2.9: 16 panels (signals, focus, positions, positions-table, chart, market, trades, session, journal + End-of-day report, earnings, settings, live, controls, telemetry, costs, setup-stats), `panels/definitions.ts`, `panels/parity.test.ts`, toasts, `actions.request`, confirm adapters for legacy components.
- 1.1 tokens/density/dockview theme + contrast tests; 1.2 store core; 1.3 appStore + SSE stream; 1.4 pollers; 1.5 actions + auth + confirm; 1.6 selection; 1.7 lib (time, numbers, csv, useTable); 1.8 PanelFrame + registry; 1.9 shell flag, Chrome, StatusBar, ModeBanner, kill switch (DhanConnectDialog extracted from Header).
- 0.1 Baseline recorded (Vitest 141, pytest 821, e2e 11, 14 pre-existing tsc errors).
- 0.2 Spike: dockview-react 8.6.1 MIT; pop-out and serialisation work; decisions D1-D6 in notes.

## Test results (latest)
- Vitest 369 pass; tsc errors 14 (baseline, no new); build ok (main chunk 151.22 kB gzip, DockApp lazy chunk 120.05 kB gzip + 10.78 kB css); pytest 821 pass (backend untouched); e2e 31 pass (with env vars above; 4 new dock specs: layout, keyboard, popout, workspaces, mobile).

## Blocked
None.

## Decisions made
- Pinned `dockview-react` at exactly 8.6.1.
- Repaired out-of-sync `frontend/package-lock.json` with `npm install` (needed for `npm ci`).
- `playwright.config.ts` honours `PW_CHROMIUM_PATH` (additive; default behaviour unchanged).
- tsc baseline has 14 pre-existing errors; new code must not add any.
- Phase 2: legacy components got optional `confirmFn` / `confirmRiskChanges` props (default keeps `window.confirm`), so the legacy shell is unchanged and the dock passes the accessible dialog.
- Phase 2: mutations inside the embedded legacy components (earnings calendar, settings save/reset, live routing calls, journal notes) still call `apiFetch` directly; audit comes from the server middleware in Phase 4, confirmations go through the dock dialog. Money actions on panels I wrote (close, auto-enter, setup modes, reset, kill switch) use `actions.*`.
- Phase 2: `chart` panel shows the selected open position (inline `PositionChartModal`); closed-trade chart and replay stay inside the `trades` panel (existing `TradeDetail`).
- Phase 2: no screenshots yet, since panels have no host until Phase 3; Phase 3 screenshots show them in the dock.
- Phase 3: the server layout API (`/api/ui/layouts`) arrives in Phase 4. Until then `loadLayouts` falls back to `localStorage.bb_layouts` (a 404 is treated like any server failure). Client contract: `GET /api/ui/layouts` returns a list of `{name, schema_version, body, updated_at}` (name is `workspace:<n>` or `custom:<n>`); `PUT /api/ui/layouts/{name}` takes `{kind, schema_version, body}`; snapshots and restore as in spec 8.3.
- Phase 3: presets already name Phase 5 panels (risk, exposure, audit, alerts, perf-summary, equity, attribution, distributions, execution, orders, health, readiness, recorder, universe); `validateLayout` drops unregistered ids, so workspaces show only built panels until Phase 5. `PLANNED_PANEL_IDS` in `presets.ts` is emptied in Phase 5 and the preset test then requires zero drops.
- Phase 3: group focus order is geometric (top then left) because spatial navigation is not in the free edition; Split needs a group with 2+ panels (toast otherwise); floating groups hold one panel (a multi-panel float is reduced to its first panel when saved); pop-outs restore as floating panels with a "Re-open pop-outs" banner.
- Phase 3: command palette (Ctrl+K) and the alerts warning "Saved layout was invalid; default restored" are visible only after Phases 5 and 6; the warning is already pushed through `alertsHook`. Keyboard e2e covers focus group, move, maximise/restore, close, float/dock via the panel menu; reopen-from-palette is added with the palette in Phase 6.
- Phase 3: Dockview group and our PanelFrame both expose `role=region` with the panel name (axe passes at serious/critical); revisit in the Phase 7 a11y pass.
