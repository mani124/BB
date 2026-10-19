import React from 'react';
import type { DashboardTrade } from '../types/dashboard';

interface Props { trades: DashboardTrade[]; selectedId: string | null; onSelect: (id: string) => void }

const timeLabel = (value: string | null) => value
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
  : 'Time not recorded';

export const TradeQueue: React.FC<Props> = ({ trades, selectedId, onSelect }) => (
  <div className="divide-y" style={{ borderColor: 'var(--line)' }}>
    {trades.length === 0 && <p className="p-4 desk-muted">No trades match these filters.</p>}
    {trades.map((trade) => (
      <button key={trade.id} type="button" onClick={() => onSelect(trade.id)} aria-pressed={selectedId === trade.id}
        aria-label={`${trade.instrument} ${trade.display_book} ${trade.status}`}
        className="w-full text-left p-3 flex gap-3 justify-between hover:bg-[var(--alt)]"
        style={{ background: selectedId === trade.id ? 'var(--accent-soft)' : undefined }}>
        <span className="min-w-0">
          <strong className="block truncate">{trade.instrument}</strong>
          <span className="desk-muted text-xs block">{trade.display_book} · {trade.setup}</span>
          <span className="desk-muted text-xs desk-num block mt-1">{timeLabel(trade.opened_at)}</span>
        </span>
        <span className="shrink-0 text-right">
          <span className={`desk-pill ${trade.status === 'OPEN' ? 'up' : 'mute'}`}>{trade.status.replaceAll('_', ' ')}</span>
          {trade.net_pnl != null && <span className={`block mt-2 text-xs desk-num ${trade.net_pnl < 0 ? 'desk-down' : 'desk-up'}`}>
            {trade.net_kind === 'estimated' ? 'Est. ' : ''}₹{trade.net_pnl.toLocaleString('en-IN')}
          </span>}
        </span>
      </button>
    ))}
  </div>
);
