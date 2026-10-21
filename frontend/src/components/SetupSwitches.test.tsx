import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PaperPortfolioView } from './PaperPortfolioView';
import { PaperPortfolio } from '../types';

const portfolio: PaperPortfolio = {
  active_positions: [],
  closed_trades: [],
  auto_trade_enabled: true,
  setup_modes: { '1': 'index', '2': 'index', '5': 'all' },
  default_lots: 2,
  total_realized_pnl: 0,
  total_unrealized_pnl: 0,
  total_pnl: 0,
  win_rate_pct: 0,
  total_trades_count: 0,
  winning_trades_count: 0,
  losing_trades_count: 0,
};

const baseProps = {
  onClosePosition: vi.fn(),
  onToggleAutoTrade: vi.fn(),
  onResetPortfolio: vi.fn(),
};

describe('Setup switches', () => {
  it('shows the current mode per setup and reports a change', () => {
    const onChangeSetupMode = vi.fn();
    render(<PaperPortfolioView portfolio={portfolio} {...baseProps} onChangeSetupMode={onChangeSetupMode} />);

    const setup1 = screen.getByRole('group', { name: /Setup 1 · BB Squeeze mode/ });
    expect(within(setup1).getByRole('button', { name: 'Index' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(setup1).getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(within(setup1).getByRole('button', { name: 'Off' }));
    expect(onChangeSetupMode).toHaveBeenCalledWith('1', 'off');
  });

  it('hides the panel when no handler is provided', () => {
    render(<PaperPortfolioView portfolio={portfolio} {...baseProps} />);
    expect(screen.queryByText('Setup switches')).toBeNull();
  });
});
