import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { createChart } from 'lightweight-charts';
import { TradeChart } from './TradeChart';
import type { DashboardChart } from '../types/dashboard';

const setData = vi.fn();
const addCandlestickSeries = vi.fn(() => ({ setData, setMarkers: vi.fn(), createPriceLine: vi.fn() }));
vi.mock('lightweight-charts', () => ({ ColorType: { Solid: 'solid' }, createChart: vi.fn(() => ({ addCandlestickSeries, timeScale: () => ({ fitContent: vi.fn() }), remove: vi.fn(), applyOptions: vi.fn() })) }));

describe('TradeChart', () => {
  it('draws actual OHLC bars with a candlestick series', () => {
    const data: DashboardChart = { candle_state: 'recorded', entry_time: 10, exit_time: null, series: [
      { key: 'option', label: 'Option', interval: '5m', indicators: {}, levels: { entry: 101 },
        candles: [{ time: 10, open: 100, high: 103, low: 99, close: 101 }] },
    ] };
    render(<TradeChart data={data} />);
    expect(addCandlestickSeries).toHaveBeenCalled();
    expect(setData).toHaveBeenCalledWith(data.series[0].candles);
  });

  it('says when real candles were never recorded', () => {
    render(<TradeChart data={{ candle_state: 'unavailable', entry_time: null, exit_time: null, series: [] }} />);
    expect(screen.getByText(/Candles were not recorded/i)).toBeInTheDocument();
  });

  it('labels underlying candles as related data when traded candles are missing', () => {
    render(<TradeChart data={{ candle_state: 'unavailable', entry_time: null, exit_time: null, series: [
      { key: 'underlying', label: 'Underlying', interval: '5m', indicators: {}, levels: {},
        candles: [{ time: 10, open: 100, high: 103, low: 99, close: 101 }] },
    ] }} />);
    expect(screen.getByText('Related market candlesticks')).toBeInTheDocument();
    expect(screen.getByText(/Candles for the traded instrument were not recorded/i)).toBeInTheDocument();
  });

  it('recolors the existing candles when the theme changes', async () => {
    const data: DashboardChart = { candle_state: 'recorded', entry_time: null, exit_time: null, series: [
      { key: 'option', label: 'Option', interval: '5m', indicators: {}, levels: {}, candles: [{ time: 10, open: 100, high: 103, low: 99, close: 101 }] },
    ] };
    render(<TradeChart data={data} />);
    const calls = vi.mocked(createChart).mock.calls.length;
    await act(async () => { document.documentElement.classList.toggle('dark'); await Promise.resolve(); });
    expect(vi.mocked(createChart).mock.calls.length).toBeGreaterThan(calls);
  });

  it('labels candle times in IST', () => {
    const data: DashboardChart = { candle_state: 'recorded', entry_time: null, exit_time: null, series: [
      { key: 'option', label: 'Option', interval: '5m', indicators: {}, levels: {}, candles: [{ time: 0, open: 100, high: 103, low: 99, close: 101 }] },
    ] };
    render(<TradeChart data={data} />);
    const options = vi.mocked(createChart).mock.lastCall?.[1];
    expect(options?.timeScale?.tickMarkFormatter?.(0 as never, 0 as never, 'en-IN')).toBe('05:30');
  });
});
