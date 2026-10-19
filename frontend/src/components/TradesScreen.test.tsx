import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TradesScreen } from './TradesScreen';
import type { DashboardTrade } from '../types/dashboard';

const trades: DashboardTrade[] = [
  { id: 'paper:p1', book: 'paper', display_book: 'Setup 16', source_id: 'p1', status: 'OPEN', instrument: 'NIFTY CE',
    setup: 'Setup 16', opened_at: '2026-10-19T09:30:00+05:30', closed_at: null, mode: 'demo', net_pnl: 120,
    net_kind: 'estimated', evidence_state: 'recorded' },
  { id: 'cx:c1', book: 'cx', display_book: 'Commodities & FX', source_id: 'c1', status: 'CLOSED', instrument: 'CRUDEOIL',
    setup: 'Setup 17', opened_at: '2026-10-19T10:00:00+05:30', closed_at: '2026-10-19T10:30:00+05:30', mode: 'paper', net_pnl: -40,
    net_kind: 'realized', evidence_state: 'recorded' },
  { id: 'earnings:e1', book: 'earnings', display_book: 'Earnings', source_id: 'e1', status: 'OPEN', instrument: 'INFY',
    setup: 'MODE_A', opened_at: '2026-10-19T11:00:00+05:30', closed_at: null, mode: 'paper', net_pnl: 0,
    net_kind: 'estimated', evidence_state: 'unavailable' },
];

const detail = async (trade: DashboardTrade) => ({ ...trade, reason_state: trade.evidence_state,
  decision: trade.evidence_state === 'recorded' ? { reason: 'SIGNAL_CONFIRMED', rationale: 'Band break', checks: { rsi: 60 },
    entry: 100, stop: 90, target_1: 110, lots: 2 } : null });
const chart = async () => ({ candle_state: 'unavailable' as const, entry_time: null, exit_time: null, series: [] });

describe('TradesScreen', () => {
  it('finds trades across books and filters by book and status', async () => {
    render(<TradesScreen trades={trades} loadDetail={detail} loadChart={chart} onClosePaper={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByRole('button', { name: /NIFTY CE/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /CRUDEOIL/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search trades'), { target: { value: 'crude' } });
    expect(screen.queryByRole('button', { name: /NIFTY CE/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /CRUDEOIL/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search trades'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Trade book'), { target: { value: 'earnings' } });
    expect(screen.getByRole('button', { name: /INFY/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Trade status'), { target: { value: 'CLOSED' } });
    expect(screen.getByText(/No trades match/i)).toBeInTheDocument();
  });

  it('shows the saved reason first and admits missing history', async () => {
    render(<TradesScreen trades={trades} loadDetail={detail} loadChart={chart} onClosePaper={vi.fn()} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /NIFTY CE/i }));
    expect(await screen.findByText('Band break')).toBeInTheDocument();
    expect(screen.getByText(/Candles were not recorded/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /INFY/i }));
    expect(await screen.findByText(/Reason was not recorded/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Close position/i })).not.toBeInTheDocument();
  });

  it('confirms paper close, refreshes canonical state and reports failure', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onClosePaper = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('Quote stale'));
    const onRefresh = vi.fn();
    render(<TradesScreen trades={trades} loadDetail={detail} loadChart={chart} onClosePaper={onClosePaper} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByRole('button', { name: /NIFTY CE/i }));
    await screen.findByText('Band break');
    fireEvent.click(screen.getByRole('button', { name: 'Close position' }));
    await waitFor(() => expect(onClosePaper).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Close position' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Quote stale');
  });

  it('shows each recorded earnings leg so the opened position is understandable', async () => {
    const loadDetail = async (trade: DashboardTrade) => ({ ...trade, reason_state: 'recorded' as const,
      decision: { reason: 'SIGNAL_CONFIRMED', legs: [{ side: 'BUY', opt: 'CE', strike: 1500 }, { side: 'SELL', opt: 'PE', strike: 1400 }] } });
    render(<TradesScreen trades={trades} loadDetail={loadDetail} loadChart={chart} onClosePaper={vi.fn()} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /INFY/i }));
    expect(await screen.findByText(/BUY CE 1500/i)).toBeInTheDocument();
    expect(screen.getByText(/SELL PE 1400/i)).toBeInTheDocument();
  });
});
