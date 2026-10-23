import React from 'react';
import { useApp } from '../../data/appStore';
import { useApiData } from '../../data/hooks/useApiData';
import { entriesAllowed, entryReasons, lossCapUsage } from '../../features/risk/entryState';
import type { RiskReport } from '../../features/analytics/types';
import { marketSession } from '../../lib/time';
import { inr, pct, points } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { AsyncStrip, Computed, Kpi } from '../kit';

const RiskPanel: React.FC<PanelProps> = () => {
  const portfolio = useApp((s) => s.scanner.paper_portfolio);
  const stream = useApp((s) => s.stream.state);
  const api = useApiData<RiskReport>('/api/analytics/risk?book=paper', { refreshMs: 15_000 });
  const risk = portfolio?.risk;
  const rep = api.data;
  const reasons = entryReasons({
    risk, autoTrade: portfolio?.auto_trade_enabled, openCount: rep?.totals.count ?? portfolio?.active_positions?.length ?? 0,
    maxOpen: rep?.totals.max_open, session: marketSession(), stream,
  });
  const allowed = entriesAllowed(reasons);
  const usage = lossCapUsage(risk);
  const capOff = !risk || !risk.daily_loss_limit;

  return (
    <PanelFrame title="Risk overview" sources={['portfolio']} onRetry={api.reload}>
      <AsyncStrip state={api} onRetry={api.reload} what="open risk" />
      <div className="flex flex-wrap items-stretch gap-x-4" style={{ borderBottom: '1px solid var(--line)' }}>
        <div className="px-2 py-1 min-w-[12rem] flex-1">
          <div className="text-xs desk-muted" id="risk-cap-label">Day P&L against the loss cap</div>
          <div className="desk-num text-base font-semibold" title="portfolio.risk.day_pnl">{risk ? inr(risk.day_pnl, { sign: true }) : '—'}{capOff ? <span className="desk-muted text-xs font-normal"> · Loss cap off</span> : <span className="desk-muted text-xs font-normal"> of {inr(-risk!.daily_loss_limit)} cap</span>}</div>
          {!capOff && usage !== null && (
            <div role="meter" aria-labelledby="risk-cap-label" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(usage * 100)} aria-valuetext={`${Math.round(usage * 100)} percent of the loss cap used`} className="desk-bar mt-1">
              <i style={{ width: `${usage * 100}%`, background: usage >= 0.8 ? 'var(--down)' : usage >= 0.5 ? 'var(--warn)' : undefined }} />
            </div>
          )}
          {!capOff && usage !== null && <div className="text-xs desk-muted">{pct(usage * 100, 0)} used</div>}
        </div>
        <div className="px-2 py-1 min-w-[12rem] flex-1">
          <div className="text-xs desk-muted">New entries</div>
          <div className="mb-1"><span className={`desk-pill ${allowed ? 'up' : 'down'}`}>{allowed ? 'Allowed' : 'Blocked'}</span></div>
          {reasons.length > 0 ? (
            <ol className="text-xs list-decimal pl-4" aria-label="Reasons, most important first">
              {reasons.map((r) => <li key={r.code} data-reason={r.code}>{r.text}</li>)}
            </ol>
          ) : <p className="text-xs desk-muted">No restrictions.</p>}
        </div>
        <Kpi label="Open risk at stops" value={rep ? inr(rep.totals.risk_rupees) : '—'} hint="Sum of quantity × (entry − stop) over open positions" />
        <Kpi label={`Open positions${rep?.totals.max_open_key ? ` (max: ${rep.totals.max_open_key})` : ''}`} value={rep ? `${rep.totals.count}${rep.totals.max_open ? ` of ${rep.totals.max_open}` : ''}` : '—'} />
      </div>
      {rep && rep.open.length === 0 ? (
        <p className="p-6 text-center text-sm desk-muted">No open positions.{allowed ? ' Entries are Allowed.' : ''}</p>
      ) : rep ? (
        <div className="overflow-x-auto" tabIndex={0} role="group" aria-label="Open position risk, scrollable">
          <table className="desk-table" aria-label="Open position risk">
            <thead><tr>
              <th scope="col">Instrument</th><th scope="col">Setup</th><th scope="col">Pool</th><th scope="col" className="r">Qty</th><th scope="col" className="r">Entry</th>
              <th scope="col" className="r">Stop</th><th scope="col" className="r">Risk ₹</th><th scope="col" className="r">To stop</th><th scope="col" className="r">T1</th>
            </tr></thead>
            <tbody>
              {rep.open.map((r) => (
                <tr key={r.id}>
                  <td><span className="desk-sym">{r.strike_symbol}</span></td><td>{r.setup}</td><td>{r.pool}</td>
                  <td className="r desk-num">{r.qty}</td><td className="r desk-num">{points(r.entry, 1)}</td><td className="r desk-num">{points(r.stop, 1)}</td>
                  <td className="r desk-num" title="risk_rupees = qty × (entry − stop)">{inr(r.risk_rupees)}</td>
                  <td className="r desk-num" title="Distance from last price to stop">{pct(r.distance_pct, 1)}</td><td className="r desk-num">{points(r.t1, 1)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><th scope="row" colSpan={6}>Total</th><td className="r desk-num font-semibold">{inr(rep.totals.risk_rupees)}</td><td colSpan={2} /></tr></tfoot>
          </table>
        </div>
      ) : null}
      <Computed at={rep?.generated_at} />
    </PanelFrame>
  );
};

export default RiskPanel;
