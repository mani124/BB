import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ColorType, createChart, type UTCTimestamp } from 'lightweight-charts';
import { buildQuery, useApiData } from '../../data/hooks/useApiData';
import { cleanRange, rangeError, rangeQuery, type BookKey } from '../../features/analytics/range';
import { toChartSeries } from '../../features/analytics/series';
import type { EquityReport } from '../../features/analytics/types';
import { formatIst } from '../../lib/time';
import { inr } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { AsyncStrip, Computed, DataToggle, Kpi, RangeBar } from '../kit';

const EquityPanel: React.FC<PanelProps> = ({ params, setParams }) => {
  const spec = cleanRange(params);
  const book: BookKey = params.book === 'all' ? 'all' : 'paper';
  const err = rangeError(spec);
  const api = useApiData<EquityReport>(err ? null : `/api/analytics/equity${buildQuery({ ...rangeQuery(spec), book })}`, { watchTrades: true });
  const rep = api.data;
  const series = useMemo(() => toChartSeries(rep?.points ?? []), [rep]);
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<string>('');
  const [themeRev, setThemeRev] = useState(0);
  const save = (patch: Record<string, unknown>) => setParams({ ...params, ...patch });

  useEffect(() => {
    const mo = new MutationObserver(() => setThemeRev((v) => v + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!box.current || series.equity.length === 0) return undefined;
    const root = getComputedStyle(document.documentElement);
    const color = (n: string) => root.getPropertyValue(n).trim();
    const chart = createChart(box.current, {
      width: Math.max(1, box.current.clientWidth), height: box.current.clientHeight || 260,
      layout: { background: { type: ColorType.Solid, color: color('--panel') }, textColor: color('--muted') },
      grid: { vertLines: { color: color('--line') }, horzLines: { color: color('--line') } },
      rightPriceScale: { borderColor: color('--line') },
      timeScale: { borderColor: color('--line'), timeVisible: true, secondsVisible: false },
      localization: { timeFormatter: (t: unknown) => (typeof t === 'number' ? `${formatIst(t * 1000, 'datetime')} IST` : String(t)) },
    });
    const dd = chart.addAreaSeries({ priceScaleId: 'dd', lineColor: color('--down'), topColor: 'transparent', bottomColor: color('--down'), lineWidth: 1, priceLineVisible: false });
    chart.priceScale('dd').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 }, visible: false });
    dd.setData(series.drawdown.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    const line = chart.addLineSeries({ color: color('--accent'), lineWidth: 2 });
    line.setData(series.equity.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    chart.timeScale().fitContent();
    chart.subscribeCrosshairMove((param) => {
      const pt = typeof param.time === 'number' ? series.byTime.get(param.time) : undefined;
      setHover(pt ? `${formatIst(pt.t, 'datetime')} IST · equity ${inr(pt.equity, { sign: true })} · drawdown ${inr(-pt.drawdown)}` : '');
    });
    const resize = () => { if (box.current) chart.applyOptions({ width: Math.max(1, box.current.clientWidth) }); };
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    if (ro && box.current) ro.observe(box.current);
    return () => { ro?.disconnect(); chart.remove(); };
  }, [series, themeRev]);

  const s = rep?.summary;
  return (
    <PanelFrame title="Equity and drawdown" sources={[]} onRetry={api.reload}>
      <RangeBar spec={spec} book={book} onSpec={(x) => save({ range: x.range, from: x.from, to: x.to })} onBook={(b) => save({ book: b })} />
      <AsyncStrip state={api} onRetry={api.reload} what="the equity curve" />
      {rep && rep.points.length === 0 && <p className="p-6 text-center text-sm desk-muted">No closed trades in this range.</p>}
      {rep && rep.points.length > 0 && s && (
        <>
          <p className="px-2 py-1 text-sm" aria-live="off">
            Net {inr(s.net, { sign: true })} over {rep.points.length} trades. Deepest drawdown {inr(-s.max_drawdown)}; now {inr(-s.current_drawdown)} below the peak. Longest drawdown {s.longest_drawdown_days} days.
          </p>
          <div ref={box} role="img" aria-label="Equity line with drawdown area" style={{ height: 240 }} className="w-full min-w-0" data-testid="equity-chart" />
          <p className="px-2 text-xs desk-muted" style={{ minHeight: 18 }}>{hover || 'Move over the chart for a readout.'}</p>
          <div className="flex flex-wrap"><Kpi label="Max drawdown" value={inr(-s.max_drawdown)} tone={s.max_drawdown ? 'down' : ''} /><Kpi label="Current drawdown" value={inr(-s.current_drawdown)} /></div>
          <DataToggle label="equity points">
            <div className="overflow-auto" style={{ maxHeight: 220 }} tabIndex={0} role="group" aria-label="Equity points, scrollable">
              <table className="desk-table" aria-label="Equity points">
                <thead><tr><th scope="col">Closed (IST)</th><th scope="col" className="r">Equity</th><th scope="col" className="r">Day P&L</th><th scope="col" className="r">Drawdown</th></tr></thead>
                <tbody>{rep.points.slice(-300).reverse().map((p) => <tr key={p.t + p.equity}><td>{formatIst(p.t, 'datetime')}</td><td className="r desk-num">{inr(p.equity, { sign: true })}</td><td className="r desk-num">{inr(p.day_pnl, { sign: true })}</td><td className="r desk-num">{inr(-p.drawdown)}</td></tr>)}</tbody>
              </table>
            </div>
          </DataToggle>
          <h4 className="px-2 pt-2 text-xs font-semibold">Five deepest drawdowns</h4>
          {s.drawdowns.length === 0 ? <p className="px-2 pb-2 text-xs desk-muted">No drawdowns.</p> : (
            <table className="desk-table" aria-label="Deepest drawdowns">
              <thead><tr><th scope="col">Start</th><th scope="col">Trough</th><th scope="col">Recovered</th><th scope="col" className="r">Depth</th></tr></thead>
              <tbody>{s.drawdowns.map((d) => <tr key={d.start + d.trough}><td>{formatIst(d.start, 'datetime')}</td><td>{formatIst(d.trough, 'datetime')}</td><td>{d.end ? formatIst(d.end, 'datetime') : 'Not yet'}</td><td className="r desk-num desk-down">{inr(-d.depth)}</td></tr>)}</tbody>
            </table>
          )}
        </>
      )}
      <Computed at={rep?.generated_at} />
    </PanelFrame>
  );
};

export default EquityPanel;
