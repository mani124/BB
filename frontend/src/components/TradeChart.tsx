import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, type UTCTimestamp } from 'lightweight-charts';
import type { DashboardChart, DashboardChartSeries } from '../types/dashboard';

interface Props { data: DashboardChart }

function markerTime(series: DashboardChartSeries, timestamp: number | null): UTCTimestamp | null {
  if (timestamp == null) return null;
  const bar = [...series.candles].reverse().find((candle) => candle.time <= timestamp);
  return bar ? bar.time as UTCTimestamp : null;
}

const istTime = (value: unknown) => typeof value === 'number'
  ? new Date(value * 1000).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false })
  : String(value);

const istDateTime = (value: unknown) => typeof value === 'number'
  ? new Date(value * 1000).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST'
  : String(value);

export const TradeChart: React.FC<Props> = ({ data }) => {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [themeRevision, setThemeRevision] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const selected = data.series.find((series) => series.key === selectedKey) ?? data.series[0];

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeRevision((value) => value + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!box.current || !selected?.candles.length) return;
    const root = getComputedStyle(document.documentElement);
    const color = (name: string) => root.getPropertyValue(name).trim();
    let chartWidth = Math.max(1, box.current.clientWidth);
    const chart = createChart(box.current, {
      width: chartWidth, height: box.current.clientHeight || 360,
      layout: { background: { type: ColorType.Solid, color: color('--panel') }, textColor: color('--muted') },
      localization: { timeFormatter: istDateTime },
      grid: { vertLines: { color: color('--line') }, horzLines: { color: color('--line') } },
      rightPriceScale: { borderColor: color('--line') },
      timeScale: { borderColor: color('--line'), timeVisible: true, secondsVisible: false,
        tickMarkFormatter: (time) => istTime(time) },
      crosshair: { mode: 1 },
    });
    const candles = chart.addCandlestickSeries({ upColor: color('--up'), downColor: color('--down'),
      borderUpColor: color('--up'), borderDownColor: color('--down'), wickUpColor: color('--up'), wickDownColor: color('--down') });
    candles.setData(selected.candles.map((bar) => ({ ...bar, time: bar.time as UTCTimestamp })));
    const markers = [];
    const entry = markerTime(selected, data.entry_time);
    const exit = markerTime(selected, data.exit_time);
    if (entry != null) markers.push({ time: entry, position: 'belowBar' as const, color: color('--accent'), shape: 'arrowUp' as const, text: 'Entry' });
    if (exit != null) markers.push({ time: exit, position: 'aboveBar' as const, color: color('--down'), shape: 'arrowDown' as const, text: 'Exit' });
    if (markers.length) candles.setMarkers(markers);
    for (const [name, price] of Object.entries(selected.levels || {})) {
      if (Number.isFinite(price) && price > 0) candles.createPriceLine({ price, color: name === 'stop' ? color('--down') : name === 'entry' ? color('--accent') : color('--up'),
        lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: name.replaceAll('_', ' ') });
    }
    chart.timeScale().fitContent();
    const resize = () => {
      const nextWidth = Math.max(1, box.current?.clientWidth || 0);
      if (nextWidth === chartWidth) return;
      chart.applyOptions({ width: nextWidth });
      if (chartWidth <= 1 && nextWidth > 1) chart.timeScale().fitContent();
      chartWidth = nextWidth;
    };
    window.addEventListener('resize', resize);
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    if (observer && box.current) observer.observe(box.current);
    return () => { window.removeEventListener('resize', resize); observer?.disconnect(); chart.remove(); };
  }, [selected, data.entry_time, data.exit_time, themeRevision]);

  if (!selected?.candles.length) {
    return <div className="desk-panel p-5 text-sm desk-muted">Candles were not recorded for this trade. The trade facts above are still available.</div>;
  }
  return (
    <section className="desk-panel p-3" aria-label="Trade candlestick chart">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h3 className="font-semibold text-sm">{data.candle_state === 'recorded' ? 'Real candlestick chart' : 'Related market candlesticks'}</h3>
        <label className="text-xs desk-muted">Instrument <select className="desk-input ml-2" value={selected.key} onChange={(event) => setSelectedKey(event.target.value)}>
          {data.series.map((series) => <option key={series.key} value={series.key}>{series.label}</option>)}
        </select></label>
      </div>
      {data.candle_state === 'unavailable' && <p className="text-xs desk-muted mb-2">Candles for the traded instrument were not recorded. The chart below shows recorded related market data.</p>}
      <div ref={box} className="trade-chart-canvas w-full min-w-0 overflow-hidden" />
      <p className="text-xs desk-muted mt-2">{selected.label} · {selected.interval} · recorded OHLC only</p>
    </section>
  );
};
