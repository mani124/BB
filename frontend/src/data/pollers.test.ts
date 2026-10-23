import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../api/client';
import { appStore, resetAppStore } from './appStore';
import { startPollers, onAnalyticsRefresh } from './pollers';

const fetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;
const calls = (frag: string) => fetchMock.mock.calls.filter((c) => String(c[0]).includes(frag)).length;
const ok = (body: unknown, status = 200) => ({ status, ok: status < 300, json: async () => body }) as Response;

function setHidden(v: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => v });
  document.dispatchEvent(new Event('visibilitychange'));
}

beforeEach(() => {
  vi.useFakeTimers();
  resetAppStore();
  setHidden(false);
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).includes('/live/status')) return ok({ mode: 'off' });
    return ok([]);
  });
});
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe('startPollers', () => {
  it('polls trades at its interval', async () => {
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    expect(calls('/dashboard/trades')).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(calls('/dashboard/trades')).toBe(2);
    stop();
  });

  it('keeps previous data and records the error when a poll fails', async () => {
    fetchMock.mockImplementation(async (url: string) => (String(url).includes('/dashboard/trades') ? ok([{ id: 't1' }]) : ok({})));
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    expect(appStore.getState().trades).toEqual([{ id: 't1' }]);
    fetchMock.mockImplementation(async () => ok({}, 500));
    await vi.advanceTimersByTimeAsync(30_000);
    const s = appStore.getState();
    expect(s.trades).toEqual([{ id: 't1' }]);
    expect(s.meta.trades.status).toBe('error');
    expect(s.meta.trades.error).toMatch(/500/);
    stop();
  });

  it('pauses while hidden and fetches immediately when visible again', async () => {
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    setHidden(true);
    const before = calls('/dashboard/trades');
    await vi.advanceTimersByTimeAsync(95_000);
    expect(calls('/dashboard/trades')).toBe(before);
    setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(calls('/dashboard/trades')).toBe(before + 1);
    stop();
  });

  it('polls live status slowly while routing is off and faster when on', async () => {
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    expect(calls('/live/status')).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(calls('/live/status')).toBe(1);
    stop();

    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/live/status')) return ok({ mode: 'dry_run' });
      if (String(url).includes('/live/orders')) return ok([{ id: 'o1' }]);
      return ok([]);
    });
    vi.clearAllMocks();
    resetAppStore();
    const stop2 = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    expect(calls('/live/status')).toBe(1);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(calls('/live/status')).toBe(2);
    expect(appStore.getState().live.orders).toEqual([{ id: 'o1' }]);
    stop2();
  });

  it('stop() clears every timer', async () => {
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    stop();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('one failing poller does not stop the others', async () => {
    fetchMock.mockImplementation(async (url: string) => (String(url).includes('/readiness') ? ok({}, 500) : ok([])));
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(calls('/readiness')).toBe(2);
    expect(calls('/recorder/status')).toBe(2);
    expect(calls('/dashboard/watch')).toBeGreaterThanOrEqual(2);
    stop();
  });

  it('runs registered analytics refreshers on their cadence', async () => {
    const fn = vi.fn();
    const off = onAnalyticsRefresh(fn);
    const stop = startPollers();
    await vi.advanceTimersByTimeAsync(0);
    expect(fn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fn).toHaveBeenCalledTimes(2);
    off();
    stop();
  });
});
