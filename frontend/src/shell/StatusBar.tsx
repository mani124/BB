import React from 'react';
import { AlertTriangle, CheckCircle2, Circle } from 'lucide-react';
import { sliceStale, useApp, useNow } from '../data/appStore';
import type { SliceName } from '../data/types';
import { formatIst, marketSession } from '../lib/time';

const ITEMS: { name: SliceName; label: string }[] = [
  { name: 'stream', label: 'Stream' }, { name: 'scanner', label: 'Scanner' }, { name: 'portfolio', label: 'Portfolio' },
  { name: 'trades', label: 'Trades' }, { name: 'watch', label: 'Watch' }, { name: 'live', label: 'Live' }, { name: 'health', label: 'Health' },
];

export const BUILD_ID: string = ((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_BUILD_ID) ?? 'dev';

const SESSION_LABEL = { 'pre-open': 'Pre-open', open: 'Market open', closed: 'Market closed', weekend: 'Weekend' } as const;

/** Bottom bar: per-source freshness (words and icons, never colour alone), scan cycle, session clock, build. */
export const StatusBar: React.FC = () => {
  const meta = useApp((s) => s.meta);
  const scanner = useApp((s) => ({ cycle: s.scanner.scan_cycle_count, last: s.scanner.last_scan_time }), (a, b) => a.cycle === b.cycle && a.last === b.last);
  const now = useNow();
  return (
    <footer role="status" aria-label="Status bar" data-testid="status-bar" className="flex flex-wrap items-center gap-x-4 gap-y-0 px-2 text-xs desk-muted shrink-0"
      style={{ minHeight: 22, background: 'var(--alt)', borderTop: '1px solid var(--line-strong)' }}>
      {ITEMS.map(({ name, label }) => {
        const m = meta[name];
        const stale = sliceStale(m, name, now);
        const state = m.status === 'error' ? 'Error' : stale ? 'Stale' : m.asOf === null ? 'Waiting' : 'Fresh';
        const Icon = state === 'Fresh' ? CheckCircle2 : state === 'Waiting' ? Circle : AlertTriangle;
        return (
          <span key={name} data-testid={`status-${name}`} data-state={state.toLowerCase()} className="inline-flex items-center gap-1">
            <Icon className="h-3 w-3" aria-hidden />{label}: {state}
          </span>
        );
      })}
      <span className="desk-num">Cycle {scanner.cycle} · last scan {scanner.last || 'n/a'}</span>
      <span className="ml-auto desk-num">{SESSION_LABEL[marketSession(new Date(now))]} · {formatIst(now)} IST</span>
      <span className="desk-num" title="Build id">build {BUILD_ID}</span>
    </footer>
  );
};
