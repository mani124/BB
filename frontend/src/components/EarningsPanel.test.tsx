import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EarningsPanel } from './EarningsPanel';
import type { EarningsSummary } from '../types';

const summary: EarningsSummary = {
  starting_capital: 500000, realized_net_pnl: 1500, unrealized_net_pnl: -200, equity: 501300, open_positions: 1, closed_trades: 2,
  win_rate: 50, profit_factor: 1.4, avg_win: 2000, avg_loss: -500, total_charges: 320, enabled: false,
  by_mode: {}, last_cycle: { status: 'no_credentials' },
};

describe('EarningsPanel', () => {
  it('says entries are off and paper only, and shows the summary', () => {
    render(<EarningsPanel initial={{ summary, positions: [], candidates: [], calendar: [] }} />);
    expect(screen.getByText(/Entries off/)).toBeInTheDocument();
    expect(screen.getByText('Paper only')).toBeInTheDocument();
    expect(screen.getByTestId('earnings-summary')).toHaveTextContent('Equity ₹5,01,300');
    expect(screen.getByTestId('earnings-summary')).toHaveTextContent('no_credentials');
  });

  it('lists a calendar row and a skipped candidate with its reason', () => {
    render(<EarningsPanel initial={{
      summary, positions: [],
      candidates: [{ symbol: 'TCS', mode: 'MODE_A_RUNUP', ready: false, code: 'SPREAD_TOO_WIDE', detail: 'CE spread 40%' }],
      calendar: [{ symbol: 'TCS', earnings_date: '2026-10-20', session: 'AMC', sector: 'IT', note: '', effective_session: 'AMC', session_origin: 'inferred' }],
    }} />);
    fireEvent.click(screen.getByRole('tab', { name: /Signals now/ }));
    expect(screen.getByText('SPREAD_TOO_WIDE')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Calendar/ }));
    expect(screen.getByRole('button', { name: 'Remove TCS' })).toBeInTheDocument();
    expect(screen.getByTestId('origin-TCS')).toHaveTextContent('inferred');
  });
});
