import React from 'react';
import { useDialog } from './useDialog';
import { X } from 'lucide-react';
import type { PaperPosition } from '../types';
import { setupCode } from './setupCode';
import { formatCurrency, pnlClass } from './format';
import { formatTradeSpan } from './tradeUtils';

/* ---------- Exit reason as a readable, toned pill ---------- */
const REASON_LABELS: Record<string, string> = {
  EOD_SQUARE_OFF: 'EOD square-off',
  STALE_CARRYOVER: 'Stale carry-over',
  KILL_SWITCH: 'Kill switch',
  MANUAL_OR_RULE_EXIT: 'Manual / rule exit',
  STOPPED_OUT: 'Stop loss',
  STOP_LOSS: 'Stop loss',
  TARGET_1: 'Target 1',
  TARGET_2: 'Target 2',
  CLOSED: 'Closed',
};
export const exitReasonLabel = (reason: string): string =>
  REASON_LABELS[reason] ?? (/^[A-Z0-9_]+$/.test(reason) ? reason.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : reason);
export const ExitReason: React.FC<{ reason: string }> = ({ reason }) => {
  const r = reason.toLowerCase();
  const tone = r.includes('target') ? 'up' : r.includes('stop') || r.includes('kill') ? 'down' : 'mute';
  const label = exitReasonLabel(reason);
  return (
    <span className={`desk-pill ${tone}`} title={reason} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>
      {label}
    </span>
  );
};

/* ---------- Trade drawer (side panel with the full picture of one trade) ---------- */
export const TradeDrawer: React.FC<{
  trade: PaperPosition;
  onClose: () => void;
  onChart: () => void;
  onReceipt: () => void;
}> = ({ trade, onClose, onChart, onReceipt }) => {
  const drawerRef = useDialog<HTMLElement>(onClose);
  const gross = trade.gross_pnl ?? trade.pnl_rupees ?? 0;
  const net = trade.net_pnl ?? trade.pnl_rupees ?? 0;
  const Row: React.FC<{ k: string; children: React.ReactNode }> = ({ k, children }) => (
    <div className="flex justify-between gap-3 py-1.5 text-xs" style={{ borderBottom: '1px solid var(--line)' }}>
      <span className="desk-muted">{k}</span>
      <span className="desk-num text-right">{children}</span>
    </div>
  );
  return (
    <aside ref={drawerRef} className="desk-drawer p-4" role="dialog" aria-modal="true" aria-label="Trade details" tabIndex={-1}>
      <div className="flex items-start justify-between gap-3 pb-3">
        <div>
          <div className="desk-sym text-sm">{trade.strike_symbol}</div>
          <div className="desk-sub">{setupCode(trade.setup_type)} · {trade.setup_type} · {trade.timeframe}</div>
        </div>
        <button type="button" className="desk-btn" onClick={onClose} aria-label="Close details"><X className="h-4 w-4" /></button>
      </div>
      <div className={`desk-num text-2xl font-semibold mb-2 ${pnlClass(net)}`}>{formatCurrency(net, true)}</div>
      <Row k="When">{formatTradeSpan(trade)}</Row>
      <Row k="Quantity">{trade.quantity} ({trade.lots}L × {trade.lot_size})</Row>
      <Row k="Entry → exit">{trade.option_entry.toFixed(1)} → {trade.current_option_price.toFixed(1)}</Row>
      <Row k="Stop / T1 / T2">{trade.option_sl.toFixed(1)} / {trade.option_target_1.toFixed(1)} / {trade.option_target_2.toFixed(1)}</Row>
      <Row k="Why it closed"><ExitReason reason={trade.exit_reason || trade.status} /></Row>
      <Row k="Gross P&L"><span className={pnlClass(gross)}>{formatCurrency(gross, true)}</span></Row>
      <Row k="Charges">{formatCurrency(trade.total_charges ?? 0)}</Row>
      <Row k="Slippage cost">{formatCurrency(trade.total_slippage_cost ?? 0)}</Row>
      <Row k="Entry / exit slippage">{(trade.entry_slippage ?? 0).toFixed(1)} / {(trade.exit_slippage ?? 0).toFixed(1)} pts</Row>
      <div className="flex gap-2 mt-4">
        <button type="button" className="desk-btn accent" onClick={onChart}>Chart</button>
        {trade.charges_breakdown && <button type="button" className="desk-btn" onClick={onReceipt}>Charges receipt</button>}
      </div>
    </aside>
  );
};
