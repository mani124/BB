# Dockview dashboard: progress

Read this first when resuming. Spec: `docs/superpowers/specs/2026-10-22-institutional-dockview-dashboard-design.md`. Plan: `docs/superpowers/plans/2026-10-22-institutional-dockview-dashboard.md`. Findings: `docs/DOCKVIEW_NOTES.md`.

## Where I am
- Branch: `feat/dockview-shell` (Phase 0). Next branch per phase is stacked on the previous one: `feat/dockview-p1-foundations`, `feat/dockview-p2-panels`, ...
- Local test setup (cloud container): `export PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome DASHBOARD_CAPABILITY=$(cat backend/data/dashboard_key)`; backend venv at `backend/.venv` (git-excluded). Do not commit `frontend/test-results` or `frontend/playwright-report` changes (`git checkout` them before committing).

## Phase status
| Phase | Status | PR |
|---|---|---|
| 0 Baseline and spike | done, gate passed (MIT, D1 pass, D2 pass) | (see below) |
| 1 Foundations | not started | |
| 2 Panel parity | not started | |
| 3 Dock host, layouts, keyboard, mobile | not started | |
| 4 Backend additions | not started | |
| 5 New panels | not started | |
| 6 Palette and polish | not started | |
| 7 Hardening and parity proof (7.1-7.5) | not started | |
| 7.6 Cutover, 7.7 Cleanup | waiting for owner | |

## Tasks done
- 0.1 Baseline recorded (Vitest 141, pytest 821, e2e 11, 14 pre-existing tsc errors).
- 0.2 Spike: dockview-react 8.6.1 MIT; pop-out and serialisation work; decisions D1-D6 in notes.

## Test results (latest)
- Vitest 141 pass; build ok (149.83 kB gzip); pytest 821 pass; e2e 11 pass (with env vars above).

## Blocked
None.

## Decisions made
- Pinned `dockview-react` at exactly 8.6.1.
- Repaired out-of-sync `frontend/package-lock.json` with `npm install` (needed for `npm ci`).
- `playwright.config.ts` honours `PW_CHROMIUM_PATH` (additive; default behaviour unchanged).
- tsc baseline has 14 pre-existing errors; new code must not add any.
