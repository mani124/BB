import type { PaperPosition } from '../types';

export const INR = { minimumFractionDigits: 2, maximumFractionDigits: 2 } as const;

export const formatCurrency = (val: number, showPlus = false) => {
  const formatted = Math.abs(val).toLocaleString('en-IN', INR);
  if (val > 0) return `${showPlus ? '+' : ''}₹${formatted}`;
  if (val < 0) return `-₹${formatted}`;
  return `₹${formatted}`;
};

export const pnlClass = (v: number) => (v > 0 ? 'desk-up' : v < 0 ? 'desk-down' : '');

// Quarantined rows come from before the live journal began; they are never shown or counted.
export const liveTrades = (trades: PaperPosition[] | undefined): PaperPosition[] =>
  (trades ?? []).filter((t) => !t.quarantine_reason);

// "14:36:00" -> "14:36" (the full time stays in a tooltip)
export const shortTime = (t?: string | null): string => (t ? t.slice(0, 5) : '');
