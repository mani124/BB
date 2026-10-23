# Accessibility checklist for the dock shell

Automated checks run on every change. The manual script below is for the owner (or a reviewer) before the dock shell becomes the default. Open the dock with `/?shell=dock`.

## Automated (already in the repo)

| Check | Where |
|---|---|
| axe, 0 serious or critical violations, all 7 workspaces, light and dark, colour contrast included | `frontend/e2e/specs/a11y_dock.spec.ts` |
| axe on every workspace while checking all panel titles are present | `frontend/e2e/specs/dock_all_workspaces.spec.ts` |
| axe on the command palette | `frontend/e2e/specs/palette.spec.ts` |
| axe on the mobile shell | `frontend/e2e/specs/dock_mobile.spec.ts` |
| axe per panel and for the chrome (jsdom) | `panels/panels.test.tsx`, `shell/Chrome.test.tsx`, `shell/MobileShell.test.tsx` |
| Keyboard-only dock operations (focus group, move, maximise, restore, close, float, dock) | `frontend/e2e/specs/dock_keyboard.spec.ts` |
| Reduced motion switches animations off | `frontend/e2e/specs/dock_motion.spec.ts` |

Limit: the e2e backend is a throwaway journal, so charts and tables are mostly empty states there. Re-run the manual script with real paper data.

## Manual: keyboard-only trading day (about 15 minutes)

Do not touch the mouse. `?` opens the shortcut list at any time.

1. Load `/?shell=dock`. Press Tab: the first stop is the workspace switcher; the kill switch is reachable from the chrome in at most a few presses and its label says "Kill switch".
2. Press Ctrl+K. The palette opens with the cursor in the search box; type `risk`, press Enter: the Risk overview panel opens or is focused. Press Ctrl+K, then Escape: focus returns to where it was.
3. Switch workspaces with the switcher (Enter on each of the 7 names). Each one shows every panel title as a tab.
4. In Trading: move to Signals, use the arrow keys through rows, Enter selects a signal and Focus follows. Press Tab to the Paper buy button and confirm it is announced by name.
5. Move a panel to the next group (Alt+Shift+]), maximise (Alt+M), restore (Alt+M), close (Alt+W), reopen it from the palette.
6. Open a panel menu with Enter on its "panel menu" button, choose Float, then Dock.
7. Positions table: arrow keys move the highlighted row, Enter selects the position, Tab to Close: a confirmation dialog opens, focus is inside it, Escape cancels and focus returns to the Close button. Confirm that nothing was sent.
8. Kill switch: open from the chrome, the Engage button stays disabled until `KILL` is typed. Escape cancels. Never confirm this on a live session just to test.
9. Alerts: raise one (stop the stream or let the token run low), confirm the badge count changes and the alerts panel lists it with an acknowledge button.
10. Reset workspace and Save layout as: both open dialogs whose first field has focus, errors are read as alerts.

Pass when every step works without a mouse, focus is always visible, and no step traps focus.

## Manual: screen reader smoke (VoiceOver on macOS, Safari or Chrome)

1. Cmd+F5 to start VoiceOver. Load the dock.
2. Stream state, scanner state and portfolio state are read from the status bar ("Stream: Fresh").
3. A new confirmed signal is announced politely ("New signal: NIFTY CE"). Engaging the kill switch announces "Kill switch is on".
4. Tables announce column headers and row counts (the long ones say how many rows exist even when only part of them are drawn).
5. Charts have a text summary or a data table (Equity and drawdown: "show data table").
6. Dialogs announce their title and trap focus. The command palette announces the number of results as you type.

## Target size, zoom and reflow

- Pointer targets: buttons in the chrome and panel menus are at least 24 by 24 CSS px (WCAG 2.2 AA 2.5.8). Row action buttons in dense tables may be smaller than the comfortable density; switch density with the chrome toggle and confirm comfortable mode reaches 24 px.
- Zoom 200 percent (Cmd + three times): the chrome wraps, nothing is cut off, the dock is still usable, or the page falls back to the mobile shell below 1024 CSS px width.
- Reflow at 320 px width: the mobile shell shows one pane at a time, the kill switch stays visible, there is no horizontal page scroll (`dock_mobile.spec.ts`).
- Colour is never the only signal: profit and loss show a sign, statuses show words, stale data shows "Stale" text.
- `prefers-reduced-motion: reduce` stops shimmer and live pulses.

## Known gaps and notes

- Dockview exposes a `region` role on each group and our panel frame also exposes one with the panel name. axe accepts it; a screen reader may read the name twice. Flagged for the real-session review.
- Free Dockview has no spatial keyboard navigation, keyboard docking or pinned tabs. Group focus moves by geometric order, and docking is done through the panel menu.
