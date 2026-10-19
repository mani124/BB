import React from 'react';
import type { RiskStatus } from '../types';
import type { DashboardSource } from '../types/dashboard';
import type { StreamStatus } from './Header';

const labels: Record<DashboardSource['book'], string> = {
  paper: 'Main scanner', setup16: 'Setup 16', cx: 'Commodities & FX', earnings: 'Earnings',
};

interface Props {
  sources: DashboardSource[];
  openCount: number;
  risk?: RiskStatus | null;
  stream?: StreamStatus;
  error?: string | null;
}

export const DashboardStatus: React.FC<Props> = ({ sources, openCount, risk, stream, error }) => (
  <section className="desk-panel px-3 py-2" aria-label="Dashboard status">
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <strong className="mr-1 text-sm">{openCount} open {openCount === 1 ? 'position' : 'positions'}</strong>
      {sources.map((source) => (
        <span key={source.book} className={`desk-pill ${source.state === 'error' ? 'down' : source.state === 'stale' || source.state === 'unknown' ? 'warn' : source.state === 'ready' ? 'up' : ''}`}
          title={source.message || (source.as_of ? `Last evaluation: ${source.as_of}` : 'Last evaluation time unavailable')}>
          {labels[source.book]} · {source.mode} · {source.state}
        </span>
      ))}
      {error && <span className="desk-pill down">Status unavailable: {error}</span>}
      {risk?.kill_switch_active && <span className="desk-pill down">Kill switch on · positions may be closing</span>}
      {!risk?.kill_switch_active && risk?.entries_blocked && <span className="desk-pill warn">New entries blocked: {risk.block_reason || risk.loss_cap_reason || 'risk rule'}</span>}
      {stream && stream.state !== 'live' && <span className="desk-pill warn">Browser stream {stream.state}</span>}
    </div>
  </section>
);
