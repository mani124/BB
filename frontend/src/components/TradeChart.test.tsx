import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
});
