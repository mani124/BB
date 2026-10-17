import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import type { EarningsCalendarRow, EarningsCandidate, EarningsPosition, EarningsSummary } from '../types';

const money = (v: number | null | undefined, plus = false) => {
  if (v === null || v === undefined) return '-';
  const s = Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const tone = (v: number | null | undefined) => ((v ?? 0) > 0 ? 'desk-pos' : (v ?? 0) < 0 ? 'desk-neg' : '');
const modeLabel = (m: string) => (m === 'MODE_A_RUNUP' ? 'A · Pre-earnings straddle' : m === 'MODE_B_CRUSH' ? 'B · Post-earnings condor' : m);

export interface EarningsInitial {
  summary?: EarningsSummary;
  positions?: EarningsPosition[];
  candidates?: EarningsCandidate[];
  calendar?: EarningsCalendarRow[];
}

export const EarningsPanel: React.FC<{ initial?: EarningsInitial }> = ({ initial }) => {
  const [summary, setSummary] = useState<EarningsSummary | null>(initial?.summary ?? null);
  const [positions, setPositions] = useState<EarningsPosition[]>(initial?.positions ?? []);
  const [candidates, setCandidates] = useState<EarningsCandidate[]>(initial?.candidates ?? []);
  const [calendar, setCalendar] = useState<EarningsCalendarRow[]>(initial?.calendar ?? []);
  const [form, setForm] = useState({ symbol: '', earnings_date: '', session: 'AMC', sector: '' });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, p, c, cal] = await Promise.all([
        apiFetch('/api/earnings/summary'), apiFetch('/api/earnings/positions'),
        apiFetch('/api/earnings/candidates'), apiFetch('/api/earnings/calendar'),
      ]);
      if (s.ok) setSummary(await s.json());
      if (p.ok) setPositions(await p.json());
      if (c.ok) setCandidates(await c.json());
      if (cal.ok) setCalendar(await cal.json());
    } catch {
      setMsg('Could not reach the server.');
    }
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

  return (
    <div className="flex flex-col gap-3" data-testid="earnings-panel">
      <div className="desk-panel">
        <div className="desk-ph">
          <h2>Stock earnings options</h2>
          <span className={`desk-pill ${summary?.enabled ? 'up' : 'warn'}`}>{summary?.enabled ? 'Entries enabled' : 'Entries off (Settings)'}</span>
          <span className="desk-pill">Paper only</span>
          <div className="ml-auto flex gap-2">
            <button type="button" className="desk-btn accent" disabled={busy} onClick={() => call('/api/earnings/run-cycle', { method: 'POST' }, 'Cycle run')}>Run check now</button>
            <button type="button" className="desk-btn danger" disabled={busy || open.length === 0}
              onClick={() => { if (window.confirm('Close all open earnings paper positions now?')) void call('/api/earnings/square-off', { method: 'POST' }, 'Positions closed'); }}>
              Square off
            </button>
          </div>
        </div>
        {msg && <div className="px-3.5 py-2 text-xs desk-muted" role="status">{msg}</div>}
        {summary && (
          <div className="px-3.5 py-2.5 text-xs flex flex-wrap gap-x-6 gap-y-1" data-testid="earnings-summary">
            <span>Equity <b className="desk-num">{money(summary.equity)}</b></span>
            <span>Realised <b className={`desk-num ${tone(summary.realized_net_pnl)}`}>{money(summary.realized_net_pnl, true)}</b></span>
            <span>Unrealised <b className={`desk-num ${tone(summary.unrealized_net_pnl)}`}>{money(summary.unrealized_net_pnl, true)}</b></span>
            <span>Closed <b className="desk-num">{summary.closed_trades}</b></span>
            <span>Win rate <b className="desk-num">{summary.win_rate}%</b></span>
            <span>Profit factor <b className="desk-num">{summary.profit_factor ?? '-'}</b></span>
            <span>Charges <b className="desk-num">{money(summary.total_charges)}</b></span>
            <span className="desk-muted">Last check: {summary.last_cycle?.status ?? 'never'}</span>
          </div>
        )}
      </div>

      <section className="desk-panel" aria-label="Open positions">
        <div className="desk-ph"><h3>Open positions</h3></div>
        {open.length === 0 ? <div className="p-4 text-xs desk-muted">No open earnings positions.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th>Symbol</th><th>Mode</th><th>Earnings</th><th>Exit by</th><th>Expiry</th><th className="r">Lots</th><th className="r">Max risk</th><th className="r">Spot</th><th className="r">Unrealised</th><th className="r">MFE / MAE</th></tr></thead>
            <tbody>{open.map((p) => (
              <tr key={p.id}><td className="desk-sym">{p.symbol}</td><td>{modeLabel(p.mode)}</td><td>{p.earnings_date} {p.session}</td><td>{p.exit_date}</td><td>{p.expiry}</td>
                <td className="r desk-num">{p.lots}</td><td className="r desk-num">{money(p.max_risk)}</td>
                <td className="r desk-num">{p.spot_current}</td><td className={`r desk-num ${tone(p.unrealized_net)}`}>{money(p.unrealized_net, true)}</td>
                <td className="r desk-num">{money(p.mfe)} / {money(p.mae)}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel" aria-label="Signals now">
        <div className="desk-ph"><h3>What the engine sees now</h3><span className="desk-muted text-xs">Needs a connected Dhan session. Nothing is opened from here.</span></div>
        {candidates.length === 0 ? <div className="p-4 text-xs desk-muted">No calendar rows are due today.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th>Symbol</th><th>Mode</th><th>Status</th><th>Why</th><th>Expiry</th><th>Exit by</th><th className="r">Net / unit</th><th className="r">Max risk</th></tr></thead>
            <tbody>{candidates.map((c, i) => (
              <tr key={`${c.symbol}-${c.mode}-${i}`}><td className="desk-sym">{c.symbol}</td><td>{modeLabel(c.mode)}</td>
                <td><span className={`desk-pill ${c.ready ? 'up' : 'warn'}`}>{c.ready ? 'READY' : c.code}</span></td>
                <td className="desk-muted text-xs" style={{ whiteSpace: 'normal' }}>{c.detail}</td>
                <td>{c.expiry ?? ''}</td><td>{c.exit_date ?? ''}</td>
                <td className="r desk-num">{c.net_unit ?? ''}</td><td className="r desk-num">{c.max_risk != null ? money(c.max_risk) : ''}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel" aria-label="Earnings calendar">
        <div className="desk-ph"><h3>Earnings calendar</h3><span className="desk-muted text-xs">Maintained here. Session: BMO = before open, AMC = after close.</span></div>
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
            <thead><tr><th>Symbol</th><th>Date</th><th>Session</th><th>Sector</th><th /></tr></thead>
            <tbody>{calendar.map((r) => (
              <tr key={`${r.symbol}-${r.earnings_date}`}><td className="desk-sym">{r.symbol}</td><td>{r.earnings_date}</td><td>{r.session || 'unknown'}</td><td>{r.sector}</td>
                <td className="r"><button type="button" className="desk-btn" aria-label={`Remove ${r.symbol}`} disabled={busy}
                  onClick={() => call(`/api/earnings/calendar/${r.symbol}/${r.earnings_date}`, { method: 'DELETE' }, `Removed ${r.symbol}`)}>Remove</button></td></tr>
            ))}</tbody></table></div>
        )}
      </section>

      <section className="desk-panel" aria-label="Closed positions">
        <div className="desk-ph"><h3>Closed trades</h3></div>
        {closed.length === 0 ? <div className="p-4 text-xs desk-muted">No closed earnings trades yet.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th>Symbol</th><th>Mode</th><th>Closed</th><th>Reason</th><th className="r">Charges</th><th className="r">Net</th></tr></thead>
            <tbody>{closed.map((p) => (
              <tr key={p.id}><td className="desk-sym">{p.symbol}</td><td>{modeLabel(p.mode)}</td><td>{p.closed_at}</td><td><span className="desk-code">{p.exit_reason}</span></td>
                <td className="r desk-num">{money(p.charges)}</td><td className={`r desk-num ${tone(p.net_pnl)}`}>{money(p.net_pnl, true)}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
    </div>
  );
};
