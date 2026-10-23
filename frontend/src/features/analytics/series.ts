import type { EquityPoint } from './types';

export interface ChartPoint { time: number; value: number }

/** Epoch seconds, strictly ascending: trades closed in the same second are spread one second apart. */
export function toChartSeries(points: EquityPoint[]): { equity: ChartPoint[]; drawdown: ChartPoint[]; byTime: Map<number, EquityPoint> } {
  const equity: ChartPoint[] = [];
  const drawdown: ChartPoint[] = [];
  const byTime = new Map<number, EquityPoint>();
  let last = -Infinity;
  for (const p of points) {
    let t = Math.floor(new Date(p.t).getTime() / 1000);
    if (!Number.isFinite(t)) continue;
    if (t <= last) t = last + 1;
    last = t;
    equity.push({ time: t, value: p.equity });
    drawdown.push({ time: t, value: -p.drawdown });
    byTime.set(t, p);
  }
  return { equity, drawdown, byTime };
}
