import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ScannerState, Signal } from '../types';
import { WatchScreen } from './WatchScreen';

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
