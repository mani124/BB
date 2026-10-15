import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { apiFetch } from '../api/client';
import type { PaperPosition } from '../types';
import { setupCode } from './setupCode';
import { ReplayControls, sliceSeries, startIndex, useReplay } from './ReplayControls';

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
  status: string;
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
    case 'S9': return ['ema', 'vwap'];
    default: return ['bb'];
  }
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// The candle containing time t, or null when t falls before the first held candle.
export const snap = (candles: Candle[], t: number | null): number | null => {
  if (t == null || candles.length === 0) return null;
  let hit: number | null = null;
  for (const c of candles) if (c.time <= t) hit = c.time;
  return hit;
};

const LINE_STYLES: { key: string; group: IndicatorKey; color: (c: Record<string, string>) => string; width: 1 | 2; style: LineStyle; title: string }[] = [
  { key: 'bb_upper', group: 'bb', color: (c) => c.accent, width: 1, style: LineStyle.Solid, title: 'BB+' },
  { key: 'bb_middle', group: 'bb', color: (c) => c.muted, width: 1, style: LineStyle.Dashed, title: 'BB mid' },
  { key: 'bb_lower', group: 'bb', color: (c) => c.accent, width: 1, style: LineStyle.Solid, title: 'BB-' },
  { key: 'bb_upper_25', group: 'bb25', color: (c) => c.down, width: 1, style: LineStyle.Dotted, title: '2.5σ+' },
  { key: 'bb_lower_25', group: 'bb25', color: (c) => c.up, width: 1, style: LineStyle.Dotted, title: '2.5σ-' },
  { key: 'ema_9', group: 'ema', color: () => '#e0a100', width: 2, style: LineStyle.Solid, title: 'EMA9' },
  { key: 'vwap', group: 'vwap', color: () => '#9b59d0', width: 2, style: LineStyle.Solid, title: 'VWAP' },
];

const themeColors = () => ({
  fg: css('--fg'), muted: css('--muted'), line: css('--line'), panel: css('--panel'),
  up: css('--up'), down: css('--down'), accent: css('--accent'),
});

interface DrawnChart {
  chart: IChartApi;
  candles: ISeriesApi<'Candlestick'>;
  lines: Record<string, ISeriesApi<'Line'>>;
  priceLines: IPriceLine[];
  fitted: boolean;
}

export const PositionChartModal: React.FC<{ position: PaperPosition; onClose: () => void }> = ({ position, onClose }) => {
  const [which, setWhich] = useState<Which>(setupCode(position.setup_type) === 'S5' ? 'option' : 'underlying');
  const [data, setData] = useState<ChartPayload | null>(null);
  // The server's status wins, so a position that closes while the popup is open stops polling.
  const status = data?.status ?? position.status;
  const isOpen = status === 'OPEN' || status === 'TARGET_1';
  const [error, setError] = useState<string | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const drawn = useRef<DrawnChart | null>(null);
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

  const fullSeries = data ? data[which] : null;
  const hasCandles = !!fullSeries && fullSeries.candles.length > 0;
  const [replaying, setReplaying] = useState(false);
  const replay = useReplay(fullSeries?.candles.length ?? 0, startIndex(fullSeries?.candles ?? [], data?.entry_time ?? null));
  const canReplay = hasCandles && !isOpen;
  const replayOn = replaying && canReplay;
  const series = useMemo(
    () => (fullSeries && replayOn ? sliceSeries(fullSeries, replay.index) : fullSeries),
    [fullSeries, replayOn, replay.index],
  );
  const shownTime = fullSeries?.candles[replay.index]?.time ?? null;

  // Build the chart once per source/theme; polling below only swaps data, so zoom and pan survive.
  useEffect(() => {
    if (!box.current || !hasCandles) return;
    const c = themeColors();
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: c.panel }, textColor: c.muted, fontSize: 11 },
      grid: { vertLines: { color: c.line }, horzLines: { color: c.line } },
      rightPriceScale: { borderColor: c.line },
      timeScale: { borderColor: c.line, timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: c.muted }, horzLine: { color: c.muted } },
    });
    const candles = chart.addCandlestickSeries({
      upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down,
    });
    const lines: Record<string, ISeriesApi<'Line'>> = {};
    for (const l of LINE_STYLES) {
      if (!indicators.includes(l.group)) continue;
      lines[l.key] = chart.addLineSeries({
        color: l.color(c), lineWidth: l.width, lineStyle: l.style, priceLineVisible: false, lastValueVisible: false, title: l.title,
      });
    }
    drawn.current = { chart, candles, lines, priceLines: [], fitted: false };
    return () => { chart.remove(); drawn.current = null; };
  }, [which, hasCandles, indicators, themeTick]);

  useEffect(() => {
    const d = drawn.current;
    if (!d || !series || series.candles.length === 0) return;
    const c = themeColors();
    d.candles.setData(series.candles.map((k) => ({ ...k, time: k.time as UTCTimestamp })));
    for (const [key, s] of Object.entries(d.lines)) {
      s.setData((series.indicators[key] ?? []).map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    }

    d.priceLines.forEach((pl) => d.candles.removePriceLine(pl));
    const lvl = (price: number, color: string, title: string) =>
      d.candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title });
    const L = series.levels;
    d.priceLines = [
      lvl(L.entry, c.fg, 'Entry'),
      lvl(L.stop, c.down, status === 'TARGET_1' ? 'Trail SL' : 'SL'),
      lvl(L.target_1, c.up, 'T1'),
      lvl(L.target_2, c.up, 'T2'),
    ];
    if (indicators.includes('orb') && series.opening_range) {
      d.priceLines.push(lvl(series.opening_range.high, c.accent, 'OR high'), lvl(series.opening_range.low, c.accent, 'OR low'));
    }

    const markers: SeriesMarker<Time>[] = [];
    // During a replay a marker only appears once its candle has been reached.
    const reached = (t: number | null) => {
      const k = snap(fullSeries?.candles ?? series.candles, t);
      return k != null && (!replayOn || k <= (series.candles[series.candles.length - 1]?.time ?? 0)) ? k : null;
    };
    const et = reached(data?.entry_time ?? null);
    if (et != null) markers.push({ time: et as UTCTimestamp, position: 'belowBar', shape: 'arrowUp', color: c.accent, text: 'Entry' });
    const xt = reached(data?.exit_time ?? null);
    if (xt != null && !isOpen) markers.push({ time: xt as UTCTimestamp, position: 'aboveBar', shape: 'arrowDown', color: c.down, text: 'Exit' });
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    d.candles.setMarkers(markers);

    if (!d.fitted) { d.chart.timeScale().fitContent(); d.fitted = true; }
  }, [series, indicators, data?.entry_time, data?.exit_time, isOpen, status, which, themeTick, hasCandles, fullSeries, replayOn]);

  const entryOffChart = hasCandles && data?.entry_time != null && snap(series!.candles, data.entry_time) == null;

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
              {setupCode(position.setup_type) === 'S8' ? ' · RSI divergence not plotted' : ''}
              {entryOffChart ? ' · entry was before the first held candle' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {canReplay && !replayOn && (
              <button type="button" className="desk-btn text-xs" onClick={() => { replay.seek(startIndex(fullSeries!.candles, data?.entry_time ?? null)); setReplaying(true); }}>Replay</button>
            )}
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
                : !data
                  ? 'Loading chart…'
                  : isOpen
                    ? 'No candles held for this chart yet. The scanner builds them from live ticks, so they appear after a few minutes of market data.'
                    : 'No candles were saved for this trade. Trades taken before candle saving was added cannot be charted.'}
            </div>
          )}
        </div>
        {replayOn && (
          <ReplayControls
            replay={replay}
            total={fullSeries!.candles.length}
            label={shownTime != null ? new Date(shownTime * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }) : ''}
            onExit={() => setReplaying(false)}
          />
        )}
      </div>
    </div>
  );
};
