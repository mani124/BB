import type { HistBin } from './types';

/** Equal-width bins over the data range; one bin when all values are equal. */
export function histogram(values: number[], bins: number): HistBin[] {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length === 0) return [];
  const lo = Math.min(...v);
  const hi = Math.max(...v);
  if (lo === hi) return [{ lo, hi, count: v.length }];
  const n = Math.max(1, Math.min(60, Math.round(bins)));
  const w = (hi - lo) / n;
  const counts = new Array<number>(n).fill(0);
  for (const x of v) counts[Math.min(n - 1, Math.floor((x - lo) / w))] += 1;
  return counts.map((count, i) => ({ lo: lo + i * w, hi: lo + (i + 1) * w, count }));
}
