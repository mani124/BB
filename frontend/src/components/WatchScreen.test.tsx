import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ScannerState, Signal } from '../types';
import { WatchScreen } from './WatchScreen';
import type { DashboardTrade, DashboardWatch } from '../types/dashboard';

const signal = {
  id: 's1', symbol: 'NIFTY 50', timeframe: '5m', setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
  option_type: 'CE', timestamp: '2026-10-19T10:40:00+05:30', is_confirmed: true,
  entry_price: 22535, stop_loss: 22480, target_1: 22600,
  rationale: 'Breakout above upper band',
  strike_recommendation: { strike_symbol: 'NIFTY 22550 CE', estimated_option_entry: 143.6, option_sl_price: 121.6, option_target_1_price: 176.6, lot_size: 65 },
  indicators_snapshot: { rsi: 61.2, bandwidth: 1.85 },
} as Signal;

const state = {
  signals: [signal], radar: {}, active_mode: 'live', feed_status: 'WS_LIVE',
  last_scan_time: '', scan_cycle_count: 1, is_scanning: false, scan_progress: 0, universe_count: 34,
  paper_portfolio: { active_positions: [], closed_trades: [], default_lots: 2, auto_trade_enabled: false },
} as ScannerState;

describe('WatchScreen', () => {
  const watch: DashboardWatch = {
    observed_at: '2026-10-19T10:45:00+05:30',
    sources: [
      { book: 'paper', mode: 'demo', as_of: '2026-10-19T10:40:00+05:30', state: 'ready', message: '' },
      { book: 'cx', mode: 'paper', as_of: null, state: 'error', message: 'Feed unavailable' },
      { book: 'earnings', mode: 'paper', as_of: null, state: 'unknown', message: '' },
    ],
    candidates: [
      { id: 'paper:s1', book: 'paper', stage: 'CONFIRMED', observed_at: '2026-10-19T10:40:00+05:30',
        is_preview: false, checks: [{ name: 'rsi', value: 61.2 }], block_reason: null,
        instrument: 'NIFTY 50', setup: 'Setup 1', detail: 'Band break', source_ref: {} },
      { id: 'earnings:INFY:A', book: 'earnings', stage: 'READY', observed_at: '2026-10-19T10:42:00+05:30',
        is_preview: true, checks: [], block_reason: null, instrument: 'INFY', setup: 'MODE_A', detail: '', source_ref: {} },
    ],
  };

  const props = { state, loaded: true, wsConnected: true, stream: { state: 'live' as const, ageSec: 0 },
    filters: { setup: 'ALL', optionType: 'ALL', instrumentType: 'ALL', timeframe: 'ALL' }, onFilters: () => {},
    filteredSignals: [signal], closedTrades: [], activeSignalIds: new Set<string>(), onPaperBuy: () => {},
    onClosePosition: () => {}, onToggleAutoTrade: () => {}, onChangeLots: () => {} };

  it('shows mixed-book candidates with preview, source error, and recorded measurements', () => {
    render(<WatchScreen {...props} dashboardWatch={watch} />);
    expect(screen.getByRole('button', { name: /NIFTY 50.*recorded/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /INFY.*preview/i })).toBeInTheDocument();
    expect(screen.getByText(/CX.*Feed unavailable/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /NIFTY 50.*recorded/i }));
    expect(screen.getByText('61.2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /INFY.*preview/i }));
    expect(screen.getByText(/Preview only/i)).toBeInTheDocument();
  });

  it('filters by book and keeps the selected candidate after refresh', () => {
    const { rerender } = render(<WatchScreen {...props} dashboardWatch={watch} />);
    fireEvent.click(screen.getByRole('button', { name: /INFY.*preview/i }));
    rerender(<WatchScreen {...props} dashboardWatch={{ ...watch, observed_at: '2026-10-19T10:46:00+05:30' }} />);
    expect(screen.getByRole('heading', { name: 'INFY' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Book filter'), { target: { value: 'paper' } });
    expect(screen.queryByRole('button', { name: /INFY.*preview/i })).not.toBeInTheDocument();
  });

  it('can focus on candidates still waiting for a condition', () => {
    const waiting = { ...watch.candidates[0], id: 'setup16:WAIT', book: 'setup16' as const,
      instrument: 'BANKNIFTY', stage: 'NO_BREAKOUT', is_preview: false };
    render(<WatchScreen {...props} dashboardWatch={{ ...watch, candidates: [...watch.candidates, waiting] }} />);
    fireEvent.change(screen.getByLabelText('Status filter'), { target: { value: 'waiting' } });
    expect(screen.getByRole('button', { name: /BANKNIFTY.*recorded/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /NIFTY 50.*recorded/i })).not.toBeInTheDocument();
  });

  it('opens a trade only when a recorded signal id matches that trade', () => {
    const onOpenTrade = vi.fn();
    const trade = { id: 'paper:p1', book: 'paper', signal_id: 's1' } as DashboardTrade;
    render(<WatchScreen {...props} dashboardWatch={watch} trades={[trade]} onOpenTrade={onOpenTrade} />);
    fireEvent.click(screen.getByRole('button', { name: /NIFTY 50.*recorded/i }));
    fireEvent.click(screen.getByRole('button', { name: 'View matching trade and chart' }));
    expect(onOpenTrade).toHaveBeenCalledWith('paper:p1');
    fireEvent.click(screen.getByRole('button', { name: /INFY.*preview/i }));
    expect(screen.queryByRole('button', { name: 'View matching trade and chart' })).not.toBeInTheDocument();
  });

  it('asks the operator to inspect a signal before paper buying', () => {
    const onBuy = vi.fn();
    render(<WatchScreen state={state} loaded wsConnected stream={{ state: 'live', ageSec: 0 }}
      filters={{ setup: 'ALL', optionType: 'ALL', instrumentType: 'ALL', timeframe: 'ALL' }} onFilters={() => {}}
      filteredSignals={[signal]} closedTrades={[]} activeSignalIds={new Set()} onPaperBuy={onBuy}
      onClosePosition={() => {}} onToggleAutoTrade={() => {}} onChangeLots={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Paper buy' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /inspect nifty 22550 ce/i }));
    expect(screen.getByText('Breakout above upper band')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Paper buy' }));
    expect(onBuy).toHaveBeenCalledWith(signal);
  });
});
