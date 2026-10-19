import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { WatchlistPanel } from './WatchlistPanel';

describe('WatchlistPanel', () => {
  it('shows when it was built, for which day, and why a stock is on it', () => {
    render(<WatchlistPanel initial={{
      enabled: true, built_for: '2026-10-21', built_on: '2026-10-19', built_at: '2026-10-19T22:40:00+05:30',
      last_bar_day: '2026-10-19', screened: 180, last_cycle: { status: 'built' },
      candidates: [{ symbol: 'TCS', bw_percentile: 3, bandwidth: 2.1, nr7: true, avg_value_cr: 900, reasons: ['NR7 (narrowest range of 7 days)'] }],
    }} />);
    expect(screen.getByText('1 stocks for 2026-10-21')).toBeInTheDocument();
    expect(screen.getByText('Built just now')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(screen.getByText('TCS')).toBeInTheDocument();
    expect(screen.getByText(/NR7/)).toBeInTheDocument();
  });

  it('says so when nothing was built, and why', () => {
    render(<WatchlistPanel initial={{ enabled: true, candidates: [], last_cycle: { status: 'no_credentials' } }} />);
    expect(screen.getByText('Not built yet')).toBeInTheDocument();
    expect(screen.getByText('Waiting for a Dhan login')).toBeInTheDocument();
  });
});
