# Dashboard API additions (Dockview dashboard, Phase 4)

All additions are new files plus one middleware registration and three router registrations in `backend/app/main.py`. No trading logic (scanner, setups, paper trader, exits, risk engine, order router, broker adapters) is changed. All routes sit behind the existing dashboard capability check.

## New routes

| Route | Purpose |
|---|---|
| `GET /api/ui/layouts` | List saved layouts (`workspace:<name>` and `custom:<name>`). |
| `PUT /api/ui/layouts/{name}` | Save a layout. Body `{kind, schema_version, body}`; max 256 KB (413), bad name or schema 422, NaN rejected. |
| `DELETE /api/ui/layouts/{name}` | Delete a custom layout. Built-in workspaces cannot be deleted (403). |
| `GET /api/ui/layouts/{name}/snapshots` | Last 20 versions, newest first. |
| `POST /api/ui/layouts/{name}/restore/{id}` | Return a snapshot body; the replaced state is kept as a new snapshot. |
| `GET /api/audit/actions` | Recent operator actions (filters: `limit`, `action`, `outcome`, `since`). |
| `GET /api/analytics/equity` | Equity curve, daily P&L, drawdown episodes. |
| `GET /api/analytics/attribution?group=` | P&L by `setup`, `symbol`, `side`, `hour`, `weekday` or `exit_reason`, with cost drag and a low-sample flag (< 20 trades). |
| `GET /api/analytics/distribution` | P&L, R and hold-time histograms, MFE/MAE points. |
| `GET /api/analytics/execution` | Slippage, spread, liquidity quartiles, charge breakdown, and a `not_recorded` list for fields the data does not have. |
| `GET /api/analytics/risk` | Open risk (entry minus stop times quantity) by underlying, side, pool and setup. |

Analytics routes take `from`, `to` (IST dates, inclusive), `book=paper|all`, `setup`, `side`. Quarantined trades are excluded and counted in `excluded`. Responses never contain NaN or Infinity.

## New tables (SQLite, `CREATE TABLE IF NOT EXISTS` on first start)

- `ui_layouts(name, kind, schema_version, body, updated_at)`
- `ui_layout_snapshots(id, name, taken_at, body)`; at most one snapshot per 60 s per layout, last 20 kept.
- `action_audit(id, ts, method, route, action, target, outcome, status, detail, client)`

No migration step is needed on deploy.

## Audit allowlist

Every mutating route has a named action (a test fails if a new mutating route has none). Routes under `/api/auth/*`, `/api/live/broker/*` and `/api/live/enable` are recorded without request bodies. Token-shaped strings in error text are redacted. Writing the audit row never blocks or fails the request.
