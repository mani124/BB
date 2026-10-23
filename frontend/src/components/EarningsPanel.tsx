import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { BookFrame } from './BookFrame';
import type { EarningsCalendarRow, EarningsCandidate, EarningsPosition, EarningsSummary } from '../types';

const money = (v: number | null | undefined, plus = false) => {
  if (v === null || v === undefined) return '-';
  const s = Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const tone = (v: number | null | undefined) => ((v ?? 0) > 0 ? 'desk-up' : (v ?? 0) < 0 ? 'desk-down' : '');

const modeLabel = (m: string) => (m === 'MODE_A_RUNUP' ? 'A · Pre-earnings straddle' : m === 'MODE_B_CRUSH' ? 'B · Post-earnings condor' : m);

export interface EarningsInitial {
  summary?: EarningsSummary;
  positions?: EarningsPosition[];
  candidates?: EarningsCandidate[];
  calendar?: EarningsCalendarRow[];
}

export const EarningsPanel: React.FC<{ initial?: EarningsInitial; /** Dock shell passes the accessible dialog; the legacy shell keeps window.confirm. */ confirmFn?: (message: string) => boolean | Promise<boolean> }> = ({ initial, confirmFn = (m) => window.confirm(m) }) => {
  const [summary, setSummary] = useState<EarningsSummary | null>(initial?.summary ?? null);
  const [positions, setPositions] = useState<EarningsPosition[]>(initial?.positions ?? []);
  const [candidates, setCandidates] = useState<EarningsCandidate[]>(initial?.candidates ?? []);
  const [calendar, setCalendar] = useState<EarningsCalendarRow[]>(initial?.calendar ?? []);
  const [form, setForm] = useState({ symbol: '', earnings_date: '', session: 'AMC', sector: '' });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    // Each piece loads on its own: a slow or failing candidates preview must not hide the summary, positions or calendar.
    const pieces: [string, (r: Response) => Promise<void>][] = [
      ['/api/earnings/summary', async (r) => setSummary(await r.json())],
      ['/api/earnings/positions', async (r) => setPositions(await r.json())],
      ['/api/earnings/candidates', async (r) => setCandidates(await r.json())],
      ['/api/earnings/calendar', async (r) => setCalendar(await r.json())],
    ];
    const results = await Promise.allSettled(pieces.map(async ([url, apply]) => {
      const res = await apiFetch(url);
      if (!res.ok) throw new Error(url);
      await apply(res);
    }));
    const failed = results.filter((r) => r.status === 'rejected').length;
    if (failed === pieces.length) setMsg('Could not reach the server.');
    else if (failed > 0) setMsg(`${failed} of ${pieces.length} sections could not be refreshed; showing the rest.`);
  }, []);

  useEffect(() => { if (!initial) void load(); }, [initial, load]);

  const call = async (url: string, init: RequestInit, ok: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await apiFetch(url, init);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Failed (${res.status})`);
      setMsg(ok);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  const addRow = (e: React.FormEvent) => {
    e.preventDefault();
    void call('/api/earnings/calendar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows: [form] }),
    }, `Added ${form.symbol.toUpperCase()}`).then(() => setForm({ ...form, symbol: '', earnings_date: '' }));
  };

  const open = positions.filter((p) => p.status === 'OPEN');
  const closed = positions.filter((p) => p.status === 'CLOSED').slice().reverse();

  const kpis = summary ? [
    { label: 'Equity', value: money(summary.equity) },
    { label: 'Realised', value: money(summary.realized_net_pnl, true), tone: summary.realized_net_pnl > 0 ? 'up' as const : summary.realized_net_pnl < 0 ? 'down' as const : undefined },
    { label: 'Unrealised', value: money(summary.unrealized_net_pnl, true), tone: summary.unrealized_net_pnl > 0 ? 'up' as const : summary.unrealized_net_pnl < 0 ? 'down' as const : undefined },
    { label: 'Closed trades', value: summary.closed_trades },
    { label: 'Win rate', value: `${summary.win_rate}%` },
    { label: 'Profit factor', value: summary.profit_factor ?? 'n/a' },
    { label: 'Charges', value: money(summary.total_charges) },
    { label: 'Last check', value: summary.last_cycle?.status ?? 'never' },
  ] : [];
  return (
    <BookFrame
      idPrefix="earn"
      testId="earnings-panel"
      kpiTestId="earnings-summary"
      title="Stock earnings options"
      pills={[{ text: summary?.enabled ? 'Entries enabled' : 'Entries off (Settings)', tone: summary?.enabled ? 'up' : 'warn' }, { text: 'Paper only', tone: 'mute' }]}
      notice={msg ? { tone: 'mute', text: msg } : null}
      actions={<>
        <button type="button" className="desk-btn accent" disabled={busy} onClick={() => call('/api/earnings/run-cycle', { method: 'POST' }, 'Cycle run')}>Run check now</button>
        <button type="button" className="desk-btn danger" disabled={busy || open.length === 0}
          onClick={async () => { if (await confirmFn('Close all open earnings paper positions now?')) void call('/api/earnings/square-off', { method: 'POST' }, 'Positions closed'); }}>
          Square off
        </button>
      </>}
      kpis={kpis}
      tabs={[
        { id: 'positions', label: 'Positions', count: open.length, content: <>
      <section className="desk-panel" aria-label="Open positions">
        <div className="desk-ph"><h3>Open positions</h3></div>
        {open.length === 0 ? <div className="p-4 text-xs desk-muted">No open earnings positions.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Mode</th><th scope="col">Earnings</th><th scope="col">Exit by</th><th scope="col">Expiry</th><th scope="col" className="r">Lots</th><th scope="col" className="r">Max risk</th><th scope="col" className="r">Spot</th><th scope="col" className="r">Unrealised</th><th scope="col" className="r">MFE / MAE</th></tr></thead>
            <tbody>{open.map((p) => (
              <tr key={p.id}><td className="desk-sym">{p.symbol}</td><td>{modeLabel(p.mode)}</td><td>{p.earnings_date} {p.session}</td><td>{p.exit_date}</td><td>{p.expiry}</td>
                <td className="r desk-num">{p.lots}</td><td className="r desk-num">{money(p.max_risk)}</td>
                <td className="r desk-num">{p.spot_current}</td><td className={`r desk-num ${tone(p.unrealized_net)}`}>{money(p.unrealized_net, true)}</td>
                <td className="r desk-num">{money(p.mfe)} / {money(p.mae)}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel" aria-label="Closed positions">
        <div className="desk-ph"><h3>Closed trades</h3></div>
        {closed.length === 0 ? <div className="p-4 text-xs desk-muted">No closed earnings trades yet.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Mode</th><th scope="col">Closed</th><th scope="col">Reason</th><th scope="col" className="r">Charges</th><th scope="col" className="r">Net</th></tr></thead>
            <tbody>{closed.map((p) => (
              <tr key={p.id}><td className="desk-sym">{p.symbol}</td><td>{modeLabel(p.mode)}</td><td>{p.closed_at}</td><td><span className="desk-code">{p.exit_reason}</span></td>
                <td className="r desk-num">{money(p.charges)}</td><td className={`r desk-num ${tone(p.net_pnl)}`}>{money(p.net_pnl, true)}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
        </> },
        { id: 'signals', label: 'Signals now', count: candidates.length || undefined, content: <>
      <section className="desk-panel" aria-label="Signals now">
        <div className="desk-ph"><h3>What the engine sees now</h3><span className="desk-muted text-xs">Needs a connected Dhan session. Nothing is opened from here.</span></div>
        {candidates.length === 0 ? <div className="p-4 text-xs desk-muted">No calendar rows are due today.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Mode</th><th scope="col">Status</th><th scope="col">Why</th><th scope="col">Expiry</th><th scope="col">Exit by</th><th scope="col" className="r">Net / unit</th><th scope="col" className="r">Max risk</th></tr></thead>
            <tbody>{candidates.map((c, i) => (
              <tr key={`${c.symbol}-${c.mode}-${i}`}><td className="desk-sym">{c.symbol}</td><td>{modeLabel(c.mode)}</td>
                <td><span className={`desk-pill ${c.ready ? 'up' : 'warn'}`}>{c.ready ? 'READY' : c.code}</span></td>
                <td className="desk-muted text-xs" style={{ whiteSpace: 'normal' }}>{c.detail}</td>
                <td>{c.expiry ?? ''}</td><td>{c.exit_date ?? ''}</td>
                <td className="r desk-num">{c.net_unit ?? ''}</td><td className="r desk-num">{c.max_risk != null ? money(c.max_risk) : ''}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
        </> },
        { id: 'calendar', label: 'Calendar', count: calendar.length || undefined, content: <>
      <section className="desk-panel" aria-label="Earnings calendar">
        <div className="desk-ph"><h3>Earnings calendar</h3><span className="desk-muted text-xs">Filled daily from NSE (F&O stocks with a financial-results board meeting). NSE gives no before/after flag, so the session is inferred from its event text when possible, else the default in Settings (AMC) applies. Choosing BMO or AMC on a row overrides both.</span>
          <button type="button" className="desk-btn accent ml-auto" disabled={busy} onClick={() => call('/api/earnings/calendar/sync', { method: 'POST' }, 'Calendar updated from NSE')}>Sync from NSE</button></div>
        <form className="px-3.5 py-3 flex flex-wrap gap-2 items-end" onSubmit={addRow}>
          <label className="text-xs">Symbol<input className="desk-input" required value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} aria-label="Symbol" /></label>
          <label className="text-xs">Date<input className="desk-input" type="date" required value={form.earnings_date} onChange={(e) => setForm({ ...form, earnings_date: e.target.value })} aria-label="Earnings date" /></label>
          <label className="text-xs">Session
            <select className="desk-input" value={form.session} onChange={(e) => setForm({ ...form, session: e.target.value })} aria-label="Session">
              <option value="AMC">AMC</option><option value="BMO">BMO</option><option value="">Unknown</option>
            </select></label>
          <label className="text-xs">Sector<input className="desk-input" value={form.sector} onChange={(e) => setForm({ ...form, sector: e.target.value })} aria-label="Sector" /></label>
          <button type="submit" className="desk-btn solid" disabled={busy}>Add</button>
        </form>
        {calendar.length > 0 && (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Date</th><th scope="col">Session</th><th scope="col">Sector</th><th scope="col">Source</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{calendar.map((r) => (
              <tr key={`${r.symbol}-${r.earnings_date}`}><td className="desk-sym">{r.symbol}</td><td>{r.earnings_date}</td><td>
                <select className="desk-input" aria-label={`Session for ${r.symbol}`} value={r.session} disabled={busy}
                  onChange={(e) => call('/api/earnings/calendar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rows: [{ ...r, session: e.target.value }] }) }, `Session set for ${r.symbol}`)}>
                  <option value="">{r.session_origin === 'skip' ? 'Not set (skipped)' : `Auto${r.effective_session ? ` (${r.effective_session})` : ''}`}</option><option value="BMO">BMO</option><option value="AMC">AMC</option>
                </select> <span className="desk-muted text-xs" data-testid={`origin-${r.symbol}`}>{r.session_origin ?? ''}</span></td><td>{r.sector}</td><td className="desk-muted text-xs">{r.source ?? 'manual'}</td>
                <td className="r"><button type="button" className="desk-btn" aria-label={`Remove ${r.symbol}`} disabled={busy}
                  onClick={() => call(`/api/earnings/calendar/${r.symbol}/${r.earnings_date}`, { method: 'DELETE' }, `Removed ${r.symbol}`)}>Remove</button></td></tr>
            ))}</tbody></table></div>
        )}
      </section>
        </> },
      ]}
    />
  );
};
