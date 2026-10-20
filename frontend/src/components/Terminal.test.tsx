import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PaperPortfolio, PaperPosition, ScannerState, Signal } from '../types';
import type { DashboardWatch } from '../types/dashboard';
import { Terminal, type TerminalProps } from './Terminal';

const signal = {
  id: 's1', symbol: 'NIFTY 50', timeframe: '5m', setup_type: 'SETUP_1_SQUEEZE_EXPANSION', option_type: 'CE',
  timestamp: '2026-10-19T10:40:00+05:30', is_confirmed: true, entry_price: 22535, stop_loss: 22480, target_1: 22600,
  rationale: 'Breakout above upper band',
  strike_recommendation: { strike_symbol: 'NIFTY 22550 CE', estimated_option_entry: 143.6, option_sl_price: 121.6, option_target_1_price: 176.6, lot_size: 65 },
  indicators_snapshot: { rsi: 61.2, bandwidth: 1.85 },
} as unknown as Signal;
const waiting = { ...signal, id: 's2', is_confirmed: false, strike_recommendation: { ...signal.strike_recommendation, strike_symbol: 'BANKNIFTY 50000 PE' }, option_type: 'PE' } as unknown as Signal;

const position = {
  id: 'p1', signal_id: 'x', symbol: 'RELIANCE', option_type: 'CE', strike_symbol: 'RELIANCE 2880 CE', timeframe: '5m', setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
  entry_time: '10:25:00', option_entry: 50, option_sl: 36, option_target_1: 72, option_target_2: 90, lot_size: 250, lots: 2, quantity: 500,
  current_option_price: 60, pnl_points: 10, pnl_rupees: 5000, status: 'OPEN',
} as unknown as PaperPosition;

const portfolio = { active_positions: [position], closed_trades: [], default_lots: 2, auto_trade_enabled: true, win_rate_pct: 0 } as unknown as PaperPortfolio;
const state = { signals: [signal, waiting], radar: {}, active_mode: 'live', paper_portfolio: portfolio } as unknown as ScannerState;

const watch: DashboardWatch = {
  observed_at: '2026-10-19T10:45:00+05:30', sources: [],
  candidates: [{ id: 'earnings:INFY:A', book: 'earnings', stage: 'READY', observed_at: null, is_preview: true, checks: [], block_reason: null, instrument: 'INFY', setup: 'MODE_A', detail: '', source_ref: {} }],
};

const base = (over: Partial<TerminalProps> = {}): TerminalProps => ({
  state, loaded: true, wsConnected: true, dashboardWatch: null,
  filters: { setup: 'ALL', optionType: 'ALL', instrumentType: 'ALL', timeframe: 'ALL' }, onFilters: () => {},
  filteredSignals: [signal, waiting], closedTrades: [], activeSignalIds: new Set<string>(), portfolio,
  onPaperBuy: vi.fn(), onClosePosition: vi.fn(), onToggleAutoTrade: vi.fn(), onChangeLots: vi.fn(), onChangeSetupMode: vi.fn(), onResetPortfolio: vi.fn(),
  onKillSwitch: vi.fn(), onScanNow: vi.fn(), onOpenAccessKey: vi.fn(), sources: [], trades: [], tradesError: null,
  loadTradeDetail: vi.fn(), loadTradeChart: vi.fn(), onClosePaperTrade: vi.fn(), onRefreshTrades: vi.fn(),
  loadSession: vi.fn(async () => ({ day: '2026-10-19', timezone: 'Asia/Kolkata', events: [], by_book: [], observations: [] })), sessionDay: '2026-10-19', ...over,
});

describe('Terminal', () => {
  it('shows the first open position in the centre until something else is chosen', () => {
    render(<Terminal {...base()} />);
    expect(screen.getByRole('region', { name: 'Selected instrument' })).toHaveTextContent('RELIANCE 2880 CE');
    expect(screen.getByRole('button', { name: 'Close RELIANCE 2880 CE position now' })).toBeInTheDocument();
  });

  it('opens a signal with its reasoning and only buys after inspection', () => {
    const props = base();
    render(<Terminal {...props} />);
    expect(screen.queryByRole('button', { name: 'Paper buy' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect NIFTY 22550 CE CE' }));
    const centre = screen.getByRole('region', { name: 'Selected instrument' });
    expect(within(centre).getByText('Breakout above upper band')).toBeInTheDocument();
    fireEvent.click(within(centre).getByRole('button', { name: 'Paper buy' }));
    expect(props.onPaperBuy).toHaveBeenCalledWith(signal);
  });

  it('does not allow buying a signal that is still awaiting its candle close', () => {
    render(<Terminal {...base()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect BANKNIFTY 50000 PE PE' }));
    expect(screen.getByRole('button', { name: 'Paper buy' })).toBeDisabled();
  });

  it('closes a position from the right column and from the table', () => {
    const props = base();
    render(<Terminal {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Close RELIANCE 2880 CE' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close RELIANCE 2880 CE from table' }));
    expect(props.onClosePosition).toHaveBeenCalledTimes(2);
    expect(props.onClosePosition).toHaveBeenCalledWith('p1');
  });

  it('keeps the scanner-watch list one switch away', () => {
    render(<Terminal {...base({ dashboardWatch: watch })} />);
    fireEvent.click(screen.getByRole('button', { name: /Watching/ }));
    fireEvent.click(screen.getByRole('button', { name: /INFY.*preview/i }));
    expect(screen.getByRole('region', { name: 'Selected instrument' })).toHaveTextContent('Preview only');
  });

  it('gives a full-height tab the whole workspace and lets you take it back', () => {
    render(<Terminal {...base()} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Session' }));
    expect(screen.getByRole('button', { name: 'Show the terminal again' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show the terminal again' }));
    expect(screen.getByRole('button', { name: 'Give the table the whole workspace' })).toBeInTheDocument();
  });
});
