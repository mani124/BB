import React from 'react';
import type { PaperPortfolio, PaperPosition } from '../types';
import { TodaySummary } from './TodaySummary';
import { formatCurrency, pnlClass } from './format';
import { setupCode } from './setupCode';

interface Props {
  portfolio?: PaperPortfolio;
  closedTrades: PaperPosition[];
  selectedId: string | null;
  onSelect: (position: PaperPosition) => void;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
}

const Figure: React.FC<{ label: string; title?: string; children: React.ReactNode }> = ({ label, title, children }) => (
  <div className="flex items-baseline justify-between gap-2 px-3 py-1" title={title}>
    <span className="desk-label">{label}</span>
    <span className="desk-num font-semibold">{children}</span>
  </div>
);

/** Right column: the day's figures, entry controls and every open position with its Close button. */
export const PositionsPane: React.FC<Props> = ({ portfolio, closedTrades, selectedId, onSelect, onClosePosition, onToggleAutoTrade, onChangeLots }) => {
  if (!portfolio) {
    return (
      <div className="flex flex-col h-full" aria-busy="true" aria-label="Portfolio">
        <div className="desk-ph"><h2>Open positions</h2></div>
        <div className="p-3 flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <div key={i} className="desk-skel h-8" />)}</div>
      </div>
    );
  }
  const net = portfolio.total_net_pnl ?? portfolio.total_realized_pnl ?? 0;
  const floating = portfolio.total_unrealized_net ?? portfolio.total_unrealized_pnl ?? 0;
  const positions = portfolio.active_positions ?? [];
  return (
    <div className="flex flex-col min-h-0 h-full" aria-label="Portfolio">
      <section aria-label="Portfolio summary" style={{ borderBottom: '1px solid var(--line)' }} className="py-1">
        <Figure label="Net realized" title="Closed trades only, after charges"><span className={pnlClass(net)}>{formatCurrency(net, true)}</span></Figure>
        <Figure label="Unrealized" title="Open positions, net of estimated exit charges"><span className={pnlClass(floating)}>{formatCurrency(floating, true)}</span></Figure>
        <Figure label="Win rate">{(portfolio.win_rate_pct ?? 0).toFixed(1)}% <span className="desk-muted font-normal text-xs">{portfolio.winning_trades_count ?? 0}W / {portfolio.losing_trades_count ?? 0}L</span></Figure>
        <Figure label="Slippage" title="Execution slippage cost on closed trades"><span style={{ color: 'var(--warn)' }}>-{formatCurrency(portfolio.total_slippage_cost ?? 0).replace('-', '')}</span></Figure>
        <Figure label="Charges" title="Brokerage, STT, GST, exchange and SEBI fees">{formatCurrency(portfolio.total_charges ?? 0)}</Figure>
      </section>
      <div className="px-3 py-2 flex flex-wrap items-center gap-2" style={{ borderBottom: '1px solid var(--line)' }}>
        <button type="button" className={`desk-btn sm ${portfolio.auto_trade_enabled ? 'solid' : ''}`} aria-pressed={portfolio.auto_trade_enabled}
          onClick={() => onToggleAutoTrade(!portfolio.auto_trade_enabled)}>
          Auto-enter: {portfolio.auto_trade_enabled ? 'ON' : 'OFF'}
        </button>
        <div className="desk-seg" role="group" aria-label="Lot multiplier">
          {[2, 4, 6, 8, 10].map((l) => <button key={l} type="button" aria-pressed={portfolio.default_lots === l} onClick={() => onChangeLots(l)}>{l}x</button>)}
        </div>
      </div>
      <div className="desk-ph"><h2 id="open-positions-title">Open positions</h2><span className="desk-pill desk-num ml-auto">{positions.length}</span></div>
      <div className="desk-scroll flex-1" tabIndex={0} aria-label="Open positions list">
        {positions.length === 0 && <p className="p-4 text-sm desk-muted">No open paper positions. New signals open trades automatically, or use Paper buy on a signal.</p>}
        {positions.map((pos) => (
          <div key={pos.id} className="desk-row !items-center !py-1.5" data-selected={selectedId === pos.id || undefined}
            style={{ borderBottom: '1px solid var(--line)', background: selectedId === pos.id ? 'var(--accent-soft)' : undefined, borderLeftColor: selectedId === pos.id ? 'var(--accent)' : undefined }}>
            <button type="button" className="min-w-0 text-left flex-1" aria-pressed={selectedId === pos.id} aria-label={`Open ${pos.strike_symbol} position`} onClick={() => onSelect(pos)}>
              <span className="block truncate"><span className="desk-sym">{pos.strike_symbol}</span>{' '}<span className={`desk-side ${pos.option_type === 'CE' ? 'ce' : 'pe'}`}>{pos.option_type}</span></span>
              <span className="desk-sub">{setupCode(pos.setup_type)} · LTP {pos.current_option_price.toFixed(1)}{pos.status === 'TARGET_1' ? ' · T1 hit' : ''}</span>
            </button>
            <span className={`desk-num font-semibold text-right shrink-0 ${pnlClass(pos.pnl_rupees)}`}>{formatCurrency(pos.pnl_rupees, true)}</span>
            <button type="button" className="desk-btn sm danger" aria-label={`Close ${pos.strike_symbol}`} onClick={() => onClosePosition(pos.id)}>Close</button>
          </div>
        ))}
        <TodaySummary trades={closedTrades} />
      </div>
    </div>
  );
};
