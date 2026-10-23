import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../api/client';
import { actions, resetInFlight } from './actions';
import { appStore, resetAppStore } from './appStore';
import { alertsHook } from './alertsHook';

const fetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;
const res = (body: unknown, status = 200) => ({ status, ok: status >= 200 && status < 300, json: async () => body }) as Response;
const urls = () => fetchMock.mock.calls.map((c) => String(c[0]));
const portfolio = (extra: Record<string, unknown> = {}) => ({ active_positions: [], closed_trades: [], auto_trade_enabled: true, default_lots: 3, ...extra });

beforeEach(() => {
  resetAppStore();
  resetInFlight();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => (String(url).includes('/paper/portfolio') ? res(portfolio()) : res({})));
});
afterEach(() => { vi.useRealTimers(); });

describe('actions', () => {
  it('paperBuy posts the signal with default lots and refreshes the portfolio', async () => {
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: portfolio({ default_lots: 3 }) as never } }));
    const r = await actions.paperBuy({ id: 's1', symbol: 'NIFTY', option_type: 'CE' } as never);
    expect(r.ok).toBe(true);
    const call = fetchMock.mock.calls.find((c) => String(c[0]) === '/api/paper/trade')!;
    expect(JSON.parse(call[1].body)).toMatchObject({ lots: 3, signal: { id: 's1' } });
    expect(urls()).toContain('/api/paper/portfolio');
  });

  it('closePosition, scanNow and resetPortfolio hit their endpoints', async () => {
    await actions.closePosition('p 1');
    await actions.scanNow();
    await actions.resetPortfolio();
    expect(urls()).toEqual(expect.arrayContaining(['/api/paper/close/p%201', '/api/signals/scan-now', '/api/paper/reset']));
  });

  it('a 401 opens the key dialog', async () => {
    fetchMock.mockImplementation(async () => res({}, 401));
    const r = await actions.scanNow();
    expect(r.ok).toBe(false);
    expect(appStore.getState().ui.needsCapability).toBe(true);
  });

  it('surfaces the server detail as the message', async () => {
    fetchMock.mockImplementation(async () => res({ detail: 'Daily loss cap hit' }, 409));
    const r = await actions.paperBuy({ id: 's', symbol: 'X', option_type: 'CE' } as never);
    expect(r.ok).toBe(false);
    expect(r.message).toContain('Daily loss cap hit');
  });

  it('ignores a second call while the first is in flight', async () => {
    let release: (v: Response) => void = () => {};
    fetchMock.mockImplementation(() => new Promise<Response>((r) => { release = r; }));
    const first = actions.scanNow();
    const second = await actions.scanNow();
    expect(second).toEqual({ ok: false, message: 'Already running' });
    release(res({}));
    expect((await first).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('killSwitch(true) reports positions that failed to close', async () => {
    fetchMock.mockImplementation(async (url: string) => (String(url).includes('kill-switch') ? res({ failed: ['NIFTY 24500 CE'] }) : res(portfolio())));
    const r = await actions.killSwitch(true);
    expect(r.ok).toBe(true);
    expect(r.failed).toEqual(['NIFTY 24500 CE']);
    expect(r.message).toContain('NIFTY 24500 CE');
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes('kill-switch'))!;
    expect(JSON.parse(call[1].body)).toEqual({ confirm: true });
  });

  it('killSwitch(false) uses the release route', async () => {
    await actions.killSwitch(false);
    expect(urls()).toContain('/api/paper/kill-switch/release');
  });

  it('a timeout reports an unknown outcome and refetches', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((url: string, init: RequestInit) => new Promise<Response>((resolve, reject) => {
      if (String(url).includes('/paper/portfolio')) { resolve(res(portfolio())); return; }
      init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    }));
    const p = actions.killSwitch(true);
    await vi.advanceTimersByTimeAsync(10_500);
    const r = await p;
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/Outcome unknown/);
    expect(urls()).toContain('/api/paper/portfolio');
  });

  it('toggleAutoTrade fails when the refetch shows the state unchanged', async () => {
    fetchMock.mockImplementation(async (url: string) => (String(url).includes('/paper/portfolio') ? res(portfolio({ auto_trade_enabled: false })) : res({})));
    const r = await actions.toggleAutoTrade(true);
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/did not apply/);
    const ok = await actions.toggleAutoTrade(false);
    expect(ok.ok).toBe(true);
  });

  it('settings, live and earnings actions call the right routes and methods', async () => {
    await actions.updateSettings({ a: 1 });
    await actions.resetSetting('max_open');
    await actions.live.setMode('dry_run');
    await actions.live.enable('123456', 'ENABLE LIVE TRADING');
    await actions.earnings.deleteCalendarRow('TCS', '2026-10-25');
    await actions.journal.save('t1', { note: 'x' });
    const calls = fetchMock.mock.calls.map((c) => `${c[1]?.method ?? 'GET'} ${c[0]}`);
    expect(calls).toEqual(expect.arrayContaining([
      'PUT /api/settings', 'POST /api/settings/max_open/reset', 'POST /api/live/mode', 'POST /api/live/enable',
      'DELETE /api/earnings/calendar/TCS/2026-10-25', 'PUT /api/journal/trades/t1',
    ]));
  });

  it('reports each outcome to the alerts hook', async () => {
    const sink = vi.fn();
    const off = alertsHook.setSink(sink);
    await actions.scanNow();
    fetchMock.mockImplementation(async () => res({ detail: 'nope' }, 400));
    await actions.resetPortfolio();
    off();
    expect(sink.mock.calls.map((c) => c[0].severity)).toEqual(['info', 'warning']);
  });
});
