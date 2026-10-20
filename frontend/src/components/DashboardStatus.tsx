import React from 'react';
import type { RiskStatus } from '../types';
import type { DashboardSource } from '../types/dashboard';
import type { StreamStatus } from './Header';

const labels: Record<DashboardSource['book'], string> = {
  paper: 'Main scanner', setup16: 'Setup 16', cx: 'Commodities & FX', earnings: 'Earnings',
};

interface Props {
  sources: DashboardSource[];
  openCount: number | null;
  risk?: RiskStatus | null;
  stream?: StreamStatus;
  error?: string | null;
  entriesAllowed?: boolean | null;
}

const SourceItems: React.FC<Omit<Props, 'entriesAllowed'>> = ({ sources, openCount, risk, stream, error }) => <div className="flex flex-wrap items-center gap-2 text-xs">
  <strong className="mr-1 text-sm">{openCount == null ? 'Open count unavailable' : `${openCount} open ${openCount === 1 ? 'position' : 'positions'}`}</strong>
  {sources.map((source) => (
    <span key={source.book} className={`desk-pill ${source.state === 'error' ? 'down' : source.state === 'stale' || source.state === 'idle' || source.state === 'unknown' ? 'warn' : source.state === 'ready' ? 'up' : ''}`}
      title={source.message || (source.as_of ? `Last evaluation: ${source.as_of}` : 'Last evaluation time unavailable')}>
      {labels[source.book]} · {source.mode} · {source.state === 'idle' ? 'waiting for first scan' : source.state}
    </span>
  ))}
  {error && <span className="desk-pill down">Status unavailable: {error}</span>}
  {risk?.kill_switch_active && <span className="desk-pill down">Kill switch on · positions may be closing</span>}
  {!risk?.kill_switch_active && risk?.entries_blocked && <span className="desk-pill warn">New entries blocked: {risk.block_reason || risk.loss_cap_reason || 'risk rule'}</span>}
  {stream && stream.state !== 'live' && <span className="desk-pill warn">Browser stream {stream.state}</span>}
</div>;

export const DashboardStatus: React.FC<Props> = ({ sources, openCount, risk, stream, error, entriesAllowed }) => (
  <section className="desk-panel px-3 py-2" aria-label="Dashboard status">
    <div className="hidden sm:block"><SourceItems sources={sources} openCount={openCount} risk={risk} stream={stream} error={error} /></div>
    <details className="sm:hidden desk-status-mobile">
      <summary className="flex items-center justify-between gap-2 text-xs">
        <strong>{openCount == null ? 'Open count unavailable' : `${openCount} open`} · paper entries {risk?.kill_switch_active || risk?.entries_blocked ? 'blocked' : entriesAllowed == null ? 'unknown' : entriesAllowed ? 'on' : 'paused'}</strong>
        <span className={`desk-pill ${error || risk?.kill_switch_active || sources.some((source) => source.state === 'error') ? 'down' : stream?.state !== 'live' ? 'warn' : 'up'}`}>
          {error || risk?.kill_switch_active || sources.some((source) => source.state === 'error') ? 'Needs attention' : stream?.state !== 'live' ? 'Updating' : 'Status'} ▾
        </span>
      </summary>
      <div className="pt-3 mt-2 border-t" style={{ borderColor: 'var(--line)' }}><SourceItems sources={sources} openCount={openCount} risk={risk} stream={stream} error={error} /></div>
    </details>
  </section>
);
