/** Signed rupees without decimals for one-line hints. */
export function formatCurrencyShort(n: number): string {
  const r = Math.round(n);
  return `${r > 0 ? '+' : r < 0 ? '-' : ''}₹${Math.abs(r).toLocaleString('en-IN')}`;
}
