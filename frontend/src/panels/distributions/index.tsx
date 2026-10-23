import React from 'react';
import { buildQuery, useApiData } from '../../data/hooks/useApiData';
import { cleanRange, rangeError, rangeQuery, type BookKey } from '../../features/analytics/range';
import type { DistributionReport, HistBin, Percentiles } from '../../features/analytics/types';
import { inr, points } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { AsyncStrip, Computed, DataToggle, RangeBar } from '../kit';
import { Histogram, Scatter } from '../charts';
import { BINS_MAX, BINS_MIN, cleanBins } from './bins';


const sentence = (name: string, p: Percentiles, fmt: (n: number) => string): string =>
  (p.p50 === null ? `${name}: not enough data.` : `${name}: median ${fmt(p.p50)}, 10th percentile ${p.p10 === null ? 'n/a' : fmt(p.p10)}, 90th percentile ${p.p90 === null ? 'n/a' : fmt(p.p90)}.`);

const BinTable: React.FC<{ bins: HistBin[]; name: string }> = ({ bins, name }) => (
  <table className="desk-table" aria-label={`${name} bins`}>
    <thead><tr><th scope="col" className="r">From</th><th scope="col" className="r">To</th><th scope="col" className="r">Trades</th></tr></thead>
    <tbody>{bins.map((b, i) => <tr key={i}><td className="r desk-num">{points(b.lo)}</td><td className="r desk-num">{points(b.hi)}</td><td className="r desk-num">{b.count}</td></tr>)}</tbody>
  </table>
);

const DistributionsPanel: React.FC<PanelProps> = ({ params, setParams }) => {
  const spec = cleanRange(params);
  const book: BookKey = params.book === 'all' ? 'all' : 'paper';
  const bins = cleanBins(params.bins);
  const err = rangeError(spec);
  const api = useApiData<DistributionReport>(err ? null : `/api/analytics/distribution${buildQuery({ ...rangeQuery(spec), book, bins })}`, { watchTrades: true });
  const rep = api.data;
  const save = (patch: Record<string, unknown>) => setParams({ ...params, ...patch });
  const empty = rep && rep.pnl.length === 0;
  const money = (n: number) => inr(n, { sign: true });
  const items = rep ? [
    { id: 'pnl', name: 'Net P&L per trade', bins: rep.pnl, text: sentence('Net P&L', rep.medians.pnl, money), fmt: (n: number) => inr(n), zero: true },
    { id: 'r', name: 'R multiple', bins: rep.r, text: sentence('R multiple', rep.medians.r, (n) => `${points(n, 2)} R`), fmt: (n: number) => points(n, 1), zero: true },
    { id: 'hold', name: 'Hold time (minutes)', bins: rep.hold_minutes, text: sentence('Hold time', rep.medians.hold_minutes, (n) => `${points(n, 0)} min`), fmt: (n: number) => points(n, 0), zero: false },
  ] : [];
  return (
    <PanelFrame title="Distributions" sources={[]} onRetry={api.reload}>
      <RangeBar spec={spec} book={book} onSpec={(x) => save({ range: x.range, from: x.from, to: x.to })} onBook={(b) => save({ book: b })} />
      <div className="px-2 py-1 text-xs flex items-center gap-2">
        <label>Bins <input type="number" className="desk-input" style={{ width: '4.5rem' }} min={BINS_MIN} max={BINS_MAX} value={bins} aria-label="Number of bins" onChange={(e) => save({ bins: cleanBins(Number(e.target.value)) })} /></label>
        <span className="desk-muted">{BINS_MIN} to {BINS_MAX}</span>
      </div>
      <AsyncStrip state={api} onRetry={api.reload} what="distributions" />
      {empty && <p className="p-6 text-center text-sm desk-muted">No closed trades in this range.</p>}
      {rep && !empty && (
        <div className="flex flex-wrap">
          {items.map((it) => (
            <section key={it.id} aria-label={it.name} className="min-w-[16rem] flex-1 p-2">
              <h4 className="text-xs font-semibold">{it.name}</h4>
              <Histogram bins={it.bins} label={`${it.name} histogram`} fmt={it.fmt} zeroLine={it.zero} />
              <p className="text-xs" data-testid={`summary-${it.id}`}>{it.text}</p>
              <DataToggle label={it.name}><BinTable bins={it.bins} name={it.name} /></DataToggle>
            </section>
          ))}
          <section aria-label="MFE against MAE" className="min-w-[16rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Best and worst during the trade</h4>
            <Scatter points={rep.mfe_mae.map((p) => ({ x: p.mae, y: p.mfe }))} label="Maximum adverse excursion against maximum favourable excursion" xLabel="worst (₹)" yLabel="best (₹)" />
            <p className="text-xs">{rep.mfe_mae.length === 0 ? 'Excursions were not recorded for these trades.' : `${rep.mfe_mae.length} trades with recorded excursions.`}</p>
          </section>
        </div>
      )}
      <Computed at={rep?.generated_at} />
    </PanelFrame>
  );
};

export default DistributionsPanel;
