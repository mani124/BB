import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ScannerState } from '../types';
import { WatchStatus } from './WatchStatus';

const state = {
  active_mode: 'live', feed_status: 'WS_LIVE', signals: [], radar: {}, last_scan_time: '',
  scan_cycle_count: 1, is_scanning: false, scan_progress: 0, universe_count: 34,
  paper_portfolio: { active_positions: [], risk: { entries_blocked: false, kill_switch_active: false, loss_cap_tripped: false, daily_loss_limit: 5000, day_pnl: -1000 } },
} as ScannerState;

describe('WatchStatus', () => {
  it('shows entry permission and source freshness separately', () => {
    render(<WatchStatus state={state} stream={{ state: 'stale', ageSec: 27 }} confirmedCount={2} />);
    expect(screen.getByText('Risk permits entries')).toBeInTheDocument();
    expect(screen.getByText('Stale 27s')).toBeInTheDocument();
    expect(screen.getByText('2 confirmed')).toBeInTheDocument();
  });

  it('shows an entry block reason', () => {
    render(<WatchStatus state={{ ...state, paper_portfolio: { ...state.paper_portfolio!, risk: { ...state.paper_portfolio!.risk!, entries_blocked: true, block_reason: 'Daily loss cap reached' } } }} stream={{ state: 'live', ageSec: 0 }} confirmedCount={0} />);
    expect(screen.getByText('Entries paused')).toBeInTheDocument();
    expect(screen.getByText('Daily loss cap reached')).toBeInTheDocument();
  });
});
