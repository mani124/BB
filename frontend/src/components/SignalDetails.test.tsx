import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Signal } from '../types';
import { SignalDetails } from './SignalDetails';

const signal = {
  id: 's1', symbol: 'NIFTY 50', timeframe: '5m', setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
  option_type: 'CE', timestamp: '2026-10-19T10:40:00+05:30', is_confirmed: true,
  entry_price: 22535, stop_loss: 22480, target_1: 22600, target_2: 22650,
  rationale: 'Breakout confirmed above the upper band.',
  strike_recommendation: {
    strike_symbol: 'NIFTY 22550 CE', lot_size: 65, estimated_option_entry: 143.6,
    option_sl_price: 121.6, option_target_1_price: 176.6, option_target_2_price: 198,
    is_live_quote: false,
  },
  indicators_snapshot: { rsi: 61.2, bandwidth: 1.85 },
} as Signal;

describe('SignalDetails', () => {
  it('explains the signal and labels an estimated option price', () => {
    const onBuy = vi.fn();
    render(<SignalDetails signal={signal} onClose={() => {}} onPaperBuy={onBuy} isBought={false} />);
    expect(screen.getByRole('dialog', { name: /signal details/i })).toBeInTheDocument();
    expect(screen.getByText(signal.rationale)).toBeInTheDocument();
    expect(screen.getByText(/entry price estimated/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /paper buy/i }));
    expect(onBuy).toHaveBeenCalledWith(signal);
  });

  it('does not allow buying an unconfirmed signal', () => {
    render(<SignalDetails signal={{ ...signal, is_confirmed: false }} onClose={() => {}} onPaperBuy={() => {}} isBought={false} />);
    expect(screen.getByRole('button', { name: /paper buy/i })).toBeDisabled();
    expect(screen.getByText(/awaiting candle close/i)).toBeInTheDocument();
  });
});
