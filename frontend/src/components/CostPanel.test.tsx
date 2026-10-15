import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CostPanel, type CostReport } from './CostPanel';

const tot = { trades: 2, gross_pnl: 500, slippage: 150, charges: 180, net_pnl: 320, gross_before_slippage: 650, avg_slippage_per_trade: 75 };
const report: CostReport = {
  totals: tot,
  trades: [{ id: 'a', symbol: 'NIFTY 50', setup_type: 'Setup 1', date: '2026-10-15', option_entry: 150, gross_pnl: 1000, slippage: 200, charges: 100, net_pnl: 900 }],
  by_day: [{ date: '2026-10-15', ...tot }],
  by_setup: [{ key: 'Setup 1', ...tot }],
  by_symbol: [{ key: 'NIFTY 50', ...tot }],
  by_premium: [{ key: '100 - 200', ...tot }],
};

describe('CostPanel', () => {
  it('shows totals and says slippage is already inside gross', () => {
    render(<CostPanel initialReport={report} />);
    expect(screen.getByTestId('cost-summary')).toHaveTextContent('Slippage ₹150.00');
    expect(screen.getByTestId('cost-summary')).toHaveTextContent('Net +₹320.00');
    expect(screen.getByText(/already reflected in gross/)).toBeInTheDocument();
    expect(screen.getByText('2026-10-15')).toBeInTheDocument();
  });

  it('switches to the premium breakdown', () => {
    render(<CostPanel initialReport={report} />);
    fireEvent.click(screen.getByText('By premium'));
    expect(screen.getByText('100 - 200')).toBeInTheDocument();
  });

  it('shows an empty state with no trades', () => {
    render(<CostPanel initialReport={{ ...report, totals: { ...tot, trades: 0 } }} />);
    expect(screen.getByText(/after the first closed trade/)).toBeInTheDocument();
  });
});
