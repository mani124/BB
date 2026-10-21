import React from 'react';
import type { DashboardCandidate } from '../types/dashboard';

const bookName: Record<DashboardCandidate['book'], string> = {
  paper: 'Main scanner', cx: 'Commodities & FX', earnings: 'Earnings',
};

interface Props {
  candidates: DashboardCandidate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const WatchCandidateListImpl: React.FC<Props> = ({ candidates, selectedId, onSelect }) => (
  <div className="divide-y" style={{ borderColor: 'var(--line)' }}>
    {candidates.length === 0 && <p className="p-4 desk-muted">No candidates match this filter.</p>}
    {candidates.map((candidate) => (
      <button key={candidate.id} type="button" onClick={() => onSelect(candidate.id)}
        aria-pressed={candidate.id === selectedId}
        aria-label={`${candidate.instrument} ${bookName[candidate.book]} ${candidate.stage} ${candidate.is_preview ? 'preview' : 'recorded'}`}
        className="desk-row">
        <span className="min-w-0">
          <strong className="block text-base truncate">{candidate.instrument}</strong>
          <span className="text-xs desk-muted">{bookName[candidate.book]} · {candidate.setup || 'Scanner'}</span>
        </span>
        <span className="shrink-0 text-right">
          <span className={`desk-pill ${candidate.stage === 'READY' || candidate.stage === 'CONFIRMED' || candidate.stage === 'SIGNAL' ? 'up' : 'warn'}`}>{candidate.stage.replaceAll('_', ' ')}</span>
          <span className="block text-xs desk-muted mt-1">{candidate.is_preview ? 'Preview' : 'Recorded'}</span>
        </span>
      </button>
    ))}
  </div>
);

export const WatchCandidateList = React.memo(WatchCandidateListImpl);
