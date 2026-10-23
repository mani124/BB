import React from 'react';
import { buildQuery, useApiData } from '../../data/hooks/useApiData';
import { cleanRange, rangeError, rangeQuery, type BookKey } from '../../features/analytics/range';
import { histogram } from '../../features/analytics/hist';
import type { AttributionReport, ExecutionReport } from '../../features/analytics/types';
import { inr, pct, points } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { AsyncStrip, Bar, Computed, DataToggle, RangeBar } from '../kit';
import { Histogram, Scatter } from '../charts';

const PARTS = ['brokerage', 'stt', 'exchange_fee', 'sebi_fee', 'stamp_duty', 'gst'] as const;
const PART_LABEL: Record<(typeof PARTS)[number], string> = { brokerage: 'Brokerage', stt: 'STT', exchange_fee: 'Exchange fee', sebi_fee: 'SEBI fee', stamp_duty: 'Stamp duty', gst: 'GST' };
const SHADE = ['var(--accent)', 'var(--up)', 'var(--warn)', 'var(--down)', 'var(--muted)', 'var(--line-strong)'];

/** Charts that need a field the data may not have, mapped to that field. */
export const NEEDS: Record<'spread' | 'liquidity' | 'charges', string> = { spread: 'entry_spread_pct', liquidity: 'option_volume', charges: 'charges_breakdown' };

const NotRecorded: React.FC<{ field: string; what: string }> = ({ field, what }) => (
  <p className="text-xs desk-muted p-2" data-testid={`not-recorded-${field}`}>Not recorded: {field}. {what} is hidden until trades carry it.</p>
);

const ExecutionPanel: React.FC<PanelProps> = ({ params, setParams }) => {
  const spec = cleanRange(params);
  const book: BookKey = params.book === 'all' ? 'all' : 'paper';
  const err = rangeError(spec);
  const q = buildQuery({ ...rangeQuery(spec), book });
  const api = useApiData<ExecutionReport>(err ? null : `/api/analytics/execution${q}`, { watchTrades: true });
  const attr = useApiData<AttributionReport>(err ? null : `/api/analytics/attribution${buildQuery({ ...rangeQuery(spec), book, group: 'setup' })}`, { watchTrades: true });
  const rep = api.data;
  const save = (patch: Record<string, unknown>) => setParams({ ...params, ...patch });
  const missing = new Set(rep?.not_recorded ?? []);
  const empty = rep && rep.slippage.entry.length === 0;
  const maxSlip = Math.max(0, ...(rep?.slippage.by_setup ?? []).map((r) => Math.abs(r.entry_avg ?? 0) + Math.abs(r.exit_avg ?? 0)));
  const totalCharges = rep ? PARTS.reduce((a, k) => a + (rep.charges.totals[k] ?? 0), 0) : 0;
  return (
    <PanelFrame title="Execution quality" sources={[]} onRetry={() => { api.reload(); attr.reload(); }}>
      <RangeBar spec={spec} book={book} onSpec={(x) => save({ range: x.range, from: x.from, to: x.to })} onBook={(b) => save({ book: b })} />
      <AsyncStrip state={api} onRetry={api.reload} what="execution quality" />
      {empty && <p className="p-6 text-center text-sm desk-muted">No closed trades in this range.</p>}
      {rep && !empty && (
        <div className="flex flex-wrap">
          <section aria-label="Slippage by setup" className="min-w-[18rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Average slippage by setup (points)</h4>
            <table className="desk-table" aria-label="Slippage by setup">
              <thead><tr><th scope="col">Setup</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Entry</th><th scope="col" className="r">Exit</th><th scope="col" className="r">Cost ₹</th><th scope="col"><span className="sr-only">Bar</span></th></tr></thead>
              <tbody>{rep.slippage.by_setup.map((r) => (
                <tr key={r.key}><td>{r.key}</td><td className="r desk-num">{r.trades}</td><td className="r desk-num">{points(r.entry_avg, 2)}</td><td className="r desk-num">{points(r.exit_avg, 2)}</td><td className="r desk-num">{inr(r.total_cost)}</td>
                  <td style={{ width: '18%' }}><Bar value={Math.abs(r.entry_avg ?? 0) + Math.abs(r.exit_avg ?? 0)} max={maxSlip} /></td></tr>
              ))}</tbody>
            </table>
          </section>
          <section aria-label="Slippage by entry hour" className="min-w-[14rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Average slippage by entry hour</h4>
            <table className="desk-table" aria-label="Slippage by hour">
              <thead><tr><th scope="col">Hour</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Entry</th><th scope="col" className="r">Exit</th></tr></thead>
              <tbody>{rep.slippage.by_hour.map((r) => <tr key={r.key}><td>{r.key}</td><td className="r desk-num">{r.trades}</td><td className="r desk-num">{points(r.entry_avg, 2)}</td><td className="r desk-num">{points(r.exit_avg, 2)}</td></tr>)}</tbody>
            </table>
          </section>
          <section aria-label="Entry and exit slippage" className="min-w-[16rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Entry slippage</h4>
            <Histogram bins={histogram(rep.slippage.entry, 15)} label="Entry slippage histogram" />
            <h4 className="text-xs font-semibold">Exit slippage</h4>
            <Histogram bins={histogram(rep.slippage.exit, 15)} label="Exit slippage histogram" />
          </section>
          <section aria-label="Spread against slippage" className="min-w-[16rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Spread at entry against slippage</h4>
            {missing.has(NEEDS.spread) ? <NotRecorded field={NEEDS.spread} what="This chart" /> : (
              <>
                <Scatter points={rep.spread.points.map((p) => ({ x: p.spread_pct, y: p.slippage }))} label="Spread at entry against entry slippage" xLabel="spread %" yLabel="slippage (pts)" />
                <table className="desk-table" aria-label="Spread buckets"><thead><tr><th scope="col">Spread</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Avg slippage</th></tr></thead>
                  <tbody>{rep.spread.buckets.map((b) => <tr key={b.label}><td>{b.label}</td><td className="r desk-num">{b.trades}</td><td className="r desk-num">{points(b.avg_slippage, 2)}</td></tr>)}</tbody></table>
              </>
            )}
          </section>
          <section aria-label="Liquidity quartiles" className="min-w-[16rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Option volume quartiles against slippage</h4>
            {missing.has(NEEDS.liquidity) ? <NotRecorded field={NEEDS.liquidity} what="This table" /> : (
              <table className="desk-table" aria-label="Liquidity quartiles">
                <thead><tr><th scope="col">Quartile</th><th scope="col" className="r">Volume</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Avg slippage</th><th scope="col" className="r">Net ₹</th></tr></thead>
                <tbody>{rep.liquidity.quartiles.map((r) => <tr key={r.q}><td>Q{r.q}</td><td className="r desk-num">{r.volume_lo}–{r.volume_hi}</td><td className="r desk-num">{r.trades}</td><td className="r desk-num">{points(r.avg_slippage, 2)}</td><td className="r desk-num">{inr(r.net_pnl, { sign: true })}</td></tr>)}</tbody>
              </table>
            )}
          </section>
          <section aria-label="Charges" className="min-w-[18rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Charges</h4>
            {missing.has(NEEDS.charges) ? <NotRecorded field={NEEDS.charges} what="The breakdown" /> : (
              <>
                <svg viewBox="0 0 320 22" role="img" aria-label={`Charges split: ${PARTS.map((k) => `${PART_LABEL[k]} ${inr(rep.charges.totals[k] ?? 0)}`).join(', ')}`} className="w-full">
                  {(() => { let x = 0; return PARTS.map((k, i) => { const w = totalCharges > 0 ? ((rep.charges.totals[k] ?? 0) / totalCharges) * 320 : 0; const r = <rect key={k} x={x} y={2} width={w} height={18} fill={SHADE[i]} />; x += w; return r; }); })()}
                </svg>
                <DataToggle label="charges by setup">
                  <table className="desk-table" aria-label="Charges by setup">
                    <thead><tr><th scope="col">Setup</th>{PARTS.map((k) => <th key={k} scope="col" className="r">{PART_LABEL[k]}</th>)}<th scope="col" className="r">Total</th></tr></thead>
                    <tbody>
                      {rep.charges.by_setup.map((r) => <tr key={r.key}><td>{r.key}</td>{PARTS.map((k) => <td key={k} className="r desk-num">{inr(r[k])}</td>)}<td className="r desk-num">{inr(r.total)}</td></tr>)}
                      <tr><th scope="row">All</th>{PARTS.map((k) => <td key={k} className="r desk-num">{inr(rep.charges.totals[k] ?? 0)}</td>)}<td className="r desk-num">{inr(totalCharges)}</td></tr>
                    </tbody>
                  </table>
                </DataToggle>
              </>
            )}
          </section>
          <section aria-label="Cost drag" className="min-w-[16rem] flex-1 p-2">
            <h4 className="text-xs font-semibold">Cost drag per setup (charges and slippage as a share of gross)</h4>
            {attr.data && attr.data.buckets.length > 0 ? (
              <table className="desk-table" aria-label="Cost drag per setup">
                <thead><tr><th scope="col">Setup</th><th scope="col" className="r">Gross</th><th scope="col" className="r">Charges</th><th scope="col" className="r">Slippage</th><th scope="col" className="r">Drag</th></tr></thead>
                <tbody>{attr.data.buckets.map((b) => <tr key={b.key}><td>{b.key}</td><td className="r desk-num">{inr(b.gross_pnl, { sign: true })}</td><td className="r desk-num">{inr(b.charges)}</td><td className="r desk-num">{inr(b.slippage_cost)}</td><td className="r desk-num">{b.cost_drag_pct == null ? '—' : pct(b.cost_drag_pct, 1)}</td></tr>)}</tbody>
              </table>
            ) : <p className="text-xs desk-muted">No data.</p>}
          </section>
        </div>
      )}
      {rep && missing.size > 0 && <p className="px-2 text-xs desk-muted">Fields absent from every trade in this range: {[...missing].join(', ')}.</p>}
      <Computed at={rep?.generated_at} />
    </PanelFrame>
  );
};

export default ExecutionPanel;
