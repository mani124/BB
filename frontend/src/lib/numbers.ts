const grouped = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** Rupees with Indian digit grouping, 0 dp. `sign` always shows + or -. */
export function inr(n: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const rounded = Math.round(Math.abs(n));
  const body = `₹${grouped.format(rounded)}`;
  if (n < 0 && rounded !== 0) return `-${body}`;
  return opts.sign && rounded !== 0 ? `+${body}` : body;
}

export function pct(n: number | null | undefined, dp = 1): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return `${n.toFixed(dp)}%`;
}

export function points(n: number | null | undefined, dp = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toFixed(dp);
}

export function signedClass(n: number | null | undefined): 'desk-up' | 'desk-down' | '' {
  if (!n) return '';
  return n > 0 ? 'desk-up' : 'desk-down';
}
