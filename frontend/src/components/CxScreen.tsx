import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import type { CxOverview, CxPosition } from '../types';

const money = (v: number | null | undefined, plus = false) => {
  if (v === null || v === undefined) return '-';
  const s = Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const tone = (v: number | null | undefined) => ((v ?? 0) > 0 ? 'desk-up' : (v ?? 0) < 0 ? 'desk-down' : '');
const hhmm = (s?: string | null) => (s ? (s.includes('T') ? s.slice(11, 16) : s.slice(0, 5)) : '-');

export const SETUP_TEXT: Record<string, string> = {
  SETUP_17_RANGE_BREAK: 'Setup 17 range break',
  SETUP_18_OPENING_RANGE: 'Setup 18 opening range',
  SETUP_19_BAND_FADE: 'Setup 19 band fade',
};
const POOL_TEXT: Record<string, string> = { commodity: 'Commodities (MCX)', currency: 'Currency (NSE)' };
const STATE_TEXT: Record<string, string> = {
  WATCHING: 'Watching', SESSION_CLOSED: 'Session closed', BOOK_OFF: 'Book is off', NO_CONTRACT: 'No contract found',
  NO_CANDLES: 'No candles', NO_OPTION_CHAIN: 'No option chain', STALE_DATA: 'Data is stale',
};
const REFRESH_MS = 10_000;

const Trades: React.FC<{ rows: CxPosition[]; empty: string; label: string; open?: boolean }> = ({ rows, empty, label, open }) => (
  rows.length === 0 ? <div className="p-4 text-xs desk-muted">{empty}</div> : (
    <div className="overflow-x-auto"><table className="desk-table" aria-label={label}>
      <thead><tr><th scope="col">Underlying</th><th scope="col">Setup</th><th scope="col">Option</th><th scope="col">In</th>{!open && <th scope="col">Out</th>}
        <th scope="col" className="r">Entry</th><th scope="col" className="r">{open ? 'Bid' : 'Exit'}</th><th scope="col">{open ? 'Invalidates at' : 'Reason'}</th><th scope="col" className="r">Net</th></tr></thead>
      <tbody>{rows.map((p) => (
        <tr key={p.id}><td className="desk-sym">{p.symbol}</td><td>{SETUP_TEXT[p.setup] ?? p.setup}</td><td>{p.strike} {p.side}</td><td>{hhmm(p.opened_at)}</td>
          {!open && <td>{hhmm(p.closed_at)}</td>}
          <td className="r desk-num">{p.entry_price}</td><td className="r desk-num">{open ? (p.last_bid ?? '-') : (p.exit_price ?? '-')}</td>
          <td>{open ? p.invalidate_level : p.exit_reason}</td>
          <td className={`r desk-num ${tone(open ? p.unrealized_net : p.net_pnl)}`}>{money(open ? p.unrealized_net : p.net_pnl, true)}</td></tr>
      ))}</tbody></table></div>
  )
);

/** The Commodities & Currency section: pools with their own loss caps, session state, positions and decisions. */
export const CxScreen: React.FC<{ initial?: CxOverview }> = ({ initial }) => {
  const [o, setO] = useState<CxOverview | null>(initial ?? null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/cx/overview');
      if (res.ok) { setO(await res.json()); setError(false); } else setError(true);
    } catch { setError(true); }
  }, []);

  useEffect(() => {
    if (initial) return undefined;
    void load();
    const id = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(id);
  }, [initial, load]);

  if (!o) return <div className="p-4 text-sm desk-muted">{error ? 'Could not load Commodities & Currency.' : 'Loading Commodities & Currency…'}</div>;
  const s = o.summary;
  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3" data-testid="cx-screen">
      <section className="desk-panel shrink-0" aria-labelledby="cx-title">
        <div className="desk-ph">
          <h2 id="cx-title">Commodities & Currency · Setups 17-19</h2>
          <span className={`desk-pill ${s.enabled ? 'up' : 'warn'}`}>{s.enabled ? 'ON' : 'OFF: nothing is entered'}</span>
          <span className="desk-pill">Paper only</span>
          <span className="text-xs desk-muted ml-auto">Updated {o.as_of}</span>
        </div>
        <div className="px-3.5 py-2.5 text-sm flex flex-wrap gap-x-6 gap-y-1">
          <span>Equity <b className="desk-num">{money(s.equity)}</b></span>
          <span>Realised <b className={`desk-num ${tone(s.realized_net_pnl)}`}>{money(s.realized_net_pnl, true)}</b></span>
          <span>Open P&L <b className={`desk-num ${tone(s.unrealized_net_pnl)}`}>{money(s.unrealized_net_pnl, true)}</b></span>
          <span>Trades <b className="desk-num">{s.closed_trades}</b> · win rate <b className="desk-num">{s.win_rate}%</b></span>
          <span>Per trade <b className="desk-num">{o.settings.lots}</b> lot · stop <b className="desk-num">{o.settings.sl_pct}%</b> · target <b className="desk-num">{o.settings.target_pct}%</b></span>
        </div>
        {!s.enabled && <div className="px-3.5 pb-2.5 text-xs desk-muted">Switch the book on under Settings → Commodities & Currency book. It needs a Dhan login with MCX and currency data.</div>}
      </section>

      <section className="desk-panel shrink-0" aria-label="Pools and sessions">
        <div className="desk-ph"><h3>Pools</h3></div>
        <div className="overflow-x-auto"><table className="desk-table" aria-label="Pools">
          <thead><tr><th scope="col">Pool</th><th scope="col">Status</th><th scope="col" className="r">Today</th><th scope="col" className="r">Loss cap</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Net</th></tr></thead>
          <tbody>{Object.entries(s.pools).map(([name, p]) => (
            <tr key={name}><td>{POOL_TEXT[name] ?? name}</td>
              <td>{!p.enabled ? 'Switched off' : p.loss_cap_tripped ? 'Loss cap reached' : 'Active'}</td>
              <td className={`r desk-num ${tone(p.day_pnl)}`}>{money(p.day_pnl, true)}</td>
              <td className="r desk-num">{p.loss_cap > 0 ? money(-p.loss_cap) : 'off'}</td>
              <td className="r desk-num">{p.closed_trades}</td>
              <td className={`r desk-num ${tone(p.realized_net_pnl)}`}>{money(p.realized_net_pnl, true)}</td></tr>
          ))}</tbody></table></div>
        <div className="px-3.5 py-2.5 flex flex-wrap gap-2" data-testid="cx-sessions">
          {Object.entries(s.sessions).map(([ex, st]) => (
            <span key={ex} className={`desk-pill ${st.open ? 'up' : ''}`}>{ex === 'MCX' ? 'MCX' : 'NSE currency'} {st.open ? (st.entry_allowed ? 'open' : 'open, no new entries') : 'closed'}</span>
          ))}
        </div>
      </section>

      <section className="desk-panel shrink-0" aria-label="Underlyings">
        <div className="desk-ph"><h3>Underlyings</h3></div>
        {Object.keys(s.symbols).length === 0 ? <div className="p-4 text-xs desk-muted">No cycle has run yet. It needs a Dhan login.</div> : (
          <div className="overflow-x-auto"><table className="desk-table" aria-label="Underlying status">
            <thead><tr><th scope="col">Underlying</th><th scope="col">State</th><th scope="col">Future</th><th scope="col">Option expiry</th><th scope="col">Last bar</th></tr></thead>
            <tbody>{Object.entries(s.symbols).map(([sym, v]) => (
              <tr key={sym}><td className="desk-sym">{sym}</td><td>{STATE_TEXT[v.state ?? ''] ?? v.state ?? '-'}</td><td>{v.contract ?? '-'}</td><td>{v.expiry ?? '-'}</td><td>{hhmm(v.last_bar)}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel shrink-0" aria-label="Open positions">
        <div className="desk-ph"><h3>Open positions</h3></div>
        <Trades rows={o.open_positions} empty="No open positions." label="Open positions" open />
      </section>
      <section className="desk-panel shrink-0" aria-label="Closed today">
        <div className="desk-ph"><h3>Closed today</h3></div>
        <Trades rows={o.closed_today} empty="No trades closed today." label="Closed today" />
      </section>
      <section className="desk-panel shrink-0" aria-label="Recent trades">
        <div className="desk-ph"><h3>Recent trades</h3></div>
        <Trades rows={o.recent_closed} empty="No closed trades yet." label="Recent trades" />
      </section>

      <section className="desk-panel shrink-0" aria-label="Decisions">
        <div className="desk-ph"><h3>Entries and skips (24h)</h3></div>
        {o.decisions.length === 0 ? <div className="p-4 text-xs desk-muted">Nothing recorded in the last 24 hours.</div> : (
          <div className="overflow-x-auto"><table className="desk-table" aria-label="Decisions">
            <thead><tr><th scope="col">Time</th><th scope="col">Underlying</th><th scope="col">Setup</th><th scope="col">Side</th><th scope="col">Decision</th><th scope="col">Reason</th></tr></thead>
            <tbody>{o.decisions.map((d, i) => (
              <tr key={`${d.ts}-${i}`}><td>{d.ts.slice(11, 19)}</td><td className="desk-sym">{d.symbol}</td><td>{SETUP_TEXT[d.strategy] ?? d.strategy}</td><td>{d.side}</td><td>{d.decision}</td><td>{d.reason}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
    </div>
  );
};
