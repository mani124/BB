// Show the date whenever a trade crosses midnight/sessions so an overnight exit never
// looks like it happened before its entry (times alone are HH:MM:SS).
export function formatTradeSpan(trade: {
  entry_time: string;
  exit_time?: string;
  entry_datetime?: string | null;
  exit_datetime?: string | null;
}, opts: { short?: boolean } = {}): string {
  const t = (v?: string) => (opts.short && v ? v.slice(0, 5) : v ?? '');
  const entryDate = trade.entry_datetime?.slice(0, 10);
  const exitDate = trade.exit_datetime?.slice(0, 10);
  const fmt = (iso: string, time: string) => {
    const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
    const label = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    return `${label} ${time}`;
  };
  if (entryDate && exitDate && entryDate !== exitDate) {
    return `${fmt(entryDate, t(trade.entry_time))} → ${fmt(exitDate, t(trade.exit_time))}`;
  }
  return `${t(trade.entry_time)} → ${t(trade.exit_time)}`;
}


type SummaryTrade = {
  quarantine_reason?: string | null;
  net_pnl?: number;
  gross_pnl?: number;
  pnl_rupees?: number;
  total_slippage_cost?: number;
};

export function summarizeTrades(trades: SummaryTrade[]) {
  const counted = trades.filter((t) => !t.quarantine_reason);
  const wins = counted.filter((t) => (t.net_pnl ?? t.gross_pnl ?? t.pnl_rupees ?? 0) > 0).length;
  return {
    count: counted.length,
    winRate: counted.length > 0 ? ((wins / counted.length) * 100).toFixed(1) : '0.0',
    gross: counted.reduce((a, t) => a + (t.gross_pnl ?? t.pnl_rupees ?? 0), 0),
    net: counted.reduce((a, t) => a + (t.net_pnl ?? t.pnl_rupees ?? 0), 0),
    slippage: counted.reduce((a, t) => a + (t.total_slippage_cost ?? 0), 0),
  };
}
