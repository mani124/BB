import React from 'react';
import { PaperPortfolio, PaperPosition, SetupMode } from '../types';
import { PaperPortfolioView } from './PaperPortfolioView';
import { JournalPanel } from './JournalPanel';
import { TelemetryPanel } from './TelemetryPanel';
import { BookFrame } from './BookFrame';
import { formatCurrency } from './format';

export type ReviewTab = 'today' | 'trades' | 'setups' | 'costs' | 'analytics';

const TABS: { id: ReviewTab; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'trades', label: 'Trades' },
  { id: 'setups', label: 'Setups' },
  { id: 'costs', label: 'Costs' },
  { id: 'analytics', label: 'Analytics' },
];

interface ReviewScreenProps {
  portfolio?: PaperPortfolio;
  closedTrades: PaperPosition[];
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeSetupMode: (setup: string, mode: SetupMode) => void;
  onResetPortfolio: () => void;
}

/** After-the-close review in the same frame as every book: status, figures, then one tab at a time. */
export const ReviewScreen: React.FC<ReviewScreenProps> = ({ portfolio, closedTrades, ...handlers }) => {
  const net = portfolio?.total_net_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const open = portfolio?.total_unrealized_net ?? portfolio?.total_unrealized_pnl ?? 0;
  const tone = (v: number) => (v > 0 ? 'up' as const : v < 0 ? 'down' as const : undefined);
  const body = (tab: ReviewTab) => (tab === 'analytics' ? <TelemetryPanel /> : (
    <div className="flex flex-col gap-3">
      <PaperPortfolioView portfolio={portfolio && { ...portfolio, closed_trades: closedTrades }} view={tab} hideStrip {...handlers} />
      {tab === 'today' && <JournalPanel />}
    </div>
  ));
  return (
    <BookFrame
      idPrefix="review"
      testId="review-screen"
      title="Review and journal"
      pills={portfolio ? [
        { text: portfolio.auto_trade_enabled ? 'Auto-enter on' : 'Auto-enter off', tone: portfolio.auto_trade_enabled ? 'up' : 'warn' },
        { text: `${portfolio.default_lots}x lots`, tone: 'mute' },
      ] : []}
      kpis={portfolio ? [
        { label: 'Net realized', value: formatCurrency(net, true), tone: tone(net), hint: 'Closed trades only, after charges' },
        { label: 'Unrealized', value: formatCurrency(open, true), tone: tone(open), hint: 'Open positions, net of estimated exit charges' },
        { label: 'Win rate', value: `${(portfolio.win_rate_pct ?? 0).toFixed(1)}%` },
        { label: 'Trades', value: <>{portfolio.winning_trades_count ?? 0}W / {portfolio.losing_trades_count ?? 0}L</> },
        { label: 'Slippage', value: formatCurrency(-(portfolio.total_slippage_cost ?? 0)), hint: 'Execution slippage cost on closed trades' },
        { label: 'Charges', value: formatCurrency(portfolio.total_charges ?? 0), hint: 'Brokerage, STT, GST, exchange and SEBI fees' },
      ] : []}
      tabs={TABS.map((t) => ({ id: t.id, label: t.label, content: body(t.id) }))}
    />
  );
};
