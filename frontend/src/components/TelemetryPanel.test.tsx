import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TelemetryPanel } from './TelemetryPanel';
import type { PerformanceReport, TelemetryInsights } from '../types';

const bucket = { trades: 4, wins: 3, losses: 1, win_rate: 75, net_pnl: 1200, expectancy: 300, profit_factor: 2.5, avg_r: 0.8, max_drawdown: 400, max_consecutive_losses: 1, avg_mfe: 900, avg_mae: -200, avg_capture_pct: 62 };
const performance: PerformanceReport = {
  book: 'demo', overall: { ...bucket, slippage_cost: 50, charges: 80 },
  by_setup: [{ key: 'Setup 1', ...bucket }], by_symbol: [{ key: 'NIFTY 50', ...bucket }], by_side: [],
  by_entry_hour: [{ key: '10:00', ...bucket }], by_exit_reason: [{ key: 'TARGET_1', ...bucket }], equity_curve: [],
};
const insights: TelemetryInsights = {
  hours: 24, decisions: { ENTERED: 3, SKIPPED: 5, EXITED: 2, HELD: 0, total: 10 }, by_strategy: {},
  top_skip_reasons: [{ reason: 'SPREAD_TOO_WIDE', strategy: 'Setup 1', n: 4 }],
  errors: [{ code: 'RATE_LIMIT', component: 'DHAN_CLIENT', severity: 'WARNING', n: 2, last_seen: '2026-10-14 10:00:00' }],
  excursions: [{ strategy: 'Setup 1', trades: 4, avg_mfe: 900, avg_mae: -200, avg_final: 300 }],
};

describe('TelemetryPanel', () => {
  const props = { initial: { performance, insights, decisions: [], errors: [] } };

  it('summarises performance with expectancy and capture', () => {
    render(<TelemetryPanel initial={props.initial} />);
    expect(screen.getByTestId('perf-summary')).toHaveTextContent('Expectancy +₹300');
    expect(screen.getByTestId('perf-summary')).toHaveTextContent('62%');
    expect(screen.getByText('Setup 1')).toBeInTheDocument();
  });

  it('shows skip reasons on the decision trail', () => {
    render(<TelemetryPanel initial={props.initial} />);
    fireEvent.click(screen.getByText('Decision trail'));
    expect(screen.getByTestId('decision-summary')).toHaveTextContent('SPREAD_TOO_WIDE · 4');
  });

  it('shows MFE and MAE per strategy', () => {
    render(<TelemetryPanel initial={props.initial} />);
    fireEvent.click(screen.getByText('MFE / MAE'));
    expect(screen.getByText('Setup 1')).toBeInTheDocument();
    expect(screen.getByText('-₹200')).toBeInTheDocument();
  });

  it('shows an empty state with no closed trades', () => {
    render(<TelemetryPanel initial={{ ...props.initial, performance: { ...performance, overall: { trades: 0 } } }} />);
    expect(screen.getByText(/after the first closed trade/)).toBeInTheDocument();
  });
});
