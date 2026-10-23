import React, { useState } from 'react';
import { useApp } from '../../data/appStore';
import { buildQuery, useApiData } from '../../data/hooks/useApiData';
import { setFilter } from '../../data/selection';
import { cleanRange, rangeError, rangeQuery, type BookKey } from '../../features/analytics/range';
import type { AttributionReport, Bucket } from '../../features/analytics/types';
import { inr, pct, points } from '../../lib/numbers';
import { useTable, type ColumnDef } from '../../lib/useTable';
import { PanelFrame } from '../PanelFrame';
import { ColumnChooser, ColumnsButton, DataTable } from '../DataTable';
import type { PanelProps } from '../registry';
import { pickEnum } from '../hooks';
import { AsyncStrip, Bar, Computed, LowSampleBadge, RangeBar } from '../kit';

export const GROUPS = ['setup', 'symbol', 'side', 'hour', 'weekday', 'exit_reason'] as const;
export const GROUP_LABELS: Record<(typeof GROUPS)[number], string> = { setup: 'Setup', symbol: 'Symbol', side: 'Side', hour: 'Entry hour', weekday: 'Weekday', exit_reason: 'Exit reason' };

export const COLUMNS: ColumnDef<Bucket>[] = [
  { key: 'key', label: 'Name', sortable: true },
  { key: 'trades', label: 'Trades', sortable: true },
  { key: 'win_rate', label: 'Win %', sortable: true },
  { key: 'net_pnl', label: 'Net P&L', sortable: true },
  { key: 'gross_pnl', label: 'Gross', sortable: true },
  { key: 'charges', label: 'Charges', sortable: true },
  { key: 'cost_drag_pct', label: 'Cost drag %', sortable: true },
  { key: 'expectancy', label: 'Expectancy', sortable: true },
  { key: 'profit_factor', label: 'Profit factor', sortable: true },
  { key: 'avg_r', label: 'Avg R', sortable: true },
  { key: 'max_drawdown', label: 'Max drawdown', sortable: true },
  { key: 'avg_minutes_held', label: 'Held (min)', sortable: true, defaultHidden: true },
];

const money = (v: number | undefined) => <span className={v ? (v > 0 ? 'desk-up' : 'desk-down') : ''}>{inr(v, { sign: true })}</span>;

const AttributionPanel: React.FC<PanelProps> = ({ params, setParams }) => {
  const spec = cleanRange(params);
  const book: BookKey = params.book === 'all' ? 'all' : 'paper';
  const group = pickEnum(params.group, GROUPS, 'setup');
  const filter = useApp((s) => s.filter);
  const err = rangeError(spec);
  const api = useApiData<AttributionReport>(err ? null : `/api/analytics/attribution${buildQuery({ ...rangeQuery(spec), book, group })}`, { watchTrades: true });
  const rows = api.data?.buckets ?? [];
  const table = useTable(rows, {
    columns: COLUMNS, storageKey: `attribution-${group}`, csvName: `attribution_${group}.csv`, initialSort: { key: 'net_pnl', dir: 'desc' },
    onActivate: (b) => toggle(b.key ?? ''),
  });
  const [chooser, setChooser] = useState(false);
  const maxNet = Math.max(0, ...rows.map((r) => Math.abs(r.net_pnl ?? 0)));
  const toggle = (key: string) => setFilter(filter && filter.group === group && filter.key === key ? null : { group, key });
  const save = (patch: Record<string, unknown>) => setParams({ ...params, ...patch });
  const cell = (b: Bucket, key: string): React.ReactNode => {
    switch (key) {
      case 'key': return <>{b.key} <LowSampleBadge trades={b.trades} /></>;
      case 'win_rate': return <span className="inline-flex items-center gap-1">{pct(b.win_rate, 1)}</span>;
      case 'net_pnl': return <span className="flex items-center gap-1 justify-end">{b.low_sample ? <span>{inr(b.net_pnl, { sign: true })}</span> : money(b.net_pnl)}<span style={{ width: 48 }}><Bar value={b.net_pnl ?? 0} max={maxNet} tone={b.low_sample ? undefined : (b.net_pnl ?? 0) >= 0 ? 'up' : 'down'} /></span></span>;
      case 'gross_pnl': case 'charges': case 'expectancy': return inr((b as unknown as Record<string, number>)[key], { sign: key !== 'charges' });
      case 'cost_drag_pct': return b.cost_drag_pct == null ? '—' : pct(b.cost_drag_pct, 1);
      case 'profit_factor': return b.profit_factor == null ? '—' : points(b.profit_factor, 2);
      case 'avg_r': return b.avg_r == null ? '—' : points(b.avg_r, 2);
      case 'max_drawdown': return inr(b.max_drawdown);
      case 'avg_minutes_held': return b.avg_minutes_held == null ? '—' : points(b.avg_minutes_held, 0);
      default: return String((b as unknown as Record<string, unknown>)[key] ?? '');
    }
  };
  return (
    <PanelFrame title="Attribution" sources={[]} exportCsv={table.exportCsv} onRetry={api.reload} actions={<ColumnsButton open={chooser} onToggle={() => setChooser((v) => !v)} />}>
      {chooser && <ColumnChooser table={table} />}
      <RangeBar spec={spec} book={book} onSpec={(s) => save({ range: s.range, from: s.from, to: s.to })} onBook={(b) => save({ book: b })} />
      <div className="flex items-center gap-2 px-2 py-1">
        <label className="text-xs">Group by <select className="desk-input" style={{ width: 'auto' }} value={group} onChange={(e) => save({ group: e.target.value })}>
          {GROUPS.map((g) => <option key={g} value={g}>{GROUP_LABELS[g]}</option>)}
        </select></label>
        {filter && <span className="desk-pill">Filter: {filter.group.replace('_', ' ')} = {filter.key} <button type="button" className="desk-btn" onClick={() => setFilter(null)}>Clear</button></span>}
        <span className="text-xs desk-muted ml-auto">Select a row to filter Trades and Performance summary.</span>
      </div>
      <AsyncStrip state={api} onRetry={api.reload} what="attribution" />
      {api.data && rows.length === 0 && <p className="p-6 text-center text-sm desk-muted">No closed trades in this range.</p>}
      {rows.length > 0 && (
        <DataTable table={table} label={`Attribution by ${GROUP_LABELS[group]}`} numeric={new Set(COLUMNS.filter((c) => c.key !== 'key').map((c) => c.key))}
          rowKey={(b) => String(b.key)} renderCell={(b, c) => cell(b, c.key)} isSelected={(b) => filter?.group === group && filter.key === b.key} onRowClick={(b) => toggle(b.key ?? '')} />
      )}
      <Computed at={api.data?.generated_at} />
    </PanelFrame>
  );
};

export default AttributionPanel;
