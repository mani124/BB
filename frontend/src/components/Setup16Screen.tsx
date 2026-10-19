import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { WatchlistPanel } from './WatchlistPanel';
import type { Setup16Contract, Setup16Overview, Setup16Trade } from '../types';

const money = (v: number | null | undefined, plus = false) => {
  if (v === null || v === undefined) return '-';
  const s = Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const tone = (v: number | null | undefined) => ((v ?? 0) > 0 ? 'desk-up' : (v ?? 0) < 0 ? 'desk-down' : '');
const hhmm = (s?: string | null) => (s ? (s.includes('T') ? s.slice(11, 16) : s.slice(0, 5)) : '-');

export const STAGE_TEXT: Record<string, string> = {
  SIGNAL: 'Signal',
  NO_BREAKOUT: 'Below upper band',
  NO_SQUEEZE: 'Broke out, no squeeze before',
  RED_BAR: 'Closed above band on a red bar',
  LOW_VOLUME: 'Volume too low',
  OUT_OF_WINDOW: 'Outside entry window',
  WARMUP: 'Warming up (too few bars today)',
  NO_DATA: 'No option chart data',
};
const MODE_TEXT: Record<string, string> = {
  off: 'OFF: signals are seen but no trade is entered',
  index: 'ON for indices only',
  stocks: 'ON for stocks only',
  all: 'ON for indices and stocks',
};

const REFRESH_MS = 10_000;

const FunnelBar: React.FC<{ funnel: Record<string, number>; total: number }> = ({ funnel, total }) => (
  <div className="px-3.5 py-2.5 flex flex-wrap gap-2" data-testid="s16-funnel">
    {Object.entries(funnel).filter(([, n]) => n > 0).map(([stage, n]) => (
      <span key={stage} className={`desk-pill ${stage === 'SIGNAL' ? 'up' : ''}`} title={`${n} of ${total} contracts`}>
        {STAGE_TEXT[stage] ?? stage} <b className="desk-num">{n}</b>
      </span>
    ))}
    {total === 0 && <span className="text-xs desk-muted">No option charts checked yet. Setup 16 is evaluated during market hours with a live Dhan session.</span>}
  </div>
);

const ContractRow: React.FC<{ c: Setup16Contract }> = ({ c }) => (
  <tr className={c.stale ? 'opacity-60' : ''}>
    <td className="desk-sym">{c.strike_symbol}{c.source === 'watchlist' && <span className="desk-pill ml-1" title="From the after-close watchlist">WL</span>}</td>
    <td>{STAGE_TEXT[c.stage] ?? c.stage}</td>
    <td className="r desk-num">{c.close ?? '-'}</td>
    <td className="r desk-num">{c.upper_bb ?? '-'}</td>
    <td className={`r desk-num ${c.pct_to_upper !== undefined && c.pct_to_upper <= 0 ? 'desk-up' : ''}`}>
      {c.pct_to_upper === undefined ? '-' : c.pct_to_upper > 0 ? `${c.pct_to_upper}% to go` : `${Math.abs(c.pct_to_upper)}% above`}
    </td>
    <td>{c.in_squeeze === undefined ? '-' : c.in_squeeze ? 'Squeezed' : 'Wide'}{c.bandwidth !== undefined && <span className="desk-muted"> · BW {c.bandwidth}%</span>}</td>
    <td className="desk-muted">{c.stale ? `last ${c.updated_at}` : c.updated_at}</td>
  </tr>
);

const TradeTable: React.FC<{ rows: Setup16Trade[]; empty: string; label: string }> = ({ rows, empty, label }) => (
  rows.length === 0 ? <div className="p-4 text-xs desk-muted">{empty}</div> : (
    <div className="overflow-x-auto"><table className="desk-table" aria-label={label}>
      <thead><tr><th scope="col">Contract</th><th scope="col">In</th><th scope="col">Out</th><th scope="col" className="r">Entry</th><th scope="col" className="r">Stop</th><th scope="col" className="r">Price</th><th scope="col" className="r">Lots</th><th scope="col">Status</th><th scope="col" className="r">Net</th></tr></thead>
      <tbody>{rows.map((t) => (
        <tr key={t.id}><td className="desk-sym">{t.strike_symbol}</td><td>{hhmm(t.entry_time)}</td><td>{hhmm(t.exit_time)}</td>
          <td className="r desk-num">{t.entry}</td><td className="r desk-num">{t.stop}</td><td className="r desk-num">{t.price}</td>
          <td className="r desk-num">{t.lots}</td><td>{t.exit_reason ?? t.status}</td>
          <td className={`r desk-num ${tone(t.net_pnl)}`}>{money(t.net_pnl, true)}</td></tr>
      ))}</tbody></table></div>
  )
);

/** The Setup 16 section: switch state, funnel of where each option chart stands, watchlist, entries, results and skips. */
export const Setup16Screen: React.FC<{ initial?: Setup16Overview }> = ({ initial }) => {
  const [o, setO] = useState<Setup16Overview | null>(initial ?? null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/setup16/overview');
      if (res.ok) { setO(await res.json()); setError(false); } else setError(true);
    } catch { setError(true); }
  }, []);

  useEffect(() => {
    if (initial) return undefined;
    void load();
    const id = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(id);
  }, [initial, load]);

  if (!o) return <div className="p-4 text-sm desk-muted">{error ? 'Could not load Setup 16.' : 'Loading Setup 16…'}</div>;
  const near = o.contracts.filter((c) => c.stage !== 'WARMUP' && c.stage !== 'NO_DATA').slice(0, 15);
  const off = o.mode === 'off';
  const st = o.stats_all_time;

  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3" data-testid="setup16-screen">
      <section className="desk-panel shrink-0" aria-labelledby="s16-title">
        <div className="desk-ph">
          <h2 id="s16-title">Setup 16 · Option squeeze breakout</h2>
          <span className={`desk-pill ${off ? 'warn' : 'up'}`}>{MODE_TEXT[o.mode] ?? o.mode}</span>
          <span className="desk-pill">Paper only</span>
          <span className="text-xs desk-muted ml-auto">Updated {o.as_of}</span>
        </div>
        <div className="px-3.5 py-2.5 text-sm flex flex-wrap gap-x-6 gap-y-1">
          <span>Entry window <b className="desk-num">{o.settings.window_start}–{o.settings.window_end}</b></span>
          <span>Max stop distance <b className="desk-num">{o.settings.stop_pct}%</b></span>
          <span>Today <b className={`desk-num ${tone(o.today_net_pnl)}`}>{money(o.today_net_pnl, true)}</b></span>
          <span>Open <b className="desk-num">{o.open_positions.length}</b></span>
          {st && <span>All time <b className="desk-num">{st.trades}</b> trades · win rate <b className="desk-num">{st.win_rate}%</b> · net <b className={`desk-num ${tone(st.net_pnl)}`}>{money(st.net_pnl, true)}</b></span>}
        </div>
        {off && <div className="px-3.5 pb-2.5 text-xs desk-muted">The switch is off, so nothing is entered. Turn it on (index, stocks or all) under Review → Setups. Contracts below are still evaluated.</div>}
      </section>

      <section className="desk-panel shrink-0" aria-label="Where each option chart stands">
        <div className="desk-ph"><h3>Where the option charts stand</h3><span className="desk-pill desk-num">{o.contracts_checked} checked</span></div>
        <FunnelBar funnel={o.funnel} total={o.contracts_checked} />
        {near.length > 0 && (
          <div className="overflow-x-auto"><table className="desk-table" aria-label="Closest to a breakout">
            <thead><tr><th scope="col">Contract</th><th scope="col">Stage</th><th scope="col" className="r">Close</th><th scope="col" className="r">Upper band</th><th scope="col" className="r">Distance</th><th scope="col">Bands</th><th scope="col">Checked</th></tr></thead>
            <tbody>{near.map((c) => <ContractRow key={c.strike_symbol} c={c} />)}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel shrink-0" aria-label="Open positions">
        <div className="desk-ph"><h3>Open positions</h3></div>
        <TradeTable rows={o.open_positions} empty="No open Setup 16 positions." label="Open Setup 16 positions" />
      </section>

      <section className="desk-panel shrink-0" aria-label="Closed today">
        <div className="desk-ph"><h3>Closed today</h3></div>
        <TradeTable rows={o.today_closed} empty="No Setup 16 trades closed today." label="Setup 16 trades closed today" />
      </section>

      <WatchlistPanel initial={o.watchlist} />

      <section className="desk-panel shrink-0" aria-label="Decisions">
        <div className="desk-ph"><h3>Entries and skips (24h)</h3></div>
        {o.decisions.length === 0 ? <div className="p-4 text-xs desk-muted">Nothing recorded for Setup 16 in the last 24 hours.</div> : (
          <div className="overflow-x-auto"><table className="desk-table" aria-label="Setup 16 decisions">
            <thead><tr><th scope="col">Time</th><th scope="col">Stock</th><th scope="col">Side</th><th scope="col">Decision</th><th scope="col">Reason</th></tr></thead>
            <tbody>{o.decisions.map((d, i) => (
              <tr key={`${d.ts}-${i}`}><td>{d.ts.slice(11, 19)}</td><td className="desk-sym">{d.symbol}</td><td>{d.side}</td><td>{d.decision}</td><td>{d.reason}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
    </div>
  );
};
