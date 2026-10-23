import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { renderPanel, pos, signal } from '../test/panelHarness';
import { appStore, markError, markReady, resetAppStore } from '../data/appStore';
import { resetInFlight } from '../data/actions';
import * as actionsModule from '../data/actions';
import { axeCheck } from '../test/axe';
import { PANELS } from './registry';
import type { PanelProps } from './registry';

const load = async (id: string): Promise<React.ComponentType<PanelProps>> => {
  const def = PANELS.find((d) => d.id === id)!;
  const mod = await (def.component as unknown as { _payload: { _result: () => Promise<{ default: React.ComponentType<PanelProps> }> } })._payload._result();
  return mod.default;
};

const portfolio = (over: Record<string, unknown> = {}) => ({
  active_positions: [pos()], auto_trade_enabled: true, default_lots: 2, total_net_pnl: 100, total_unrealized_net: 50,
  win_rate_pct: 50, winning_trades_count: 1, losing_trades_count: 1, total_slippage_cost: 0, total_charges: 0, setup_modes: {},
  risk: { kill_switch_active: false, loss_cap_tripped: false, daily_loss_limit: 24000, day_pnl: 0 }, ...over,
}) as never;

const seed = () => {
  appStore.setState((s) => ({
    scanner: { ...s.scanner, signals: [signal(), signal({ id: 'S3M', timeframe: '3m', strike_symbol: undefined })], paper_portfolio: portfolio(), radar: {} },
  }));
  markReady('scanner'); markReady('portfolio');
};

beforeEach(() => {
  resetAppStore(); resetInFlight();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', { status: 500 }));
});
afterEach(() => vi.restoreAllMocks());

describe('signals panel', () => {
  it('signals renders rows', async () => {
    seed();
    renderPanel(await load('signals'));
    expect(screen.getAllByRole('button', { name: /Inspect NIFTY 24500 CE/ }).length).toBeGreaterThan(0);
  });
  it('signals shows empty state', async () => {
    markReady('scanner');
    renderPanel(await load('signals'));
    expect(screen.getByText(/No active signals match/)).toBeTruthy();
  });
  it('signals shows a 3m signal when 3m is chosen', async () => {
    appStore.setState((s) => ({ scanner: { ...s.scanner, signals: [signal({ id: 'A', timeframe: '3m' }), signal({ id: 'B', timeframe: '5m', strike_recommendation: { ...(signal() as never as { strike_recommendation: object }).strike_recommendation, strike_symbol: 'FIVE' } })] } }));
    markReady('scanner');
    const C = await load('signals');
    const { setParams, rerenderWith } = renderPanel(C);
    fireEvent.click(screen.getByRole('button', { name: '3m' }));
    expect(setParams).toHaveBeenCalled();
    rerenderWith(setParams.mock.calls[setParams.mock.calls.length - 1][0]);
    expect(screen.queryByText('FIVE')).toBeNull();
    expect(screen.getAllByRole('button', { name: /Inspect/ })).toHaveLength(1);
  });
  it('signals selection updates the store', async () => {
    seed();
    renderPanel(await load('signals'));
    fireEvent.click(screen.getAllByRole('button', { name: /Inspect NIFTY 24500 CE/ })[0]);
    expect(appStore.getState().selection).toEqual({ kind: 'signal', id: 'S1' });
  });
  it('signals marks stale', async () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-22T04:00:00Z'));
    seed();
    renderPanel(await load('signals'));
    act(() => { vi.advanceTimersByTime(70_000); });
    expect(screen.getByTestId('panel-stale')).toBeTruthy();
    vi.useRealTimers();
  });
  it('signals shows an error strip', async () => {
    seed(); markError('scanner', 'boom');
    renderPanel(await load('signals'));
    expect(screen.getByText(/boom/)).toBeTruthy();
  });
  it('signals passes axe', async () => {
    seed();
    const { container } = renderPanel(await load('signals'));
    expect(await axeCheck(container)).toEqual([]);
  });
});

describe('positions panels', () => {
  it('positions renders rows and toggles auto-enter via actions', async () => {
    seed();
    const spy = vi.spyOn(actionsModule.actions, 'toggleAutoTrade').mockResolvedValue({ ok: true, message: '' });
    renderPanel(await load('positions'));
    expect(screen.getByLabelText('Open NIFTY 24500 CE position')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Auto-enter/ }));
    expect(spy).toHaveBeenCalledWith(false);
  });
  it('positions asks for confirmation before closing and calls actions.closePosition', async () => {
    seed();
    const spy = vi.spyOn(actionsModule.actions, 'closePosition').mockResolvedValue({ ok: true, message: '' });
    renderPanel(await load('positions'));
    fireEvent.click(screen.getByRole('button', { name: 'Close NIFTY 24500 CE' }));
    const dlg = await screen.findByRole('dialog');
    expect(dlg.textContent).toMatch(/NIFTY 24500 CE/);
    expect(dlg.textContent).toMatch(/Net if closed/);
    expect(spy).not.toHaveBeenCalled();
    fireEvent.click(within(dlg).getByRole('button', { name: 'Close position' }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('P1'));
  });
  it('positions cancel does not close', async () => {
    seed();
    const spy = vi.spyOn(actionsModule.actions, 'closePosition');
    renderPanel(await load('positions'));
    fireEvent.click(screen.getByRole('button', { name: 'Close NIFTY 24500 CE' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(spy).not.toHaveBeenCalled();
  });
  it('positions-table renders rows, empty state and axe', async () => {
    seed();
    const C = await load('positions-table');
    const { container, unmount } = renderPanel(C);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getAllByText('NIFTY 24500 CE').length).toBeGreaterThan(0);
    expect(await axeCheck(container)).toEqual([]);
    unmount();
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: portfolio({ active_positions: [] }) } }));
    renderPanel(C);
    expect(screen.getByText(/No open/)).toBeTruthy();
  });
  it('positions-table close goes through the confirm dialog', async () => {
    seed();
    const spy = vi.spyOn(actionsModule.actions, 'closePosition').mockResolvedValue({ ok: true, message: '' });
    renderPanel(await load('positions-table'));
    fireEvent.click(screen.getAllByRole('button', { name: /Close NIFTY 24500 CE/ })[0]);
    expect(spy).not.toHaveBeenCalled();
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Close position' }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('P1'));
  });
});

describe('focus, chart, market panels', () => {
  it('focus follows the selected position and pins', async () => {
    seed();
    appStore.setState({ selection: { kind: 'position', id: 'P1' } });
    const { setParams } = renderPanel(await load('focus'));
    expect(screen.getAllByText(/NIFTY 24500 CE/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Pin/ }));
    expect(setParams).toHaveBeenCalledWith(expect.objectContaining({ pinned: true, subject: { kind: 'position', id: 'P1' } }));
  });
  it('focus pinned subject ignores later selection', async () => {
    seed();
    appStore.setState({ selection: { kind: 'signal', id: 'S1' } });
    renderPanel(await load('focus'), { params: { pinned: true, subject: { kind: 'position', id: 'P1' } } });
    act(() => { appStore.setState({ selection: { kind: 'signal', id: 'S3M' } }); });
    expect(screen.getByRole('button', { name: /Unpin/ })).toBeTruthy();
  });
  it('chart asks for a selection when none', async () => {
    resetAppStore();
    renderPanel(await load('chart'));
    expect(screen.getByText(/Select an open position/)).toBeTruthy();
  });
  it('market renders', async () => {
    seed();
    const { container } = renderPanel(await load('market'));
    expect(container.firstChild).toBeTruthy();
  });
});

describe('controls panel', () => {
  it('controls calls actions for auto-enter, scan, setup mode', async () => {
    seed();
    const auto = vi.spyOn(actionsModule.actions, 'toggleAutoTrade').mockResolvedValue({ ok: true, message: '' });
    const scan = vi.spyOn(actionsModule.actions, 'scanNow').mockResolvedValue({ ok: true, message: '' });
    const mode = vi.spyOn(actionsModule.actions, 'setSetupMode').mockResolvedValue({ ok: true, message: '' });
    renderPanel(await load('controls'));
    fireEvent.click(screen.getByRole('button', { name: /Auto-enter/ }));
    expect(auto).toHaveBeenCalledWith(false);
    fireEvent.click(screen.getByRole('button', { name: 'Scan now' }));
    expect(scan).toHaveBeenCalled();
    const group = screen.getByRole('group', { name: 'Setup 1 · BB Squeeze mode' });
    fireEvent.click(within(group).getByRole('button', { name: 'Off' }));
    expect(mode).toHaveBeenCalledWith('1', 'off');
  });
  it('controls reset needs confirmation', async () => {
    seed();
    const reset = vi.spyOn(actionsModule.actions, 'resetPortfolio').mockResolvedValue({ ok: true, message: '' });
    renderPanel(await load('controls'));
    fireEvent.click(screen.getByRole('button', { name: 'Reset portfolio' }));
    const dlg = await screen.findByRole('dialog');
    expect(reset).not.toHaveBeenCalled();
    fireEvent.click(within(dlg).getByRole('button', { name: 'Reset portfolio' }));
    await waitFor(() => expect(reset).toHaveBeenCalled());
  });
  it('controls opens the dashboard key dialog', async () => {
    seed();
    renderPanel(await load('controls'));
    fireEvent.click(screen.getByRole('button', { name: 'Dashboard key' }));
    expect(appStore.getState().ui.needsCapability).toBe(true);
  });
  it('controls passes axe', async () => {
    seed();
    const { container } = renderPanel(await load('controls'));
    expect(await axeCheck(container)).toEqual([]);
  });
});

describe('fetch-backed panels', () => {
  const ids = ['trades', 'session', 'journal', 'earnings', 'settings', 'live', 'telemetry', 'costs', 'setup-stats'];
  for (const id of ids) {
    it(`${id} renders inside the frame without crashing`, async () => {
      const C = await load(id);
      const { container } = renderPanel(C);
      expect(container.querySelector('[role="region"]')).toBeTruthy();
      await act(async () => { await Promise.resolve(); });
    });
  }
  it('trades shows rows from the store', async () => {
    appStore.setState({ trades: [{ id: 't1', book: 'paper', display_book: 'Main', instrument: 'NIFTY 24500 CE', setup: 'S1', status: 'CLOSED', source_id: 'P9', net_pnl: 10 } as never] });
    markReady('trades');
    renderPanel(await load('trades'));
    expect(screen.getAllByText(/NIFTY 24500 CE/).length).toBeGreaterThan(0);
  });
  it('journal has an end-of-day report button that requests today summary', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-22T04:00:00Z'));
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (u) => (String(u).includes('summary.html') ? new Response('<html></html>', { status: 200 }) : new Response('[]', { status: 200 })));
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:x';
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
    renderPanel(await load('journal'));
    fireEvent.click(screen.getByRole('button', { name: 'End-of-day report' }));
    await waitFor(() => expect(fetchSpy.mock.calls.some(([u]) => String(u).includes('/api/journal/summary.html?day=2026-10-22'))).toBe(true));
    vi.useRealTimers();
  });
});

describe('journal url helpers', () => {
  it('build export and report urls', async () => {
    const m = await import('./journal');
    expect(m.journalCsvUrl('2026-10-22', '2026-10-22')).toBe('/api/journal/export.csv?start=2026-10-22&end=2026-10-22');
    expect(m.eodReportUrl('2026-10-22')).toBe('/api/journal/summary.html?day=2026-10-22');
  });
});
