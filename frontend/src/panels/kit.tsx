import React, { useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { formatIst } from '../lib/time';
import { RANGE_KEYS, RANGE_LABELS, rangeError, type BookKey, type RangeSpec } from '../features/analytics/range';
import type { ApiData } from '../data/hooks/useApiData';

export const LOW_SAMPLE = 20;

/** Error strip that keeps the last good data below it. */
export const AsyncStrip: React.FC<{ state: Pick<ApiData<unknown>, 'error' | 'loading' | 'data'>; onRetry: () => void; what: string }> = ({ state, onRetry, what }) => (
  <>
    {state.error && (
      <div className="desk-alert flex items-center gap-2 text-xs" role="alert">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
        <span className="min-w-0 truncate">Could not load {what}: {state.error}.{state.data ? ' Showing the last good data.' : ''}</span>
        <button type="button" className="desk-btn ml-auto" onClick={onRetry}><RefreshCw className="h-3 w-3" aria-hidden /> Retry</button>
      </div>
    )}
    {!state.data && state.loading && <div className="p-4 text-sm desk-muted" role="status">Loading {what}…</div>}
  </>
);

export const Computed: React.FC<{ at?: string | null }> = ({ at }) => (at ? <p className="px-2 py-1 text-xs desk-muted">Computed at {formatIst(at)} IST</p> : null);

export const Kpi: React.FC<{ label: string; value: React.ReactNode; tone?: 'up' | 'down' | ''; hint?: string }> = ({ label, value, tone = '', hint }) => (
  <div className="px-2 py-1 min-w-[6.5rem]" title={hint}>
    <div className="text-xs desk-muted">{label}</div>
    <div className={`desk-num text-base font-semibold ${tone === 'up' ? 'desk-up' : tone === 'down' ? 'desk-down' : ''}`}>{value}</div>
  </div>
);

export const LowSampleBadge: React.FC<{ trades: number }> = ({ trades }) => (trades < LOW_SAMPLE
  ? <span className="desk-pill mute nomark" title={`Fewer than ${LOW_SAMPLE} trades: treat this as noise`}>Low sample ({trades})</span> : null);

/** Horizontal bar with a text value beside it (the text carries the meaning; the bar is decoration). */
export const Bar: React.FC<{ value: number; max: number; tone?: 'up' | 'down' }> = ({ value, max, tone }) => {
  const w = max > 0 ? Math.min(100, Math.max(0, (Math.abs(value) / max) * 100)) : 0;
  return <span className="desk-bar block min-w-[3rem]" aria-hidden><i style={{ width: `${w}%`, background: tone === 'down' ? 'var(--down)' : tone === 'up' ? 'var(--up)' : undefined }} /></span>;
};

export const RangeBar: React.FC<{ spec: RangeSpec; onSpec: (s: RangeSpec) => void; book?: BookKey; onBook?: (b: BookKey) => void }> = ({ spec, onSpec, book, onBook }) => {
  const [draft, setDraft] = useState({ from: spec.from ?? '', to: spec.to ?? '' });
  const err = rangeError({ range: 'custom', from: draft.from, to: draft.to });
  return (
    <div className="flex flex-wrap items-center gap-2 px-2 py-1" style={{ borderBottom: '1px solid var(--line)' }}>
      <div className="desk-seg" role="group" aria-label="Date range">
        {RANGE_KEYS.map((k) => <button key={k} type="button" aria-pressed={spec.range === k} onClick={() => onSpec(k === 'custom' ? { range: 'custom', from: draft.from || undefined, to: draft.to || undefined } : { range: k })}>{RANGE_LABELS[k]}</button>)}
      </div>
      {onBook && book && (
        <div className="desk-seg" role="group" aria-label="Book">
          <button type="button" aria-pressed={book === 'paper'} onClick={() => onBook('paper')}>Current book</button>
          <button type="button" aria-pressed={book === 'all'} onClick={() => onBook('all')}>All books</button>
        </div>
      )}
      {spec.range === 'custom' && (
        <form className="flex items-center gap-1 text-xs" onSubmit={(e) => { e.preventDefault(); if (!err) onSpec({ range: 'custom', from: draft.from, to: draft.to }); }}>
          <label>From <input className="desk-input" style={{ width: '8.5rem' }} placeholder="YYYY-MM-DD" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} aria-invalid={Boolean(err)} /></label>
          <label>To <input className="desk-input" style={{ width: '8.5rem' }} placeholder="YYYY-MM-DD" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} aria-invalid={Boolean(err)} /></label>
          <button type="submit" className="desk-btn" disabled={Boolean(err)}>Apply</button>
          {err && <span className="desk-down" role="alert">{err}</span>}
        </form>
      )}
    </div>
  );
};

/** Chart text alternative plus an opt-in table of the same numbers. */
export const DataToggle: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" className="desk-btn m-1" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{open ? 'Hide' : 'Show'} data table: {label}</button>
      {open && children}
    </div>
  );
};

export const Num: React.FC<{ v: number | null | undefined; fmt: (n: number) => string; sign?: boolean }> = ({ v, fmt, sign }) => (
  v === null || v === undefined || !Number.isFinite(v) ? <span className="desk-muted">—</span> : <span className={sign ? (v > 0 ? 'desk-up' : v < 0 ? 'desk-down' : '') : ''}>{fmt(v)}</span>
);
