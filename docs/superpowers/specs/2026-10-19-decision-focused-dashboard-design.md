# Decision focused dashboard redesign

## Intent

The dashboard is used to supervise mostly automatic trading. The owner wants to see what the scanners are watching, find any trade across the books, understand why and when it opened, inspect real price movement, and understand what happened during a session. The present navigation and dense panels make those jobs feel clumsy, particularly for someone who does not want to decode trading internals. The redesign must work on a laptop and a phone.

This document describes the whole product experience. It builds on the existing React, TypeScript, Vite, Tailwind and FastAPI application and on the first `Now`/signal inspection slice already on `codex/decision-focused-watch`. The approved browser mockups in `.superpowers/brainstorm/20712-1792417597/content/` illustrate direction; they are throwaway design material, not product code or a data specification.

## Desired experience

The user should be able to answer four questions without hunting through strategy tabs:

1. **What is being watched?** Which scanner and candidates are active, what conditions are met or missing, and how fresh is the evaluation?
2. **What did the system do?** Which decision was made, at what time, for which book, and whether it led to an order, open position, exit, or skip?
3. **Why this trade?** What recorded conditions caused the entry, what instrument and size were used, and what happened afterward on an actual candlestick chart?
4. **What needs my attention?** Whether data or an entry permission is unhealthy, which position is open, and which available action is safe and relevant now.

Success is a coherent path from Watch to a trade to the session history, with consistent naming and provenance. The user can supervise and understand automatic decisions from either device without learning the existing API or knowing which strategy page holds a record.

## Scope and boundaries

- Include the main scanner/paper book, Setup 16, commodities and FX (CX), and earnings in shared Watch, Trades, and Session views. Keep each book identifiable. All recorded open and closed trades from these books are discoverable through one Trades index, subject to the available history and date filters.
- Preserve book-specific strategy detail and settings as drill-down areas. Existing trading and risk rules continue to decide entries; the dashboard does not change strategy logic merely to fill the interface.
- Show recorded reasons and measurements. Do not invent confidence scores, causal explanations, recommendations, missing historical candles, or P&L values.
- Show actionable suggestions as evidence-based observations with a link to the underlying events. Examples: repeated feed gaps, frequent skips for the same guard, high recorded costs, or an unreviewed open trade. Suggestions are review prompts, not autonomous trading advice or changes to strategy settings.
- Do not merge unlike financial measures silently. Gross, charges, slippage and net appear only where the source records them, with the book and calculation basis visible. Cross-book totals require verified compatible semantics; otherwise show per-book summaries.
- Keep paper/live status explicit per book. Do not imply a paper-only book is live because another feed or book is live.

## Information structure

Primary navigation becomes **Watch · Trades · Session · Control**. Watch is the opening screen. Book names become filters and detail links within the relevant views rather than the main navigation. A persistent, compact status strip shows session date/time, each book's run mode and freshness, connection/feed health, whether automatic entries are allowed, open-position count, and any urgent issue. Warning and action text must be legible without relying on color. On a phone, the strip condenses to a brief status row that expands to the same detail.

### Watch: what scanners are watching

The top of Watch answers what is running now and whether it can act. The main list groups candidates by book and shows instrument, setup, last evaluation time, stage, met conditions, missing checks or block reason, and whether an entry is permitted. Users can filter by book and status and open a candidate to see the source measurements and evaluation trail. A scanner with no candidates should say that explicitly; stale or unavailable data must not look like a negative trading decision. Recently taken, skipped and changed decisions link to their trade or session event.

Candidate wording should be plain first (for example, “Waiting for candle close”); strategy codes and indicators are secondary detail. Show actual observed conditions rather than an artificial progress percentage. Each item exposes its own `as of` time, source/book, and data state. CX and earnings already expose candidate preview APIs and Setup 16 exposes contract stages; the main scanner exposes signals. The implementation must normalize these without falsely equating a preview with an active order or persisting an on-demand preview as a historical decision.

### Trades: all positions and decisions in one workspace

The default desktop layout is the user-selected **desk queue**: a searchable and filterable list of recent/open trades on the left, a selected trade's explanation and actions beside it, and a generous real candlestick chart in the same workspace. An open trade is easy to find; closed trades remain accessible by date, book, status, instrument and setup. The list should show a meaningful one-line event, time, status, source book and net/estimated net only when valid. Selection should not reset filters or scroll position.

The selected trade has a readable answer in this order: **what opened and when**, **why the engine opened it**, **what was planned** (entry, stop, targets, size and relevant guard state), **what changed since**, and **what happened at exit** if closed. The reason is a recorded decision snapshot, with individual triggering and blocking conditions, prices and timestamps where the engine has them. Distinguish recorded reasons, derived display text, and unavailable historical evidence. A trade without a saved decision snapshot remains visible but says the reason was not recorded; it must not manufacture one from current conditions.

The chart is an interactive, genuine OHLC candlestick chart using the existing `lightweight-charts` implementation as the starting point. Use recorded option/instrument candles for the traded instrument, with entry and exit markers, stops/targets and relevant indicators only where values exist. Offer underlying/related market view only where actual bars were saved. Entry and exit should be easy to locate on both laptop and phone. The current `/api/paper/positions/{id}/chart` supports the main paper portfolio, including Setup 16 trades, but cannot simply be reused for CX and earnings. Add a source-aware chart read path or per-book adapters and persist bars/evidence needed for newly recorded trades. For older trades lacking bars, show “Candles were not recorded for this trade” with available trade facts; never draw a simulated price path. The all-book trade requirement includes those older trades even when the chart is unavailable.

An available close-position action lives with the selected open trade, shows which book and instrument it will affect, requires confirmation, and reports the result. The action is shown only when that book supports it and the position can be closed through an existing or deliberately added endpoint. Avoid a global close action that hides which engine will receive it.

### Session: what happened and what to review

The default session view is a time-ordered story for the selected day, in Asia/Kolkata time with source market context where relevant. It includes scanner observations and skips that were actually recorded, entries, position changes, exits, control changes and data/connection warnings. Each event answers what happened, when, which book produced it, and why, then links to a trade or candidate when available. A selection opens the relevant decision evidence and real chart for a trade. If there were no events, say whether the book was idle, disabled or lacked data when that state is known.

Above the timeline, show factual counts and outcomes by book: candidates evaluated, skips, entries, open/closed trades, and gross/charges/slippage/net when recorded. Never treat a live unrealized estimate as a realized result. The suggestion area highlights patterns backed by specific session events and labels uncertainty. It should offer things to inspect, not tell the user to enter a trade or change a risk limit. The existing Review subtabs (Today, Trades, Setups, Costs, Analytics) can migrate into this structure or into secondary details without losing their functionality.

### Control: permissions and configuration

The persistent status area makes paper/live, feed freshness, automatic entry permission and risk state visible. **Pause automatic entries** is a quick, reversible control only for books whose entry permission it actually changes, and the UI names the affected book(s). It does not close positions. The existing **kill switch** is a separate emergency action that closes all applicable open positions and blocks new entries, with its existing confirmation requirement and an explicit effect summary. A per-trade close action is separate again. The interface must read back server state after every mutation and report success or failure; optimistic appearance alone is insufficient.

Control holds detailed lot sizing, setup modes, book-specific settings, loss limits, connection/authentication and any supported scheduling/manual scan controls. Explain the immediate effect and scope beside each control, and show last-changed time or an audit record when the backend records one. Where no reliable audit history exists, do not imply that a full change history is available. Preserve existing settings capabilities even if their navigation changes.

## Laptop and phone behavior

On laptop, Watch uses a scannable candidate list with a persistent detail panel; Trades uses the desk queue and large chart; Session uses a timeline with a detail panel. Main pages keep the same ordering of questions and status wording. Avoid many independent scroll panes that hide content.

On phone, each primary screen begins with a short status summary and one clear list. Selecting a trade opens a full-screen detail view with explanation, chart and relevant action in that order; returning restores list filters and scroll. Charts support touch pan/zoom and fit the screen without horizontal page scrolling. Destructive actions use explicit confirmation; controls and tap targets stay usable at phone size. Critical meaning is in text and shape as well as color. Both existing light and dark themes remain available; the design uses clearer hierarchy, spacing and typography rather than relying on a decorative market-terminal look. This visual treatment is a design call for review, not a separate user-approved aesthetic choice.

## Data and state design

Use a normalized **read model** across the four books. A record keeps stable source/book and source ID, event time with timezone, observed time, freshness, status, instrument, mode, raw source reference, normalized fields and an evidence-availability flag. The implementation may expose this from a new backend read API or dedicated adapters, but the contract must be explicit and tested at book boundaries. Distinguish live scanner state, on-demand candidate previews, durable decisions, positions and chart bars. Stable IDs and event timestamps are needed so Watch, Trades and Session link to the same item without ambiguity.

Capture the entry decision snapshot at the time the engine decides, including rule/check names and their observed values, order intent and resulting execution/position identifiers. Capture exit reason and significant management events similarly. Preserve existing stored history; migrations should be additive and safe when fields are absent. For past records without this evidence, render the known trade fields with an honest “not recorded” state. Session recommendations must be generated from durable facts rather than current scanner state used as a proxy for yesterday.

Each source may refresh differently (the main scanner streams; other sections currently poll). The UI must show source-specific last update and stale/error state. One stale book must not freeze healthy books. Do not silently replace an error with empty data. For any action, route through the owning book and refresh the canonical state after the response.

## Delivery order and verification

This is one dashboard redesign delivered in reviewable slices, with shared contracts first:

1. Define normalized book, candidate, decision, trade and chart contracts; inventory data and action gaps for all books. Add durable evidence capture where needed. Verify missing historical evidence is explicit.
2. Build the shared shell/status and Watch opening screen across books. Verify stage, freshness, mode and entry permission match each source.
3. Build unified Trades list/detail and real chart coverage. Verify active and closed trades from every book, entry/exit markers, unavailable-candle behavior, phone flow and book-specific close actions.
4. Build Session timeline, factual summaries and evidence-linked observations. Verify chronological order, timezone labeling, no fabricated history, and compatible financial measures.
5. Move detailed controls and remaining book features into Control/secondary views; finish phone responsiveness, keyboard/screen-reader behavior and visual polish.

The implementation plan should set API schemas, migrations, component boundaries, route/navigation changes, and focused tests for cross-book mappings, missing data, action routing and core user flows. Existing frontend tests and build should pass at each slice. Browser checks should cover laptop and phone widths with real or representative recorded data. Market/trading actions need explicit non-production test fixtures; no UI verification should place a live trade.

## Decisions left to the builder

- Exact component/file structure, API route names, pagination and caching strategy.
- Typography and spacing tokens consistent with the current theme system.
- Whether secondary strategy details are nested routes or panels, as long as the four primary jobs remain clear and the existing capabilities remain reachable.
- Whether normalized read models are assembled server-side or via a thin frontend layer, provided identity, freshness and evidence rules above hold and cross-book tests cover the result.

## Design calls for user review

- Keep both light and dark themes and change visual hierarchy more than visual identity.
- Use Watch, Trades, Session and Control as the main navigation.
- Show any historical trade even if its original reason or candles were not recorded, with a clear unavailable state.
- Treat session suggestions as evidence-linked review prompts, never automatic trading instructions.
