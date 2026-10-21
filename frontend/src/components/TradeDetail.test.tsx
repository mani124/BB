import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TradeDetail } from './TradeDetail';
import type { DashboardTrade, DashboardTradeDetail } from '../types/dashboard';

const trade = { id: 'paper:1', book: 'paper', source_id: '1', display_book: 'Main scanner', mode: 'demo',
  instrument: 'NIFTY CE', setup: 'Setup 1', status: 'TARGET_1', opened_at: '2026-10-19T09:30:00+05:30',
  closed_at: null, net_pnl: 50, net_kind: 'estimated', evidence_state: 'recorded' } as DashboardTrade;

describe('TradeDetail', () => {
  it('allows closing remaining paper quantity after target one', () => {
    render(<TradeDetail trade={trade} detail={null} chart={null} loading={false} onClose={vi.fn()} closing={false} actionError={null} />);
    expect(screen.getByRole('button', { name: 'Close position' })).toBeInTheDocument();
  });

  it('renders a structured signal without object coercion', () => {
    const cx = { ...trade, book: 'earnings', display_book: 'Earnings', status: 'OPEN' } as DashboardTrade;
    const detail = { ...cx, reason_state: 'recorded', decision: { reason: 'SIGNAL',
      rationale: { setup: 'MODE_A', side: 'CE', symbol: 'INFY' }, checks: { adx: 30 } } } as DashboardTradeDetail;
    render(<TradeDetail trade={cx} detail={detail} chart={null} loading={false} onClose={vi.fn()} closing={false} actionError={null} />);
    expect(screen.getByText('MODE_A · CE · INFY')).toBeInTheDocument();
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
  });
});
