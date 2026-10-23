export const BINS_MIN = 1;
export const BINS_MAX = 50;
export const cleanBins = (v: unknown): number => {
  const n = typeof v === 'number' && Number.isFinite(v) ? Math.round(v) : 20;
  return Math.min(BINS_MAX, Math.max(BINS_MIN, n));
};
