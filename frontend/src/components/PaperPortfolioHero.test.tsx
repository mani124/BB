import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PaperPortfolioView } from './PaperPortfolioView';
import { PaperPortfolio } from '../types';

describe('PaperPortfolioView Hero Bar', () => {
  const mockPortfolio: PaperPortfolio = {
    active_positions: [],
    closed_trades: [],
    auto_trade_enabled: true,
    default_lots: 2,
    total_realized_pnl: 10884.5,
    total_unrealized_pnl: 0.0,
    total_pnl: 10884.5,
    total_gross_pnl: 12450.0,
    total_slippage_cost: 923.0,
    avg_slippage_points: 0.8,
    total_charges: 642.5,
    total_net_pnl: 10884.5,
    win_rate_pct: 75.0,
    total_trades_count: 8,
    winning_trades_count: 6,
    losing_trades_count: 2,
  };

  it('renders all 4 hero cards: Gross P&L, Slippage, Charges, and Net Realized P&L', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    expect(screen.getByText(/Gross Realized P&L/i)).toBeInTheDocument();
    expect(screen.getByText(/₹12,450.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Slippage Impact/i)).toBeInTheDocument();
    expect(screen.getByText(/₹923.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Brokerage & Regulatory Taxes/i)).toBeInTheDocument();
    expect(screen.getByText(/₹642.50/i)).toBeInTheDocument();
    expect(screen.getByText(/Net Realized P&L/i)).toBeInTheDocument();
  });

  it('renders negative P&L and handles fallback values gracefully', () => {
    const negativePortfolio: PaperPortfolio = {
      active_positions: [],
      closed_trades: [],
      auto_trade_enabled: false,
      default_lots: 2,
      total_realized_pnl: -2500.0,
      total_unrealized_pnl: -120.0,
      total_pnl: -2620.0,
      total_gross_pnl: -1800.0,
      total_slippage_cost: 400.0,
      avg_slippage_points: 1.2,
      total_charges: 300.0,
      total_net_pnl: -2500.0,
      win_rate_pct: 25.0,
      total_trades_count: 4,
      winning_trades_count: 1,
      losing_trades_count: 3,
    };

    render(
      <PaperPortfolioView
        portfolio={negativePortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    expect(screen.getByText(/Gross Realized P&L/i)).toBeInTheDocument();
    expect(screen.getByText(/-₹1,800.00/i)).toBeInTheDocument();
    expect(screen.getByText(/-₹400.00/i)).toBeInTheDocument();
    expect(screen.getByText(/-₹300.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Net Realized P&L/i)).toBeInTheDocument();
    expect(screen.getByText(/-₹2,500.00/i)).toBeInTheDocument();
  });
});
