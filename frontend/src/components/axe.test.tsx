import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import axe from 'axe-core';
import { ThemeProvider } from '../context/ThemeContext';
import { DhanAuthProvider } from '../context/DhanAuthContext';
import { Header } from './Header';
import { Terminal } from './Terminal';
import { ReviewScreen } from './ReviewScreen';
import { EarningsPanel } from './EarningsPanel';
import { SettingsPanel } from './SettingsPanel';
import { Dialog } from './Dialog';
import type { PaperPortfolio, PaperPosition, ScannerState, Signal, RuntimeSettingsPayload } from '../types';

// jsdom has no layout, so colour contrast is checked separately (see design review notes).
const violations = async (node: Element) => {
  const res = await axe.run(node, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(' | ')})`);
};

const trade = (i: number): PaperPosition => ({
  id: `T${i}`, signal_id: `S${i}`, symbol: 'NIFTY', option_type: 'CE', strike_symbol: `NIFTY ${20000 + i} CE`,
  timeframe: '5m', setup_type: 'SETUP_5_OPTION_CHART', entry_time: '09:30:00', exit_time: '09:45:00',
  option_entry: 100, option_sl: 80, option_target_1: 120, option_target_2: 140, lot_size: 75, lots: 1, quantity: 75,
  current_option_price: 110, pnl_points: 10, pnl_rupees: 750, net_pnl: 700, gross_pnl: 750, status: 'CLOSED',
  exit_reason: 'TARGET_2', entry_datetime: '2026-10-16T09:30:00+05:30', exit_datetime: '2026-10-16T09:45:00+05:30',
} as unknown as PaperPosition);

const open: PaperPosition = { ...trade(99), status: 'OPEN', exit_time: undefined, exit_reason: undefined } as PaperPosition;

const portfolio = {
  active_positions: [open], closed_trades: [trade(1), trade(2)], default_lots: 2, auto_trade_enabled: true, setup_modes: {},
} as unknown as PaperPortfolio;

const signal = {
  id: 'S1', symbol: 'NIFTY', timeframe: '5m', setup_type: 'Setup 1: Squeeze', option_type: 'CE', timestamp: '2026-10-16T11:00:00+05:30',
  is_confirmed: true, entry_price: 100,
  strike_recommendation: { strike_symbol: 'NIFTY 24000 CE', lot_size: 75, estimated_option_entry: 100, option_sl_price: 70, option_sl_pts: 30, option_target_1_price: 140, option_target_1_pts: 40 },
  indicators_snapshot: { rsi: 61, bandwidth: 2.1 },
} as unknown as Signal;

const state = { signals: [signal], radar: {}, market_bias: 'NEUTRAL', active_mode: 'live', paper_portfolio: portfolio } as unknown as ScannerState;

describe('axe: no structural accessibility violations', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(
    String(url).includes('/costs')
      ? JSON.stringify({ totals: { trades: 0, gross_before_slippage: 0, slippage: 0, charges: 0, net: 0 }, trades: [], by_day: [], by_setup: [], by_symbol: [], by_premium: [] })
      : '[]',
    { status: 200 },
  ))));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('header with tabs', async () => {
    // The tab panel lives in App; stand in for it so aria-controls resolves.
    const { container } = render(
      <ThemeProvider><DhanAuthProvider>
        <div id="main-panel" role="tabpanel" aria-label="Watch" />
        <Header activeMode="live" scanCycleCount={1} lastScanTime="12:00:00" isScanning={false} scanProgress={100}
          onScanNow={vi.fn()} activeTab="scanner" onTabChange={vi.fn()} openPositionsCount={1}
          stream={{ state: 'reconnecting', ageSec: 0 }} />
      </DhanAuthProvider></ThemeProvider>,
    );
    expect(await violations(container)).toEqual([]);
  });

  it('terminal', async () => {
    const noop = vi.fn();
    const { container } = render(
      <Terminal state={state} loaded wsConnected dashboardWatch={null} filters={{ setup: 'ALL', optionType: 'ALL', instrumentType: 'ALL', timeframe: 'ALL' }}
        onFilters={noop} filteredSignals={[signal]} closedTrades={[trade(1)]} activeSignalIds={new Set()} portfolio={portfolio}
        onPaperBuy={noop} onClosePosition={noop} onToggleAutoTrade={noop} onChangeSetupMode={noop} onResetPortfolio={noop}
        onKillSwitch={noop} onScanNow={noop} onOpenAccessKey={noop} sources={[]} trades={[]} tradesError={null}
        loadTradeDetail={vi.fn()} loadTradeChart={vi.fn()} onClosePaperTrade={vi.fn()} onRefreshTrades={noop}
        loadSession={vi.fn()} sessionDay="2026-10-16" />,
    );
    expect(await violations(container)).toEqual([]);
  });

  it('review screen tabs', async () => {
    const h = { onClosePosition: vi.fn(), onToggleAutoTrade: vi.fn(), onChangeSetupMode: vi.fn(), onResetPortfolio: vi.fn() };
    const { container } = render(<ReviewScreen portfolio={portfolio} closedTrades={[trade(1), trade(2)]} {...h} />);
    for (const name of ['Today', 'Trades', 'Setups', 'Costs']) {
      fireEvent.click(screen.getByRole('tab', { name }));
      expect(await violations(container), name).toEqual([]);
    }
  });

  it('earnings tabs', async () => {
    const { container } = render(<EarningsPanel initial={{ positions: [], candidates: [], calendar: [{ symbol: 'TCS', earnings_date: '2026-10-20', session: 'AMC', sector: 'IT', note: '' }] }} />);
    for (const name of [/Positions/, /Signals now/, /Calendar/]) {
      fireEvent.click(screen.getByRole('tab', { name }));
      expect(await violations(container), String(name)).toEqual([]);
    }
  });

  it('settings', async () => {
    const payload: RuntimeSettingsPayload = {
      groups: ['Risk', 'Alerts'],
      settings: [
        { key: 'a', label: 'Daily loss limit', group: 'Risk', type: 'float', unit: 'INR', description: 'Stops entries', value: 1, default: 1, overridden: true, min: 0, max: null, choices: [], zero_disables: true },
        { key: 'b', label: 'Telegram alerts', group: 'Alerts', type: 'bool', unit: '', description: 'Send', value: false, default: false, overridden: false, min: null, max: null, choices: [], zero_disables: false },
      ],
    };
    const { container } = render(<SettingsPanel initial={payload} initialAudit={[]} />);
    expect(await violations(container)).toEqual([]);
    fireEvent.click(screen.getByRole('tab', { name: 'Alerts' }));
    expect(await violations(container)).toEqual([]);
  });

  it('dialog', async () => {
    render(<Dialog label="Test" onClose={vi.fn()}><h3>Hi</h3><button>ok</button></Dialog>);
    expect(await violations(document.body)).toEqual([]);
  });
});
