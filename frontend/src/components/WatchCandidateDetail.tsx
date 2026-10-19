import React from 'react';
import type { DashboardCandidate } from '../types/dashboard';

interface Props { candidate: DashboardCandidate | null }

function displayValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (value == null) return 'Not recorded';
  return String(value);
}

export const WatchCandidateDetail: React.FC<Props> = ({ candidate }) => {
  if (!candidate) return <section className="desk-panel p-5 desk-muted">Select a candidate to see its recorded checks.</section>;
  return (
    <section className="desk-panel p-4 sm:p-5 min-w-0" aria-label="Candidate detail">
      <div className="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <p className="desk-label mb-1">{candidate.book === 'paper' ? 'Main scanner' : candidate.book === 'setup16' ? 'Setup 16' : candidate.book === 'cx' ? 'Commodities & FX' : 'Earnings'}</p>
          <h2 className="text-lg font-semibold">{candidate.instrument}</h2>
          <p className="desk-muted text-sm">{candidate.setup} · {candidate.stage.replaceAll('_', ' ')}</p>
        </div>
        <span className={`desk-pill ${candidate.is_preview ? 'warn' : 'up'}`}>{candidate.is_preview ? 'Preview only' : 'Scanner observation'}</span>
      </div>
      <p className="text-xs desk-muted mt-3">Evaluated {candidate.observed_at || 'time unavailable'}</p>
      {candidate.detail && <p className="mt-3 text-sm">{candidate.detail}</p>}
      {candidate.block_reason && <p className="mt-3 text-sm desk-down">Blocked: {candidate.block_reason}</p>}
      <h3 className="text-sm font-semibold mt-5 mb-2">Recorded checks</h3>
      {candidate.checks.length ? (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {candidate.checks.map(({ name, value }) => (
            <div key={name} className="rounded-md p-2" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
              <dt className="desk-label">{name.replaceAll('_', ' ')}</dt>
              <dd className="desk-num text-sm">{displayValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : <p className="text-sm desk-muted">No check values were recorded for this candidate.</p>}
      {candidate.is_preview && <p className="text-xs desk-muted mt-4">A preview shows what the engine sees now. It is not a saved trade decision.</p>}
    </section>
  );
};
