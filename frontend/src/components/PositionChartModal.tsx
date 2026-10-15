import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { apiFetch } from '../api/client';
import type { PaperPosition } from '../types';
import { setupCode } from './setupCode';

interface Point { time: number; value: number }
interface Candle { time: number; open: number; high: number; low: number; close: number }
interface Levels { entry: number; stop: number; target_1: number; target_2: number }
interface SeriesPayload {
  candles: Candle[];
  indicators: Record<string, Point[]>;
  opening_range: { high: number; low: number } | null;
  interval: string;
  levels: Levels;
}
interface ChartPayload {
  entry_time: number | null;
  exit_time: number | null;
  option: SeriesPayload;
  underlying: SeriesPayload;
}

type Which = 'option' | 'underlying';
type IndicatorKey = 'bb' | 'bb25' | 'ema' | 'vwap' | 'orb';

/** Which overlays each setup is evaluated on (see docs/SETUPS_SPECIFICATION.md). */
export function setupIndicators(setupType: string): IndicatorKey[] {
  switch (setupCode(setupType)) {
    case 'S2': return ['bb', 'ema'];
    case 'S4': return ['orb', 'vwap'];
    case 'S5': return ['bb', 'vwap', 'ema'];
    case 'S6':
    case 'S7': return ['bb', 'bb25'];
    default: return ['bb'];
  }
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const snap = (candles: Candle[], t: number | null): number | null => {
  if (t == null || candles.length === 0) return null;
  let hit: number | null = null;
  for (const c of candles) if (c.time <= t) hit = c.time;
  return hit ?? candles[0].time;
};

export const PositionChartModal: React.FC<{ position: PaperPosition; onClose: () => void }> = ({ position, onClose }) => {
  const isOpen = position.status === 'OPEN' || position.status === 'TARGET_1';
  const [which, setWhich] = useState<Which>(setupCode(position.setup_type) === 'S5' ? 'option' : 'underlying');
  const [data, setData] = useState<ChartPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const indicators = useMemo(() => setupIndicators(position.setup_type), [position.setup_type]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await apiFetch(`/api/paper/positions/${encodeURIComponent(position.id)}/chart`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ChartPayload;
        if (alive) { setData(json); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load chart');
      }
    };
    load();
    const id = isOpen ? window.setInterval(load, 15000) : undefined;
    return () => { alive = false; if (id) window.clearInterval(id); };
  }, [position.id, isOpen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Redraw with fresh colours when the theme class on <html> flips.
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeTick((n) => n + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  const series = data ? data[which] : null;
  const hasCandles = !!series && series.candles.length > 0;

  useEffect(() => {
    if (!box.current || !series || series.candles.length === 0) return;
    const fg = css('--fg'), muted = css('--muted'), line = css('--line'), panel = css('--panel');
    const up = css('--up'), down = css('--down'), accent = css('--accent');
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: panel }, textColor: muted, fontSize: 11 },
      grid: { vertLines: { color: line }, horzLines: { color: line } },
      rightPriceScale: { borderColor: line },
      timeScale: { borderColor: line, timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: muted }, horzLine: { color: muted } },
    });
    chartRef.current = chart;

    const candles = chart.addCandlestickSeries({
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down,
    });
    candles.setData(series.candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })));

    const addLine = (key: string, color: string, width: 1 | 2, style: LineStyle = LineStyle.Solid, title?: string) => {
      const pts = series.indicators[key];
      if (!pts?.length) return;
      const s: ISeriesApi<'Line'> = chart.addLineSeries({
        color, lineWidth: width, lineStyle: style, priceLineVisible: false, lastValueVisible: false, title,
      });
      s.setData(pts.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    };
    if (indicators.includes('bb')) {
      addLine('bb_upper', accent, 1, LineStyle.Solid, 'BB+');
      addLine('bb_middle', muted, 1, LineStyle.Dashed, 'BB mid');
      addLine('bb_lower', accent, 1, LineStyle.Solid, 'BB-');
    }
    if (indicators.includes('bb25')) {
      addLine('bb_upper_25', down, 1, LineStyle.Dotted, '2.5σ+');
      addLine('bb_lower_25', up, 1, LineStyle.Dotted, '2.5σ-');
    }
    if (indicators.includes('ema')) addLine('ema_9', '#e0a100', 2, LineStyle.Solid, 'EMA9');
    if (indicators.includes('vwap')) addLine('vwap', '#9b59d0', 2, LineStyle.Solid, 'VWAP');
    if (indicators.includes('orb') && series.opening_range) {
      candles.createPriceLine({ price: series.opening_range.high, color: accent, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'OR high' });
      candles.createPriceLine({ price: series.opening_range.low, color: accent, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'OR low' });
    }

    const L = series.levels;
    const lvl = (price: number, color: string, title: string) =>
      candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title });
    lvl(L.entry, fg, 'Entry');
    lvl(L.stop, down, position.status === 'TARGET_1' ? 'Trail SL' : 'SL');
    lvl(L.target_1, up, 'T1');
    lvl(L.target_2, up, 'T2');

    const markers: SeriesMarker<Time>[] = [];
    const et = snap(series.candles, data?.entry_time ?? null);
    if (et != null) markers.push({ time: et as UTCTimestamp, position: 'belowBar', shape: 'arrowUp', color: accent, text: 'Entry' });
    const xt = snap(series.candles, data?.exit_time ?? null);
    if (xt != null && !isOpen) markers.push({ time: xt as UTCTimestamp, position: 'aboveBar', shape: 'arrowDown', color: down, text: 'Exit' });
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    candles.setMarkers(markers);

    chart.timeScale().fitContent();
    return () => { chart.remove(); chartRef.current = null; };
  }, [series, indicators, data?.entry_time, data?.exit_time, isOpen, position.status, themeTick]);

  const legend: Record<IndicatorKey, string> = {
    bb: 'Bollinger Bands (20, 2σ)', bb25: '2.5σ bands', ema: '9 EMA', vwap: 'Session VWAP', orb: 'Opening range',
  };

  return (
    <div className="desk-overlay" onClick={onClose}>
      <div
        className="desk-modal flex flex-col"
        style={{ maxWidth: '60rem', height: 'min(90vh, 640px)' }}
        role="dialog"
        aria-label={`${position.strike_symbol} chart`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 p-3" style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold">
              {position.strike_symbol} <span className="desk-muted font-normal">· {setupCode(position.setup_type)} {position.setup_type.replace(/^Setup \d: /, '')}</span>
            </h4>
            <p className="text-[11px] desk-muted">
              {which === 'option' ? 'Option premium' : `${position.symbol} spot`} · {series?.interval ?? ''} candles ·{' '}
              {indicators.map((k) => legend[k]).join(', ')}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="desk-seg" role="group" aria-label="Chart source">
              <button type="button" aria-pressed={which === 'option'} onClick={() => setWhich('option')}>Option</button>
              <button type="button" aria-pressed={which === 'underlying'} onClick={() => setWhich('underlying')}>Spot</button>
            </div>
            <button type="button" className="desk-btn" onClick={onClose} aria-label="Close chart">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="relative flex-1 min-h-[260px]">
          <div ref={box} className="absolute inset-0" data-testid="position-chart" />
          {!hasCandles && (
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-xs desk-muted">
              {error
                ? `Could not load the chart (${error}).`
                : data
                  ? 'No candles held for this chart yet. The scanner builds them from live ticks, so they appear after a few minutes of market data.'
                  : 'Loading chart…'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
