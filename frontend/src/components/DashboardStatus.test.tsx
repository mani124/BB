import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { DashboardStatus } from './DashboardStatus';
import type { DashboardSource } from '../types/dashboard';

const sources: DashboardSource[] = [
  { book: 'paper', mode: 'demo', as_of: '2026-10-19T09:35:00+05:30', state: 'ready', message: '' },
  { book: 'setup16', mode: 'all', as_of: null, state: 'stale', message: '' },
  { book: 'cx', mode: 'paper', as_of: null, state: 'error', message: 'Feed failed' },
  { book: 'earnings', mode: 'paper', as_of: null, state: 'disabled', message: '' },
];

describe('DashboardStatus', () => {
  it('shows each source independently and keeps its mode visible', () => {
    render(<DashboardStatus sources={sources} openCount={2} />);
    expect(screen.getAllByText(/Main scanner.*demo.*ready/i)).toHaveLength(2);
    expect(screen.getAllByText(/Setup 16.*stale/i)).toHaveLength(2);
    expect(screen.getAllByText(/Commodities & FX.*error/i)).toHaveLength(2);
    expect(screen.getAllByText(/Earnings.*disabled/i)).toHaveLength(2);
    expect(screen.getAllByText(/2 open positions/i)).toHaveLength(2);
  });

  it('calls risk blocks blocked even when the paper auto-enter switch is on', () => {
    render(<DashboardStatus sources={sources} openCount={0} entriesAllowed
      risk={{ entries_blocked: true, kill_switch_active: false, block_reason: 'LOSS_CAP' } as never} />);
    expect(screen.getByText(/paper entries blocked/i)).toBeInTheDocument();
  });
});
