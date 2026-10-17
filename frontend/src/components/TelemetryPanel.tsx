import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import type { DecisionRow, ErrorRow, PerfBucket, PerformanceReport, TelemetryInsights } from '../types';

const money = (v: number | null | undefined, plus = false) => {
  if (v === null || v === undefined) return '-';
  const s = Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const num = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? '-' : v.toFixed(d));
const tone = (v: number | null | undefined) => ((v ?? 0) > 0 ? 'desk-pos' : (v ?? 0) < 0 ? 'desk-neg' : '');

type View = 'performance' | 'decisions' | 'excursions' | 'errors';
const VIEWS: { id: View; label: string }[] = [
  { id: 'performance', label: 'Performance' },
  { id: 'decisions', label: 'Decision trail' },
  { id: 'excursions', label: 'MFE / MAE' },
  { id: 'errors', label: 'Errors' },
];
const WINDOWS = [{ h: 24, l: '24h' }, { h: 72, l: '3d' }, { h: 168, l: '7d' }, { h: 720, l: '30d' }];

export interface TelemetryInitial {
  performance?: PerformanceReport;
  insights?: TelemetryInsights;
  decisions?: DecisionRow[];
  errors?: ErrorRow[];
}

function useJson<T>(url: string, initial?: T, key = 0): { data: T | null; failed: boolean } {
  const [data, setData] = useState<T | null>(initial ?? null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (initial !== undefined) return;
    let cancelled = false;
    apiFetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: T) => { if (!cancelled) { setData(d); setFailed(false); } })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [url, initial, key]);
  return { data, failed };
}

const PerfTable: React.FC<{ title: string; rows: PerfBucket[] }> = ({ title, rows }) => (
  <section className="desk-panel" aria-label={title}>
    <div className="desk-ph"><h3>{title}</h3></div>
    <div className="overflow-x-auto">
      <table className="desk-table">
        <thead><tr>
          <th scope="col">{title.replace('By ', '')}</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Win %</th><th scope="col" className="r">Net</th>
          <th scope="col" className="r">Expectancy</th><th scope="col" className="r">PF</th><th scope="col" className="r">Avg R</th><th scope="col" className="r">Max DD</th>
          <th scope="col" className="r">Avg MFE</th><th scope="col" className="r">Avg MAE</th><th scope="col" className="r">Capture</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.key}</td><td className="r desk-num">{r.trades}</td><td className="r desk-num">{num(r.win_rate, 1)}</td>
              <td className={`r desk-num ${tone(r.net_pnl)}`}>{money(r.net_pnl, true)}</td>
              <td className={`r desk-num ${tone(r.expectancy)}`}>{money(r.expectancy, true)}</td>
              <td className="r desk-num">{num(r.profit_factor)}</td><td className="r desk-num">{num(r.avg_r)}</td>
              <td className="r desk-num">{money(r.max_drawdown)}</td>
              <td className="r desk-num">{money(r.avg_mfe)}</td><td className="r desk-num">{money(r.avg_mae)}</td>
              <td className="r desk-num">{r.avg_capture_pct == null ? '-' : `${r.avg_capture_pct}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </section>
);

export const TelemetryPanel: React.FC<{ initial?: TelemetryInitial }> = ({ initial }) => {
  const [view, setView] = useState<View>('performance');
  const [hours, setHours] = useState(24);
  const perf = useJson<PerformanceReport>('/api/telemetry/performance?mode=all', initial?.performance);
  const ins = useJson<TelemetryInsights>(`/api/telemetry/insights?hours=${hours}`, initial?.insights, hours);
  const dec = useJson<DecisionRow[]>(`/api/telemetry/decisions?hours=${hours}&limit=300`, initial?.decisions, hours);
  const errs = useJson<ErrorRow[]>(`/api/telemetry/errors?hours=${hours}&limit=300`, initial?.errors, hours);
  const [decisionFilter, setDecisionFilter] = useState<string>('ALL');
  const [openErr, setOpenErr] = useState<number | null>(null);

  const o = perf.data?.overall;
  return (
    <div className="flex flex-col gap-3" data-testid="telemetry-panel">
      <div className="desk-panel">
        <div className="desk-ph">
          <h2>Analytics</h2>
          <div className="desk-seg" role="group" aria-label="Analytics view">
            {VIEWS.map((v) => <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>)}
          </div>
          {view !== 'performance' && (
            <div className="desk-seg ml-auto" role="group" aria-label="Time window">
              {WINDOWS.map((w) => <button key={w.h} type="button" aria-pressed={hours === w.h} onClick={() => setHours(w.h)}>{w.l}</button>)}
            </div>
          )}
        </div>
      </div>

      {view === 'performance' && (
        <>
          {!perf.data && <div className="desk-panel p-6 text-center text-xs desk-muted">{perf.failed ? 'Could not load performance.' : 'Loading performance...'}</div>}
          {o && o.trades === 0 && <div className="desk-panel p-6 text-center text-xs desk-muted">Statistics appear after the first closed trade.</div>}
          {o && o.trades > 0 && perf.data && (
            <>
              <div className="desk-panel px-3.5 py-2.5 text-xs flex flex-wrap gap-x-6 gap-y-1" data-testid="perf-summary">
                <span>Trades <b className="desk-num">{o.trades}</b></span>
                <span>Win rate <b className="desk-num">{num(o.win_rate, 1)}%</b></span>
                <span>Net <b className={`desk-num ${tone(o.net_pnl)}`}>{money(o.net_pnl, true)}</b></span>
                <span>Expectancy <b className={`desk-num ${tone(o.expectancy)}`}>{money(o.expectancy, true)}</b> per trade</span>
                <span>Profit factor <b className="desk-num">{num(o.profit_factor)}</b></span>
                <span>Avg R <b className="desk-num">{num(o.avg_r)}</b></span>
                <span>Max drawdown <b className="desk-num">{money(o.max_drawdown)}</b></span>
                <span>Longest loss streak <b className="desk-num">{o.max_consecutive_losses}</b></span>
                <span>Slippage <b className="desk-num">{money(o.slippage_cost)}</b></span>
                <span>Charges <b className="desk-num">{money(o.charges)}</b></span>
                {o.avg_capture_pct != null && <span>Keeps <b className="desk-num">{o.avg_capture_pct}%</b> of the best open profit on winners</span>}
                {(o.losers_that_were_green ?? 0) > 0 && <span className="desk-muted">{o.losers_that_were_green} losing trades were in profit first</span>}
              </div>
              <PerfTable title="By setup" rows={perf.data.by_setup} />
              <PerfTable title="By symbol" rows={perf.data.by_symbol} />
              <PerfTable title="By entry hour" rows={perf.data.by_entry_hour} />
              <PerfTable title="By exit reason" rows={perf.data.by_exit_reason} />
            </>
          )}
        </>
      )}

      {view === 'decisions' && (
        <>
          {ins.data && (
            <div className="desk-panel px-3.5 py-2.5 text-xs flex flex-wrap gap-x-6 gap-y-2" data-testid="decision-summary">
              <span>Entered <b className="desk-num">{ins.data.decisions.ENTERED}</b></span>
              <span>Skipped <b className="desk-num">{ins.data.decisions.SKIPPED}</b></span>
              <span>Exited <b className="desk-num">{ins.data.decisions.EXITED}</b></span>
              <span className="flex flex-wrap gap-1.5 items-center">
                <span className="desk-muted">Top skip reasons</span>
                {ins.data.top_skip_reasons.slice(0, 8).map((r) => (
                  <span key={`${r.reason}-${r.strategy}`} className="desk-pill warn" title={r.strategy}>{r.reason} · {r.n}</span>
                ))}
                {ins.data.top_skip_reasons.length === 0 && <span className="desk-muted">none</span>}
              </span>
            </div>
          )}
          <section className="desk-panel" aria-label="Decision trail">
            <div className="desk-ph">
              <h3>Decision trail</h3>
              <div className="desk-seg" role="group" aria-label="Decision filter">
                {['ALL', 'ENTERED', 'SKIPPED', 'EXITED', 'HELD'].map((d) => (
                  <button key={d} type="button" aria-pressed={decisionFilter === d} onClick={() => setDecisionFilter(d)}>{d}</button>
                ))}
              </div>
            </div>
            {!dec.data ? <div className="p-6 text-center text-xs desk-muted">{dec.failed ? 'Could not load decisions.' : 'Loading...'}</div> : (
              <div className="overflow-x-auto">
                <table className="desk-table">
                  <thead><tr><th scope="col">Time</th><th scope="col">Book</th><th scope="col">Strategy</th><th scope="col">Symbol</th><th scope="col">Decision</th><th scope="col">Reason</th><th scope="col">Detail</th></tr></thead>
                  <tbody>
                    {dec.data.filter((d) => decisionFilter === 'ALL' || d.decision === decisionFilter).map((d) => (
                      <tr key={d.id}>
                        <td className="desk-num">{d.ts}</td><td>{d.book}</td><td>{d.strategy}</td>
                        <td>{d.symbol} {d.side && <span className={`desk-side ${d.side.toLowerCase()}`}>{d.side}</span>}</td>
                        <td>{d.decision}</td><td><span className="desk-code">{d.reason}</span></td>
                        <td className="desk-muted text-xs" style={{ whiteSpace: 'normal', maxWidth: 360 }}>
                          {String((d.metrics as Record<string, unknown>).detail ?? '')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {view === 'excursions' && (
        <section className="desk-panel" aria-label="Excursions">
          <div className="desk-ph"><h3>How far trades run for and against us</h3></div>
          {!ins.data ? <div className="p-6 text-center text-xs desk-muted">Loading...</div> : ins.data.excursions.length === 0 ? (
            <div className="p-6 text-center text-xs desk-muted">MFE / MAE appear after trades close.</div>
          ) : (
            <table className="desk-table">
              <thead><tr><th scope="col">Strategy</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Avg MFE (best open profit)</th><th scope="col" className="r">Avg MAE (worst open loss)</th><th scope="col" className="r">Avg final</th></tr></thead>
              <tbody>
                {ins.data.excursions.map((e) => (
                  <tr key={e.strategy}><td>{e.strategy}</td><td className="r desk-num">{e.trades}</td>
                    <td className="r desk-num desk-pos">{money(e.avg_mfe)}</td><td className="r desk-num desk-neg">{money(e.avg_mae)}</td>
                    <td className={`r desk-num ${tone(e.avg_final)}`}>{money(e.avg_final, true)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {view === 'errors' && (
        <section className="desk-panel" aria-label="Errors">
          <div className="desk-ph"><h3>Errors and warnings</h3></div>
          {ins.data && ins.data.errors.length > 0 && (
            <div className="px-3.5 py-2 flex flex-wrap gap-1.5">
              {ins.data.errors.map((e) => <span key={`${e.code}-${e.component}`} className={`desk-pill ${e.severity === 'WARNING' ? 'warn' : 'down'}`}>{e.code} · {e.n}</span>)}
            </div>
          )}
          {!errs.data ? <div className="p-6 text-center text-xs desk-muted">{errs.failed ? 'Could not load errors.' : 'Loading...'}</div> : errs.data.length === 0 ? (
            <div className="p-6 text-center text-xs desk-muted">No errors in this window.</div>
          ) : (
            <table className="desk-table">
              <thead><tr><th scope="col">Time</th><th scope="col">Code</th><th scope="col">Component</th><th scope="col">Message</th></tr></thead>
              <tbody>
                {errs.data.map((e) => (
                  <React.Fragment key={e.id}>
                    <tr onClick={() => setOpenErr(openErr === e.id ? null : e.id)} style={{ cursor: e.stack ? 'pointer' : 'default' }}>
                      <td className="desk-num">{e.ts}</td><td><span className="desk-code">{e.code}</span></td><td>{e.component}</td>
                      <td style={{ whiteSpace: 'normal' }}>{e.message}</td>
                    </tr>
                    {openErr === e.id && e.stack && <tr><td colSpan={4}><pre className="text-xs desk-muted overflow-x-auto">{e.stack}</pre></td></tr>}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
};
