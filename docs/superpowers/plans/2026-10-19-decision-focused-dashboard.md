# Decision Focused Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's book-first navigation with a clear Watch, Trades, Session and Control experience across laptop and phone while preserving all existing information and actions.

**Architecture:** Add source-aware read models over the existing paper, CX and earnings stores; Setup 16 remains a labeled subset of the paper book so it is never counted twice. Keep source engines responsible for trading actions. Build four focused React screens over the read models, retain existing strategy panels as detail views until every capability has a reachable home, and reuse the current candlestick renderer with a source-aware chart API.

**Tech Stack:** FastAPI, SQLite, Python, React 18, TypeScript, Vite, Tailwind, `lightweight-charts` 4, pytest, Vitest/Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-19-decision-focused-dashboard-design.md`

## Global Constraints

- Existing trading and risk rules continue to decide entries; UI work must not change strategy behavior.
- Include main scanner/paper, Setup 16, commodities and FX, and earnings in Watch, Trades and Session; represent Setup 16 once within paper positions.
- Never invent reasons, OHLC bars, confidence scores, session events, costs or cross-book totals.
- Keep book-specific mode, freshness, status, actions and provenance visible; one failed book must not blank healthy books.
- Keep every current view and action reachable until parity is checked; preserve historical rows and existing database files with additive migrations.
- Support both existing light and dark themes on laptop and phone.
- No live order is placed by verification or browser demo data.

## Review Focus

1. Setup 16 position appears in paper portfolio and its overview: show one trade with a Setup 16 label, never two. Pinned by Task 1 test.
2. One book returns an error or stale snapshot while others work: show the failed source explicitly and keep other records. Pinned by Task 2 and Task 4 tests.
3. Older trade has no saved decision or candles: keep it findable and say which evidence is unavailable. Pinned by Task 3 and Task 6 tests.
4. A phone user closes an open trade and switches themes: correct book receives the confirmed action, the refreshed state appears, and chart text remains readable. Pinned by Task 6 and Task 8 checks.
5. A session spans midnight or another exchange window: use a recorded timestamp and explicit timezone, with no silent shift into another session. Pinned by Task 7 test.

## File and capability map

| Unit | Files | Responsibility |
| --- | --- | --- |
| Read contract | `backend/app/services/dashboard_read.py`, `backend/app/api/dashboard.py`, `backend/tests/test_dashboard_read.py` | Normalize source identity, candidates, trades, decisions, health; expose filtered read endpoints. |
| Evidence and chart storage | `backend/app/services/dashboard_evidence.py`, `backend/app/services/{paper_trader,cx_engine,earnings_engine}.py`, `backend/app/api/dashboard.py`, `backend/tests/test_dashboard_evidence.py` | Save decision snapshot and actual OHLC bars for new trades; source-aware chart read. |
| Frontend contract/client | `frontend/src/types/dashboard.ts`, `frontend/src/api/dashboard.ts`, related tests | Typed reads with per-source load/error state and stable links. |
| Shell/status | `frontend/src/App.tsx`, `frontend/src/components/{Header,DashboardStatus}.tsx` | Four primary jobs, source status, navigation and retained strategy details. |
| Watch | `frontend/src/components/{WatchScreen,WatchCandidateList,WatchCandidateDetail}.tsx` | Unified candidate list and source-specific explanations. |
| Trades | `frontend/src/components/{TradesScreen,TradeQueue,TradeDetail,TradeChart}.tsx` | Cross-book index, recorded explanation, real candles, safe action. |
| Session | `frontend/src/components/{SessionScreen,SessionTimeline,SessionInsights}.tsx` | Dated chronology, factual summaries and evidence-linked review prompts. |
| Control/preservation | `frontend/src/components/{ControlScreen,SettingsPanel}.tsx`, existing `Setup16Screen`, `CxScreen`, `EarningsPanel`, `ReviewScreen` | Organize permissions/settings and provide paths to all existing functionality. |
| Presentation | `frontend/src/index.css` or existing desk stylesheet, relevant component tests | Responsive layout, light/dark variables, touch and keyboard support. |

Preservation inventory for the final parity check: current Now signals/radar/open positions; Review Today/Trades/Setups/Costs/Analytics and journal; Setup 16 watchlist, funnel, decisions and settings; CX overview, candidates, positions and run; earnings summary, calendar, IV import, candidates, positions and run; Settings/runtime audit; auth, risk, kill switch, manual scan, live routing and portfolio controls. A former primary page may become a secondary detail destination, but none may silently disappear.

---

### Task 1: Normalize recorded trades and avoid double counting

**Files:** Create `backend/app/services/dashboard_read.py`, `backend/tests/test_dashboard_read.py`; modify `backend/app/api/dashboard.py` (new router), `backend/app/main.py`.

**Interfaces:** Produce `list_dashboard_trades(*, status: str | None = None, book: str | None = None, day: str | None = None) -> list[dict]`. Each row has `id` (`paper:<id>`, `cx:<id>` or `earnings:<id>`), `book`, `display_book`, `source_id`, `status`, `instrument`, `setup`, `opened_at`, `closed_at`, `mode`, `net_pnl`, `net_kind`, `evidence_state`. Expose `GET /api/dashboard/trades` with optional `status`, `book`, `day`; use `YYYY-MM-DD` for day and return newest first.

- [ ] **Step 1: Write failing tests** for paper, Setup 16, CX and earnings rows; assert a Setup 16 paper position appears once, stable IDs are unique, estimated open net differs from realized closed net, and legacy rows without timestamps/evidence remain present.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_dashboard_read.py -q`; expect new tests to fail.
- [ ] **Step 3: Implement** `list_dashboard_trades` using existing `paper_trader.get_portfolio`, `get_cx_engine().positions()` and `get_earnings_engine().positions()`; normalize in `dashboard_read.py` without altering source stores or strategy logic. Add router and include it in `main.py`.
- [ ] **Step 4: Run** the focused test and `cd backend && pytest tests/test_setup16_api.py tests/test_cx_book.py tests/test_earnings.py -q`; expect pass.
- [ ] **Step 5: Commit** the read contract and tests.

### Task 2: Normalize current watch and source health

**Files:** Modify `backend/app/services/dashboard_read.py`, `backend/app/api/dashboard.py`; create `backend/tests/test_dashboard_watch.py`; create `frontend/src/types/dashboard.ts`, `frontend/src/api/dashboard.ts`.

**Interfaces:** Produce `build_dashboard_watch(snapshot: dict, setup16: dict, cx: dict, earnings: dict, *, observed_at: str) -> dict`; expose `GET /api/dashboard/watch`. Response has `sources[]` with `book`, `mode`, `as_of`, `state` (`ready|stale|error|disabled|unknown`) and `message`; `candidates[]` with source-prefixed `id`, `book`, `stage`, `observed_at`, `is_preview`, `checks[]`, `block_reason` and raw source reference. Frontend `types/dashboard.ts` exports `DashboardBook = 'paper' | 'cx' | 'earnings'`, `DashboardWatch` and `DashboardTrade`; `api/dashboard.ts` exports `fetchDashboardWatch(): Promise<DashboardWatch>`.

- [ ] **Step 1: Write failing tests** for source mappings, true Setup 16 stage, CX/earnings preview labeling, and one source failure while healthy sources remain visible. A missing `as_of` becomes `unknown`, never fresh.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_dashboard_watch.py -q`; expect fail.
- [ ] **Step 3: Implement** the mapper and endpoint, adapting existing `/api/signals`, `/api/setup16/overview`, `/api/cx/overview` and `/api/earnings/candidates` semantics. Do not record on-demand previews as decisions. Type the frontend response in `types/dashboard.ts`.
- [ ] **Step 4: Run** focused backend tests and `cd frontend && npm run build`; expect pass.
- [ ] **Step 5: Commit** watch read models and types.

### Task 3: Preserve entry evidence and actual chart bars

**Files:** Create `backend/app/services/dashboard_evidence.py`, `backend/tests/test_dashboard_evidence.py`; modify `backend/app/services/{paper_trader,cx_engine,earnings_engine}.py`, `backend/app/api/dashboard.py` and existing source chart storage as needed.

**Interfaces:** Produce `save_trade_evidence(book: str, position_id: str, decision: dict, bars: dict[str, list[dict]]) -> None` and `get_trade_evidence(book: str, position_id: str) -> dict | None`. Expose `GET /api/dashboard/trades/{book}/{position_id}` and `GET /api/dashboard/trades/{book}/{position_id}/chart`. Detail returns `reason_state: recorded|unavailable`; chart returns recorded OHLC plus indicator/marker/level fields and `candle_state: recorded|unavailable`, never generated prices. Source book is `paper|cx|earnings`; Setup 16 uses `paper` plus setup label.

- [ ] **Step 1: Write failing tests** for durable entry reason/check values after restart, saved OHLC ordering, source isolation on identical IDs, and old trades returning explicit unavailable evidence/candles.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_dashboard_evidence.py -q`; expect fail.
- [ ] **Step 3: Implement** additive evidence storage in the existing trades database and hook the three engines at their persisted entry/exit points. Use the existing paper chart and its saved bars; capture only actual bars available to CX and earnings, with no background data fetch for display. Link existing telemetry decisions by `position_id` where present.
- [ ] **Step 4: Run** focused tests plus `cd backend && pytest tests/test_position_chart.py tests/test_paper_persistence.py tests/test_rms_and_telemetry.py -q`; expect pass.
- [ ] **Step 5: Commit** evidence capture and read paths.

### Task 4: Replace primary navigation and show honest status

**Files:** Modify `frontend/src/App.tsx`, `frontend/src/components/Header.tsx`; create `frontend/src/components/DashboardStatus.tsx`, `frontend/src/components/DashboardStatus.test.tsx`; modify `frontend/src/types/index.ts` and `frontend/src/components/Header.test.tsx`.

**Interfaces:** `AppTab` becomes `watch|trades|session|control` for primary navigation. Keep a separate `DetailView = 'legacy-review' | 'setup16' | 'cx' | 'earnings' | 'settings' | null` state in `App.tsx` for secondary destinations, with a clear Back link to the originating primary screen. `DashboardStatus` consumes `DashboardWatch['sources']`, risk, feed/stream status and open count. Existing strategy/review panels remain reachable from Control/secondary links until Tasks 5–8 have parity.

- [ ] **Step 1: Write failing tests** that the four tabs appear, Watch opens first, each source's paper/live/fresh/error state is textual, and the old strategy and Review panels remain reachable. Assert one stale source does not paint all sources stale.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/components/DashboardStatus.test.tsx src/components/Header.test.tsx`; expect fail.
- [ ] **Step 3: Implement** navigation, status component and temporary secondary links without removing existing panels or their action props.
- [ ] **Step 4: Run** focused tests and `cd frontend && npm run build`; expect pass.
- [ ] **Step 5: Commit** shell and status.

### Task 5: Build the Watch opening experience

**Files:** Modify `frontend/src/components/WatchScreen.tsx`, `frontend/src/components/WatchScreen.test.tsx`; create `frontend/src/components/{WatchCandidateList,WatchCandidateDetail}.tsx` and focused tests.

**Interfaces:** `WatchScreen` consumes `DashboardWatch`, active source/book/status filters and a selected candidate ID. Selection opens recorded measurements, met/missing checks, block reason, source and `as_of`; links to a trade/session event use stable source-prefixed IDs. Existing radar and scanner signal detail remain reachable in secondary detail.

- [ ] **Step 1: Write failing tests** for mixed-book candidate order/filtering, stale/empty/error source wording, preview versus active decision, and restored selection after refresh.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/components/WatchScreen.test.tsx`; expect fail.
- [ ] **Step 3: Implement** the candidate list/detail and source filters; retain existing radar/signal inspection access.
- [ ] **Step 4: Run** focused tests, `cd frontend && npm run build`; expect pass.
- [ ] **Step 5: Commit** Watch.

### Task 6: Build unified Trades and book-routed actions

**Files:** Create `frontend/src/components/{TradesScreen,TradeQueue,TradeDetail,TradeChart}.tsx`, `frontend/src/components/TradesScreen.test.tsx`; refactor `frontend/src/components/PositionChartModal.tsx` to share its `lightweight-charts` chart body; modify `frontend/src/App.tsx` and `backend/app/api/{cx,earnings}.py` only if a safe single-position close operation is implemented.

**Interfaces:** `TradesScreen` consumes normalized trades and detail/chart loaders; filters by query, book, status and date. `TradeChart` consumes the source-aware OHLC payload and renders candles, recorded entry/exit markers and available levels; no line-series substitute. `closeTrade(book: DashboardBook, sourceId: string): Promise<DashboardTrade>` routes only to a supported single-position endpoint; paper uses `POST /api/paper/close/{id}`. Unsupported books show no per-trade Close button until a guarded endpoint exists.

- [ ] **Step 1: Write failing tests** for all-book search and filters, trade explanation order, old-trade unavailable states, real candle series, stable queue selection, source-specific close confirmation, server refresh after success, and visible error after failure.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/components/TradesScreen.test.tsx src/components/PositionChartModal.test.tsx`; expect fail.
- [ ] **Step 3: Implement** queue/detail/chart layout using the existing candlestick renderer. Add safe per-position close endpoints for CX/earnings only if engine/store methods can identify and close one open position atomically; otherwise document unsupported action and retain their existing bulk square-off controls in Control.
- [ ] **Step 4: Run** focused tests, `cd frontend && npm run build`, and any added backend endpoint tests; expect pass.
- [ ] **Step 5: Commit** Trades.

### Task 7: Build an evidence-linked Session review

**Files:** Extend `backend/app/services/dashboard_read.py`, `backend/app/api/dashboard.py`; create `backend/tests/test_dashboard_session.py`, `frontend/src/components/{SessionScreen,SessionTimeline,SessionInsights}.tsx`, `frontend/src/components/SessionScreen.test.tsx`.

**Interfaces:** Produce `get_dashboard_session(day: str) -> dict`, exposed as `GET /api/dashboard/session?day=YYYY-MM-DD`. Return `events[]` ordered by recorded IST timestamp, source ID, type, evidence ID, raw reason/metrics and `evidence_state`; `by_book[]` separates realized from estimated and only reports known cost fields; `observations[]` references one or more event IDs. A missing stored decision yields no invented event.

- [ ] **Step 1: Write failing tests** for ordered cross-book decisions/entries/exits/errors, correct selected day across midnight, unavailable evidence, no double-counted Setup 16 positions, and an observation linked to real event IDs. Assert incompatible financial fields are omitted rather than zero-filled.
- [ ] **Step 2: Run** `cd backend && pytest tests/test_dashboard_session.py -q`; expect fail.
- [ ] **Step 3: Implement** session aggregation from telemetry and source stores, extending telemetry's current rolling-hours query with a bounded day-range read so arbitrary historical days work. Use conservative observations (for example, repeated recorded skip reason or feed errors). Keep existing Review subtabs available as detailed analysis.
- [ ] **Step 4: Write frontend tests** for timeline selection, trade/chart link, factual counts and no-event copy; run `cd frontend && npm test -- --run src/components/SessionScreen.test.tsx` and expect fail.
- [ ] **Step 5: Implement** Session components; run both focused suites and frontend build; expect pass.
- [ ] **Step 6: Commit** Session.

### Task 8: Organize Control, polish both themes and prove parity

**Files:** Create `frontend/src/components/ControlScreen.tsx`, `frontend/src/components/ControlScreen.test.tsx`; modify `frontend/src/App.tsx`, `frontend/src/components/SettingsPanel.tsx`, `frontend/src/components/RiskControls.tsx`, and existing desk stylesheet; update affected accessibility tests.

**Interfaces:** Control gives access to existing paper settings, setup modes, CX and earnings settings/actions, calendar/IV import, runtime audit, auth, live routing, manual scan and legacy analysis details. The quick pause control changes only the source whose server entry permission it controls; kill switch explicitly names its close-all effect and remains separate. Both mutations read back canonical server state.

- [ ] **Step 1: Write failing tests** for the preservation inventory above, pause versus kill switch copy/effect, server-refreshed mutation state, and theme-specific chart/status styles. Include keyboard names/focus and phone trade-detail return-state checks.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/components/ControlScreen.test.tsx src/components/axe.test.tsx`; expect fail.
- [ ] **Step 3: Implement** Control and responsive styles at laptop and phone widths. Keep existing light/dark switch and token system; ensure warning/success text and chart lines meet contrast in both themes.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`; expect pass. Run focused backend dashboard tests and existing book/risk tests; expect pass.
- [ ] **Step 5: Browser-check** Watch, Trades, Session and Control at approximately 1366px and 390px in light and dark themes using recorded fixtures. Check no horizontal page scroll, readable candles and markers, touch targets, modal focus/return, and every preserved feature's navigation link. Do not trigger live orders.
- [ ] **Step 6: Commit** Control and presentation changes; review whole branch against the preservation inventory and spec.

## Self-review result

Each spec section maps to a task: identity/data (1–3), primary shell (4), Watch (5), Trades/chart (6), Session (7), Control/responsive/themes (8). The temporary secondary links are intentional protection against losing existing information while the new screens are built. The implementation may split a task at a review boundary, but it must not drop the acceptance checks or remove an old feature before parity is verified.
