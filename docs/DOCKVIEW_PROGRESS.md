# Dockview dashboard: progress

Read this first when resuming. Spec: `docs/superpowers/specs/2026-10-22-institutional-dockview-dashboard-design.md`. Plan: `docs/superpowers/plans/2026-10-22-institutional-dockview-dashboard.md`. Findings: `docs/DOCKVIEW_NOTES.md`.

## Where I am
- Branch: `feat/dockview-p1-foundations` (Phase 1, stacked on `feat/dockview-shell`). Next branch per phase is stacked on the previous one: `feat/dockview-p1-foundations`, `feat/dockview-p2-panels`, ...
- Local test setup (cloud container): `export PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome DASHBOARD_CAPABILITY=$(cat backend/data/dashboard_key)`; backend venv at `backend/.venv` (git-excluded). Do not commit `frontend/test-results` or `frontend/playwright-report` changes (`git checkout` them before committing).

## Phase status
| Phase | Status | PR |
|---|---|---|
| 0 Baseline and spike | done, gate passed (MIT, D1 pass, D2 pass) | (see below) |
| 1 Foundations | done (tasks 1.1-1.9) | PR pending |
| 2 Panel parity | not started | |
| 3 Dock host, layouts, keyboard, mobile | not started | |
| 4 Backend additions | not started | |
| 5 New panels | not started | |
| 6 Palette and polish | not started | |
| 7 Hardening and parity proof (7.1-7.5) | not started | |
| 7.6 Cutover, 7.7 Cleanup | waiting for owner | |

## Tasks done
- 1.1 tokens/density/dockview theme + contrast tests; 1.2 store core; 1.3 appStore + SSE stream; 1.4 pollers; 1.5 actions + auth + confirm; 1.6 selection; 1.7 lib (time, numbers, csv, useTable); 1.8 PanelFrame + registry; 1.9 shell flag, Chrome, StatusBar, ModeBanner, kill switch (DhanConnectDialog extracted from Header).
- 0.1 Baseline recorded (Vitest 141, pytest 821, e2e 11, 14 pre-existing tsc errors).
- 0.2 Spike: dockview-react 8.6.1 MIT; pop-out and serialisation work; decisions D1-D6 in notes.

## Test results (latest)
- Vitest 258 pass; tsc errors 14 (baseline, no new); build ok (main chunk 150.64 kB gzip, DockApp lazy chunk 10.6 kB gzip); pytest 821 pass (backend untouched); e2e 14 pass (with env vars above).

## Blocked
None.

## Decisions made
- Pinned `dockview-react` at exactly 8.6.1.
- Repaired out-of-sync `frontend/package-lock.json` with `npm install` (needed for `npm ci`).
- `playwright.config.ts` honours `PW_CHROMIUM_PATH` (additive; default behaviour unchanged).
- tsc baseline has 14 pre-existing errors; new code must not add any.
