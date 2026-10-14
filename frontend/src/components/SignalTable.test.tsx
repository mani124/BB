import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SignalTable } from './SignalTable';
import { Signal } from '../types';

const signal = {
  id: 'sig-1',
  symbol: 'NIFTY 50',
  timeframe: '5m',
  setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
  option_type: 'CE',
  timestamp: '2026-10-15T10:40:00+05:30',
  is_confirmed: true,
  entry_price: 22535,
  stop_loss: 22480,
  target_1: 22600,
  target_2: 22650,
  strike_recommendation: {
    strike_symbol: 'NIFTY 22550 CE',
    lot_size: 65,
    estimated_option_entry: 143.6,
    option_sl_price: 121.6,
    option_sl_pts: 22,
    option_target_1_price: 176.6,
    option_target_1_pts: 33,
    underlying_price: 22535,
  },
  indicators_snapshot: { rsi: 61.2, bandwidth: 1.85 },
  rationale: '',
} as unknown as Signal;

describe('SignalTable', () => {
  it('renders the compact row and fires Paper buy', () => {
    const onBuy = vi.fn();
    render(<SignalTable signals={[signal]} onPaperBuy={onBuy} activeSignalIds={new Set()} />);
    expect(screen.getByText('10:40')).toBeInTheDocument();
    expect(screen.getByText('NIFTY 22550 CE')).toBeInTheDocument();
    expect(screen.getByText('S1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /paper buy/i }));
    expect(onBuy).toHaveBeenCalledWith(signal);
  });

  it('shows In portfolio instead of a buy button for an open signal', () => {
    render(<SignalTable signals={[signal]} onPaperBuy={() => {}} activeSignalIds={new Set(['sig-1'])} />);
    expect(screen.getByText(/in portfolio/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /paper buy/i })).not.toBeInTheDocument();
  });

  it('disables buy while the candle is unconfirmed', () => {
    render(<SignalTable signals={[{ ...signal, is_confirmed: false } as Signal]} onPaperBuy={() => {}} />);
    expect(screen.getByRole('button', { name: /paper buy/i })).toBeDisabled();
  });
});
