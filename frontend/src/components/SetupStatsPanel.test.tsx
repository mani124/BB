import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { SetupStatsTable } from './SetupStatsPanel';

const row = (over = {}) => ({
  setup_type: 'SETUP_1_SQUEEZE_EXPANSION', date: 'ALL', trades: 3, wins: 2, win_rate: 66.7,
  avg_r: 0.83, gross_pnl: 1500, total_slippage_cost: 120, total_charges: 90, net_pnl: 1410, ...over,
});

describe('SetupStatsTable', () => {
  it('renders setup totals and day rows', () => {
    render(<SetupStatsTable rows={[row(), row({ date: '2026-10-14', avg_r: null })]} />);
    expect(screen.getByText(/S1 · SETUP_1_SQUEEZE_EXPANSION/)).toBeInTheDocument();
    expect(screen.getByText('2026-10-14')).toBeInTheDocument();
    expect(screen.getAllByText('₹1,410')).toHaveLength(2);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
  it('shows an empty state', () => {
    render(<SetupStatsTable rows={[]} />);
    expect(screen.getByText('No closed trades yet.')).toBeInTheDocument();
  });
});
