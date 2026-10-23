import { vi } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import { ConfirmProvider } from '../features/confirm/ConfirmProvider';
import { appStore } from '../data/appStore';
import type { AppState } from '../data/types';
import type { PanelProps } from '../panels/registry';

/** Renders a panel component inside the providers it needs and returns helpers to change params. */
export function renderPanel(Component: React.ComponentType<PanelProps>, opts: { params?: Record<string, unknown>; state?: Partial<AppState> } = {}) {
  if (opts.state) appStore.setState(opts.state);
  const setParams = vi.fn();
  const ui = (params: Record<string, unknown>) => (
    <ConfirmProvider><Component id="test" params={params} setParams={setParams} /></ConfirmProvider>
  );
  const result = render(ui(opts.params ?? {}));
  return { ...result, setParams, rerenderWith: (params: Record<string, unknown>) => result.rerender(ui(params)) };
}

export const pos = (over: Record<string, unknown> = {}) => ({
  id: 'P1', signal_id: 'S1', symbol: 'NIFTY', option_type: 'CE', strike_symbol: 'NIFTY 24500 CE', timeframe: '5m',
  setup_type: 'SETUP_1_SQUEEZE_EXPANSION', entry_time: '09:30:00', underlying_entry: 24500, underlying_sl: 24400,
  underlying_target_1: 24600, underlying_target_2: 24700, option_entry: 100, option_sl: 80, option_target_1: 120,
  option_target_2: 140, lot_size: 75, lots: 2, quantity: 150, current_underlying: 24510, current_option_price: 105,
  pnl_points: 5, pnl_rupees: 750, status: 'OPEN', est_net_pnl: 700, ...over,
}) as never;

export const signal = (over: Record<string, unknown> = {}) => ({
  id: 'S1', symbol: 'NIFTY', timeframe: '5m', setup_type: 'Setup 1: BB Squeeze Breakout', option_type: 'CE',
  timestamp: '2026-10-22T09:30:00+05:30', is_confirmed: true, entry_price: 24500, stop_loss: 24400, target_1: 24600, target_2: 24700,
  strike_recommendation: { strike_symbol: 'NIFTY 24500 CE', estimated_option_entry: 100, option_sl_price: 80, option_target_1_price: 120, option_target_2_price: 140, lot_size: 75, underlying_price: 24500, option_type: 'CE', atm_strike: 24500, recommended_strike: 24500, symbol: 'NIFTY', risk: 100, stop_loss: 24400, target_1: 24600, target_2: 24700, option_sl_pts: 20, option_target_1_pts: 20, option_target_2_pts: 40 },
  indicators_snapshot: { close: 24500, bb_upper: 24600, bb_middle: 24500, bb_lower: 24400, bandwidth: 1, percent_b: 0.5, vwap: 24490, rsi: 55, ema_9: 24495, adx: 25 },
  rationale: 'test', ...over,
}) as never;
