import React, { useState } from 'react';
import { JournalPanel } from '../../components/JournalPanel';
import { apiFetch } from '../../api/client';
import { istToday } from '../../lib/time';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

export const eodReportUrl = (day: string): string => `/api/journal/summary.html?day=${encodeURIComponent(day)}`;
export const journalCsvUrl = (start: string, end: string): string => `/api/journal/export.csv?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;

const JournalPanelWrapper: React.FC<PanelProps> = () => {
  const [error, setError] = useState<string | null>(null);
  const report = async () => {
    const day = istToday();
    const res = await apiFetch(eodReportUrl(day));
    if (!res.ok) { setError(`End-of-day report failed (${res.status})`); return; }
    setError(null);
    const href = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = href; a.download = `summary_${day}.html`; a.click();
    URL.revokeObjectURL(href);
  };
  const actionsRow = <button type="button" className="desk-btn" onClick={() => { void report(); }}>End-of-day report</button>;
  return (
    <PanelFrame title="Journal" sources={['closedTrades']} actions={actionsRow}>
      {error && <p role="alert" className="desk-alert m-2 text-xs">{error}</p>}
      <JournalPanel />
    </PanelFrame>
  );
};

export default JournalPanelWrapper;
