import React from 'react';
import type { DashboardTrade } from '../types/dashboard';

interface Props { trades: DashboardTrade[]; selectedId: string | null; onSelect: (id: string) => void }

const timeLabel = (value: string | null) => value
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
  : 'No time';

const money = (value: number) => `${value < 0 ? '-' : value > 0 ? '+' : ''}₹${Math.abs(value).toLocaleString('en-IN')}`;

/** One scannable line per trade: instrument and setup, opened time, status, net P&L. */
export const TradeQueue: React.FC<Props> = ({ trades, selectedId, onSelect }) => (
  <div>
    <div aria-hidden className="desk-label trade-grid trade-head px-3 py-1.5 sticky top-0 z-[1]"
      style={{ background: 'var(--panel)', borderBottom: '1px solid var(--line-strong)', fontWeight: 600 }}>
      <span>Instrument · setup</span><span>Opened</span><span>Status</span><span className="text-right">Net P&L</span>
    </div>
    {trades.length === 0 && <p className="p-4 desk-muted">No trades match these filters.</p>}
    {trades.map((trade) => (
      <button key={trade.id} type="button" onClick={() => onSelect(trade.id)} aria-pressed={selectedId === trade.id}
        aria-label={`${trade.instrument} ${trade.display_book} ${trade.status}`}
        className="desk-row trade-grid" style={{ borderBottom: '1px solid var(--line)' }}>
        <span className="min-w-0">
          <strong className="block truncate">{trade.instrument}</strong>
          <span className="desk-muted text-xs block truncate">{trade.display_book} · {trade.setup}{trade.quarantine_reason ? ' · excluded from totals' : ''}</span>
        </span>
        <span className="desk-num text-xs desk-muted">{timeLabel(trade.opened_at)}</span>
        <span><span className={`desk-pill ${trade.status === 'OPEN' ? 'up' : 'mute'}`}>{trade.status.replaceAll('_', ' ')}</span></span>
        <span className={`text-right desk-num font-semibold ${trade.net_pnl == null ? 'desk-muted' : trade.net_pnl < 0 ? 'desk-down' : 'desk-up'}`}>
          {trade.net_pnl == null ? 'n/a' : <>{trade.net_kind === 'estimated' && <span className="desk-muted font-normal text-xs">est </span>}{money(trade.net_pnl)}</>}
        </span>
      </button>
    ))}
  </div>
);
