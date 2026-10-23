import React from 'react';
import { useApp } from '../../data/appStore';
import { buildQuery, useApiData } from '../../data/hooks/useApiData';
import { cleanRange, rangeError, rangeQuery, type BookKey, type RangeSpec } from '../../features/analytics/range';
import { filterToQuery } from '../../features/analytics/filter';
import type { AttributionReport, EquityReport } from '../../features/analytics/types';
import { inr, pct, points } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { AsyncStrip, Computed, Kpi, LOW_SAMPLE, RangeBar } from '../kit';

const toneOf = (n: number | undefined | null): 'up' | 'down' | '' => (!n ? '' : n > 0 ? 'up' : 'down');

const PerfSummaryPanel: React.FC<PanelProps> = ({ params, setParams }) => {
  const spec: RangeSpec = cleanRange(params);
  const book: BookKey = params.book === 'all' ? 'all' : 'paper';
  const filter = useApp((s) => s.filter);
  const err = rangeError(spec);
  const q = { ...rangeQuery(spec), book, ...filterToQuery(filter) };
  const attr = useApiData<AttributionReport>(err ? null : `/api/analytics/attribution${buildQuery({ ...q, group: 'setup' })}`, { watchTrades: true });
  const eq = useApiData<EquityReport>(err ? null : `/api/analytics/equity${buildQuery(q)}`, { watchTrades: true });
  const o = attr.data?.overall;
  const none = o && o.trades === 0;
  const low = Boolean(o && o.trades < LOW_SAMPLE);
  const tone = (n: number | undefined | null) => (low ? '' : toneOf(n));
  const save = (patch: Record<string, unknown>) => setParams({ ...params, ...patch });
  return (
    <PanelFrame title="Performance summary" sources={[]} onRetry={() => { attr.reload(); eq.reload(); }}>
      <RangeBar spec={spec} book={book} onSpec={(s) => save({ range: s.range, from: s.from, to: s.to })} onBook={(b) => save({ book: b })} />
      <AsyncStrip state={attr} onRetry={attr.reload} what="performance" />
      {filter && <p className="px-2 py-1 text-xs desk-muted" role="status">Linked filter from Attribution: {filter.group.replace('_', ' ')} = {filter.key}{filterToQuery(filter).setup || filterToQuery(filter).side ? '' : ' (not applied here: the API filters setup and side only)'}.</p>}
      {none && <p className="p-6 text-center text-sm desk-muted">No closed trades in this range.</p>}
      {o && !none && (
        <>
          <div className="flex flex-wrap" role="group" aria-label="Key figures">
            <Kpi label="Net P&L" value={inr(o.net_pnl, { sign: true })} tone={tone(o.net_pnl)} hint="After charges and slippage" />
            <Kpi label="Gross P&L" value={inr(o.gross_pnl, { sign: true })} tone={tone(o.gross_pnl)} />
            <Kpi label="Charges" value={inr(o.charges)} />
            <Kpi label="Slippage cost" value={inr(o.slippage_cost)} />
            <Kpi label="Trades" value={o.trades} />
            <Kpi label="Win rate" value={pct(o.win_rate, 1)} />
            <Kpi label="Profit factor" value={o.profit_factor == null ? '—' : points(o.profit_factor, 2)} hint="Gross wins divided by gross losses" />
            <Kpi label="Expectancy" value={inr(o.expectancy, { sign: true })} tone={tone(o.expectancy)} hint="Average net P&L per trade" />
            <Kpi label="Average R" value={o.avg_r == null ? '—' : `${points(o.avg_r, 2)} R`} />
            <Kpi label="Max drawdown" value={eq.data ? inr(-eq.data.summary.max_drawdown) : '—'} tone={eq.data && eq.data.summary.max_drawdown > 0 ? 'down' : ''} />
          </div>
          {o.trades < LOW_SAMPLE && (
            <p className="px-2 py-1 text-xs desk-muted" role="note">Low sample: {o.trades} trades. Fewer than {LOW_SAMPLE} trades is too few to trust these ratios, so they are shown in a neutral colour.</p>
          )}
          {attr.data && attr.data.excluded > 0 && <p className="px-2 text-xs desk-muted">{attr.data.excluded} quarantined trades are excluded.</p>}
        </>
      )}
      <Computed at={attr.data?.generated_at} />
    </PanelFrame>
  );
};

export default PerfSummaryPanel;
