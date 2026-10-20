import React from 'react';
import type { DashboardChart, DashboardTrade, DashboardTradeDetail } from '../types/dashboard';
import { TradeChart } from './TradeChart';

interface Props {
  trade: DashboardTrade;
  detail: DashboardTradeDetail | null;
  chart: DashboardChart | null;
  loading: boolean;
  onClose: () => void;
  closing: boolean;
  actionError: string | null;
}

const fmt = (value: string | null) => value
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST'
  : 'Time not recorded';

const reasonText = (decision: Record<string, unknown>): string => {
  const rationale = decision.rationale;
  if (typeof rationale === 'string' && rationale.trim()) return rationale;
  if (rationale && typeof rationale === 'object' && !Array.isArray(rationale)) {
    const signal = rationale as Record<string, unknown>;
    const parts = [signal.setup, signal.side, signal.symbol].filter((part) => typeof part === 'string' && part);
    if (parts.length) return parts.join(' · ');
  }
  return typeof decision.reason === 'string' ? decision.reason : 'Decision recorded without a written rationale';
};

export const TradeDetail: React.FC<Props> = ({ trade, detail, chart, loading, onClose, closing, actionError }) => {
  const decision = detail?.decision;
  const checks = decision?.checks && typeof decision.checks === 'object' && !Array.isArray(decision.checks)
    ? Object.entries(decision.checks) : [];
  const legs = Array.isArray(decision?.legs) ? decision.legs as Record<string, unknown>[] : [];
  const signal = decision?.rationale && typeof decision.rationale === 'object' && !Array.isArray(decision.rationale)
    ? decision.rationale as Record<string, unknown> : null;
  return (
    <article className="min-w-0 flex flex-col gap-3" aria-label="Selected trade">
      <section className="desk-panel p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="desk-label">{trade.display_book} · {trade.mode}</p>
            <h2 className="text-xl font-semibold mt-0.5">{trade.instrument}</h2>
            <p className="text-sm desk-muted">{trade.setup} · {trade.status.replaceAll('_', ' ')}</p>
          </div>
          {(trade.status === 'OPEN' || trade.status === 'TARGET_1') && trade.book === 'paper' && (
            <button type="button" className="desk-btn danger fill" disabled={closing} onClick={onClose}>{closing ? 'Closing…' : 'Close position'}</button>
          )}
        </div>
        <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-4 mt-5 text-base">
          <div><dt className="desk-label">{trade.net_kind === 'estimated' ? 'Estimated net' : 'Realized net'}</dt>
            <dd className={`desk-hero lg ${trade.net_pnl == null ? 'desk-muted' : trade.net_pnl < 0 ? 'desk-down' : 'desk-up'}`}>{trade.net_pnl == null ? 'Not recorded' : `${trade.net_pnl < 0 ? '-' : '+'}₹${Math.abs(trade.net_pnl).toLocaleString('en-IN')}`}</dd></div>
          <div><dt className="desk-label">Opened</dt><dd className="desk-num">{fmt(trade.opened_at)}</dd></div>
          {trade.closed_at && <div><dt className="desk-label">Closed</dt><dd className="desk-num">{fmt(trade.closed_at)}</dd></div>}
          {trade.exit_reason && <div><dt className="desk-label">Exit reason</dt><dd>{trade.exit_reason}</dd></div>}
          {trade.quarantine_reason && <div><dt className="desk-label">Data quality</dt><dd>Excluded from financial totals: {trade.quarantine_reason}</dd></div>}
        </dl>
        {legs.length > 0 && <div className="mt-4">
          <h3 className="font-semibold text-sm mb-2">Opened legs</h3>
          <ul className="flex flex-wrap gap-2">{legs.map((leg, index) => (
            <li key={`${String(leg.security_id || index)}`} className="desk-pill">
              {String(leg.side || '')} {String(leg.opt || '')} {String(leg.strike || '')}
            </li>
          ))}</ul>
        </div>}
        {trade.status === 'OPEN' && trade.book !== 'paper' && <p className="desk-muted text-xs mt-3">This book has no single-position close action. Its existing controls remain in Control.</p>}
        {actionError && <p role="alert" className="desk-down mt-3 text-sm">{actionError}</p>}
      </section>

      <section className="desk-panel p-4 sm:p-5">
        <h3 className="font-semibold text-base mb-2">Why it opened</h3>
        {loading ? <p className="desk-muted text-sm">Loading recorded decision…</p>
          : detail?.reason_state === 'recorded' && decision ? (
            <>
              <p className="text-base">{reasonText(decision)}</p>
              {decision.reason && decision.rationale && <p className="desk-muted text-xs mt-1">Decision code: {String(decision.reason)}</p>}
              {signal && <dl className="grid sm:grid-cols-3 gap-2 mt-3 text-sm">
                {(['bar_time', 'price', 'invalidate_level'] as const).filter((key) => signal[key] != null).map((key) =>
                  <div key={key}><dt className="desk-label">{key.replaceAll('_', ' ')}</dt><dd className="desk-num">{String(signal[key])}</dd></div>)}
              </dl>}
              <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4 text-sm">
                {(['entry', 'stop', 'target_1', 'target_2', 'lots'] as const).filter((key) => decision[key] != null).map((key) => (
                  <div key={key} className="p-3 rounded-lg" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
                    <dt className="desk-label">{key.replaceAll('_', ' ')}</dt><dd className="desk-num text-base font-semibold">{String(decision[key])}</dd>
                  </div>
                ))}
              </dl>
              {checks.length > 0 && <>
                <h4 className="font-semibold text-sm mt-4 mb-2">Recorded checks</h4>
                <dl className="grid sm:grid-cols-2 gap-2 text-sm">{checks.map(([name, value]) => (
                  <div key={name} className="flex justify-between gap-3 border-b py-1" style={{ borderColor: 'var(--line)' }}>
                    <dt className="desk-muted">{name.replaceAll('_', ' ')}</dt><dd className="desk-num">{String(value)}</dd>
                  </div>
                ))}</dl>
              </>}
            </>
          ) : <p className="desk-muted text-sm">Reason was not recorded for this older trade. Its position facts remain available.</p>}
      </section>
      {chart ? <TradeChart data={chart} /> : <section className="desk-panel p-5 text-sm desk-muted">{loading ? 'Loading chart…' : 'Chart unavailable.'}</section>}
    </article>
  );
};
