import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ReviewScreen } from './ReviewScreen';
import { OpenPositionsPanel, CompactStrip, exitReasonLabel } from './PaperPortfolioView';
import type { PaperPortfolio, PaperPosition } from '../types';

const trade = (i: number): PaperPosition => ({
  id: `T${i}`, signal_id: `S${i}`, symbol: 'NIFTY', option_type: 'CE', strike_symbol: `NIFTY ${20000 + i} CE`,
  timeframe: '5m', setup_type: 'SETUP_1_SQUEEZE_EXPANSION', entry_time: '09:30:00', exit_time: '09:45:00',
  underlying_entry: 1, underlying_sl: 1, underlying_target_1: 1, underlying_target_2: 1, option_entry: 100,
  option_sl: 80, option_target_1: 120, option_target_2: 140, lot_size: 75, lots: 1, quantity: 75,
  current_underlying: 1, current_option_price: 110, pnl_points: 10, pnl_rupees: 750, net_pnl: 700, gross_pnl: 750,
  status: 'CLOSED', exit_reason: 'TARGET_2', entry_datetime: `2026-10-${String(1 + (i % 9)).padStart(2, '0')}T09:30:00+05:30`,
  exit_datetime: `2026-10-${String(1 + (i % 9)).padStart(2, '0')}T09:45:00+05:30`,
});

const portfolio = { active_positions: [], closed_trades: [], default_lots: 2, auto_trade_enabled: false, setup_modes: {} } as unknown as PaperPortfolio;

describe('ReviewScreen', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());
  const handlers = {
    onClosePosition: vi.fn(), onToggleAutoTrade: vi.fn(), onChangeLots: vi.fn(),
    onChangeSetupMode: vi.fn(), onResetPortfolio: vi.fn(),
  };

  it('pages the trades tab 25 at a time and opens a drawer on row click', () => {
    const trades = Array.from({ length: 60 }, (_, i) => trade(i));
    render(<ReviewScreen portfolio={portfolio} closedTrades={trades} {...handlers} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Trades' }));
    expect(screen.getByText(/1–25 of 60 trades/)).toBeInTheDocument();
    expect(document.querySelectorAll('tbody tr')).toHaveLength(25);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText(/26–50 of 60 trades/)).toBeInTheDocument();
    fireEvent.click(document.querySelectorAll('tbody tr')[0]);
    expect(screen.getByRole('dialog', { name: 'Trade details' })).toBeInTheDocument();
  });

  it('today tab shows only the latest day', () => {
    render(<ReviewScreen portfolio={portfolio} closedTrades={[trade(0), trade(1)]} {...handlers} />);
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1);
  });
});

describe('compact watch components', () => {
  const open = { ...trade(1), status: 'OPEN', exit_time: undefined, est_net_pnl: 500 } as PaperPosition;
  it('compact position row expands to show details', () => {
    render(<OpenPositionsPanel compact positions={[open]} onClosePosition={() => {}} />);
    expect(screen.queryByText(/Net if closed now/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Details for/ }));
    expect(screen.getByText(/Net if closed now/)).toBeInTheDocument();
  });
  it('compact strip shows net, unrealized and win rate', () => {
    render(<CompactStrip portfolio={{ total_net_pnl: 1200, total_unrealized_net: 300, win_rate_pct: 50, winning_trades_count: 1, losing_trades_count: 1, active_positions: [open] } as unknown as PaperPortfolio} />);
    expect(screen.getByText('+₹1,200.00')).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
  });
});

describe('exitReasonLabel', () => {
  it('turns engine codes into words and keeps readable reasons', () => {
    expect(exitReasonLabel('EOD_SQUARE_OFF')).toBe('EOD square-off');
    expect(exitReasonLabel('LOSS_STREAK_PAUSE')).toBe('Loss streak pause');
    expect(exitReasonLabel('Target 2 (1:2.5) Hit')).toBe('Target 2 (1:2.5) Hit');
  });
});
