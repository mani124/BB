# Dockview migration notes

Findings from Phase 0 of the institutional Dockview dashboard (spec `docs/superpowers/specs/2026-10-22-institutional-dockview-dashboard-design.md`). Date: 2026-10-22.

## Baseline (clean `main` at 6395f43)

| Check | Result |
|---|---|
| `npx vitest run` | 38 files, 141 tests, all pass |
| `npm run build` (`tsc && vite build`) | passes; `index-*.js` 510.76 kB raw, 149.83 kB gzip; `index-*.css` 30.59 kB raw, 7.02 kB gzip (single chunk, no code splitting yet) |
| `npx tsc -p tsconfig.app.json --noEmit` | **14 pre-existing type errors** in 9 files (`SessionScreen`, `TradeChart(.test)`, `TradeDetail`, `TradeQueue`, `WatchCandidate*`, `WatchStatus.test`, `axe.test`). `npm run build` still passes because the root `tsconfig.json` has no `include`. Rule for this project: the count must not grow (new code is type-clean). |
| `npm run test:e2e` | 11 specs, all pass **with the environment fixes below** |
| `cd backend && .venv/bin/pytest -q` | 821 passed |

### Environment fixes needed to run the baseline (not product bugs)

1. `frontend/package-lock.json` on `main` was out of sync with `package.json` (`npm ci` fails: missing `esbuild@0.28.2` entries). `npm install` repairs the lock file; the repaired lock file is committed in the Phase 0 PR.
2. This container has Chromium 1194 but Playwright 1.64.1 wants 1248, and no ffmpeg. `playwright.config.ts` now honours `PW_CHROMIUM_PATH` (launch executable) and disables video when it is set. Local run: `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
3. `e2e/fixtures/auth.fixture.ts` reads `backend/data/dashboard_key` through `__dirname`, which is undefined under this ESM package, so it silently falls back to a stale hard-coded key. Run e2e with `DASHBOARD_CAPABILITY=$(cat backend/data/dashboard_key)` after the backend has generated the key once. (Fixture not changed here.)

## Dockview spike

### Licence (D0)

Installed `dockview-react@8.6.1` (pinned exactly in `package.json`, no caret) which depends on `dockview-core@8.6.1`. `package.json` of both says `"license": "MIT"`. `LICENCE.md` of both packages is the standard MIT text, "Copyright (c) 2021 mathuo". **Licence gate: pass.** `dockview-enterprise` is not installed and must never be.

### API names confirmed in 8.6.1

- Component: `DockviewReact` with props `components`, `onReady({api})`, `tabComponents`, `defaultTabComponent`, `watermarkComponent`, `rightHeaderActionsComponent`, `leftHeaderActionsComponent`, `prefixHeaderActionsComponent`, `getTabContextMenuItems`. CSS: `import 'dockview-react/dist/styles/dockview.css'`; theme class `dockview-theme-light` / `dockview-theme-dark` on a wrapper.
- `api.addPanel({id, component, title, params, position:{referencePanel|referenceGroup, direction}})`, `api.removePanel`, `api.getPanel(id)`, `api.panels`, `api.groups`, `api.activeGroup`, `api.activePanel`.
- Serialise: `api.toJSON()` returns `{grid:{root,width,height,orientation}, panels:{id:{id,contentComponent,title,params?}}, activeGroup, floatingGroups?, popoutGroups?}`. Restore: `api.fromJSON(json)`. Layout-change event: `api.onDidLayoutChange`.
- Floating: `api.addFloatingGroup(panelOrGroup, {position:{left,top}, width, height})`; serialised under `floatingGroups`.
- Pop-out: `await api.addPopoutGroup(panelOrGroup, {popoutUrl})`; returns `true`/`false`. The URL must be same-origin; default `/popout.html`. We ship `frontend/public/popout.html` (empty page).
- Maximise: `api.maximizeGroup(panel)`, `api.exitMaximizedGroup()`, `api.hasMaximizedGroup()`.
- Move a panel: `panel.api.moveTo({group, position})`, `panel.api.setActive()`.
- Theme CSS variables (set on `.dockview-theme-*`): `--dv-group-view-background-color`, `--dv-tabs-and-actions-container-background-color`, `--dv-tabs-and-actions-container-height`, `--dv-tabs-and-actions-container-font-size`, `--dv-activegroup-visiblepanel-tab-background-color`, `--dv-activegroup-hiddenpanel-tab-background-color`, `--dv-inactivegroup-visiblepanel-tab-background-color`, `--dv-inactivegroup-hiddenpanel-tab-background-color`, `--dv-activegroup-visiblepanel-tab-color`, `--dv-activegroup-hiddenpanel-tab-color`, `--dv-inactivegroup-visiblepanel-tab-color`, `--dv-inactivegroup-hiddenpanel-tab-color`, `--dv-tab-divider-color`, `--dv-separator-border`, `--dv-paneview-header-border-color`, `--dv-drag-over-background-color`, `--dv-floating-box-shadow`, `--dv-sash-color`, `--dv-active-sash-color`, `--dv-border-radius`, `--dv-tab-font-size`.

### D1 pop-out context: PASS (Chromium)

Measured in Chromium 1194 via Playwright with a module-level counter store and a React context provider above `DockviewReact`:
- Pop-out opens (`addPopoutGroup` resolves `true`), the panel DOM is moved into the new window.
- The counter keeps updating inside the pop-out (`0` then `3` after 1.2 s), so the panel renders in the opener's React tree (portal): **same JS realm, the store and handlers keep working**.
- React context from the opener reaches the pop-out panel.
- Stylesheets are copied into the pop-out, the Dockview group view is themed.
- Closing the pop-out window returns the panel to the main dock; no panel is lost.
- Blocked pop-up (`window.open` stubbed to `null`): `addPopoutGroup` resolves `false`, logs a console error, panel stays docked.
- Serialised under `popoutGroups: [{gridReferenceGroup, position, url, data:{views, activeView, id}}]`.
- Firefox and Safari were **not tested** (only Chromium exists in this container). Decision: pop-out is enabled; failures show the "blocked" message (Task 3.5). No `BroadcastChannel` bridge is needed.

### D2 serialisation round trip: PASS

`toJSON` then `fromJSON` then `toJSON` is identical (tabs, active tab, sizes). Floating groups round-trip. A JSON that references an unknown component id makes `fromJSON` throw, logs "failed to deserialize layout. Reverting changes", **and leaves the dock empty** (0 panels). Rule: never pass unvalidated JSON to `fromJSON`; `validateLayout` drops unknown ids first, and on any thrown error the host loads the preset.

### D3 accessibility: tab semantics exist, one axe violation

Dockview renders `tablist`, `tab` (with `aria-selected`, `aria-label`, `aria-controls`), `tabpanel`, `region` natively. axe on the bare dock reports one serious violation: `nested-interactive` (the tab contains a close button). Decision: a custom `tabComponent` renders the title only (no nested button); closing is through the panel menu, `Alt+W`, and the command palette. Re-verify with axe in Task 3.3.

Free-edition keyboard: `api.moveToNext()` / `moveToPrevious()` are no-ops (paid keyboard docking), confirmed by test (no group change). We build our own commands on `panel.api.moveTo`, `maximizeGroup`, `addFloatingGroup`, `addPopoutGroup`.

### D4 theming

The variables listed above map to our tokens in `theme/dockview-theme.css` (Task 1.1) under `.dockview-theme-light` and `.dockview-theme-dark` selectors, applied on the dock wrapper according to the `dark` class on `<html>`.

### D5 bundle

Eager import of `dockview-react` plus the spike grew the main chunk from 149.83 kB to 246.76 kB gzip (+96.9 kB) and CSS from 7.02 kB to 17.45 kB gzip (+10.4 kB). Decision: the dock shell is loaded with `React.lazy` so the legacy shell keeps its current size and Dockview is a separate lazy chunk. The budget (initial gzip <= 450 kB) holds either way.

### D6 jsdom

`DockviewReact` mounts in Vitest/jsdom when `ResizeObserver` is stubbed (`globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }`); `addPanel`, `panels` and `toJSON` work; content layout is zero-sized, so layout behaviour is tested in Playwright instead. The stub goes into `src/test/setup.ts` when first needed.

### Decisions summary

| Id | Decision |
|---|---|
| D1 | Pop-out via Dockview as is (portal, same realm). No bridge. Blocked -> message. |
| D2 | Always validate our `LayoutSpec` before `toDockviewJson`/`fromJSON`; catch and fall back to preset. |
| D3 | Custom tab component without nested buttons; own keyboard commands. |
| D4 | Map `--dv-*` variables to our tokens for both themes. |
| D5 | Lazy-load the dock shell. |
| D6 | Unit-test panels and `layoutModel` in Vitest; test the dock itself in Playwright. |
