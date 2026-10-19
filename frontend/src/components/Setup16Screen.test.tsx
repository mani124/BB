import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Setup16Screen } from './Setup16Screen';
import type { Setup16Overview } from '../types';

const base: Setup16Overview = {
  mode: 'off', settings: { stop_pct: 12, window_start: '09:30', window_end: '14:25' },
  watchlist: { enabled: true, candidates: [], last_cycle: { status: 'no_credentials' } },
  funnel: { NO_BREAKOUT: 2, SIGNAL: 1, WARMUP: 3 }, contracts_checked: 6,
  contracts: [
    { symbol: 'NIFTY 50', side: 'CE', strike_symbol: 'NIFTY 22500 CE', source: 'scan', stage: 'NO_BREAKOUT', close: 101, upper_bb: 103.2, pct_to_upper: 2.18, in_squeeze: true, bandwidth: 8.1, updated_at: '10:31:05' },
    { symbol: 'TCS', side: 'PE', strike_symbol: 'TCS 3900 PE', source: 'watchlist', stage: 'NO_SQUEEZE', close: 80, upper_bb: 70, pct_to_upper: -12.5, in_squeeze: false, bandwidth: 30, updated_at: '10:31:06', stale: true },
  ],
  open_positions: [], today_closed: [{ id: 't1', strike_symbol: 'NIFTY 22500 CE', symbol: 'NIFTY 50', side: 'CE', entry_time: '2026-10-19T10:05:00', exit_time: '2026-10-19T10:40:00', entry: 100, stop: 90, target_1: 115, target_2: 125, price: 90, status: 'STOPPED_OUT', exit_reason: 'Stop Loss', lots: 2, net_pnl: -1800 }],
  today_net_pnl: -1800, stats_all_time: { trades: 4, wins: 1, win_rate: 25, net_pnl: -900, avg_r: -0.2 },
  decisions: [{ ts: '2026-10-19 10:05:00', symbol: 'NIFTY 50', side: 'CE', decision: 'SKIPPED', reason: 'SETUP_OFF' }],
  as_of: '10:31:10',
};

describe('Setup16Screen', () => {
  it('explains that the switch is off and shows the funnel, contracts, results and decisions', () => {
    render(<Setup16Screen initial={base} />);
    expect(screen.getByText(/OFF: signals are seen but no trade is entered/)).toBeInTheDocument();
    expect(screen.getByTestId('s16-funnel')).toHaveTextContent('Below upper band');
    expect(screen.getByTestId('s16-funnel')).toHaveTextContent('Signal');
    expect(screen.getAllByText('NIFTY 22500 CE', { selector: 'td' })).toHaveLength(2);
    expect(screen.getByText('2.18% to go')).toBeInTheDocument();
    expect(screen.getByText('12.5% above')).toBeInTheDocument();
    expect(screen.getByText('-₹1,800', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('SETUP_OFF')).toBeInTheDocument();
    expect(screen.getByText(/All time/)).toHaveTextContent('win rate 25%');
  });

  it('shows an empty state before any option chart is checked', () => {
    render(<Setup16Screen initial={{ ...base, mode: 'index', funnel: {}, contracts: [], contracts_checked: 0, today_closed: [], decisions: [], stats_all_time: null }} />);
    expect(screen.getByText(/No option charts checked yet/)).toBeInTheDocument();
    expect(screen.getByText('ON for indices only')).toBeInTheDocument();
    expect(screen.getByText('No Setup 16 trades closed today.')).toBeInTheDocument();
  });
});
