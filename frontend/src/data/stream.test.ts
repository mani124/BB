import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../api/client';
import { appStore, resetAppStore } from './appStore';
import { startStream } from './stream';

class FakeES {
  static instances: FakeES[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeES.instances.push(this); }
  addEventListener(name: string, fn: (e: MessageEvent) => void) { (this.listeners[name] ??= []).push(fn); }
  close() { this.closed = true; }
  emit(name: string, data: string) { (this.listeners[name] ?? []).forEach((f) => f({ data } as MessageEvent)); }
  message(data: unknown) { this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent); }
}

const snap = (extra: Record<string, unknown> = {}) => ({
  signals: [{ id: 's1', symbol: 'NIFTY' }], radar: { NIFTY: { symbol: 'NIFTY', close: 100 } },
  last_scan_time: '', scan_cycle_count: 1, is_scanning: false, scan_progress: 0, universe_count: 3, active_mode: 'live',
  paper_portfolio: { closed_trades_count: 1, active_positions: [], closed_trades: [] }, ...extra,
});

const mockFetch = (responder: (url: string) => { status?: number; body?: unknown }) => {
  (apiFetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (url: string) => {
    const r = responder(String(url));
    const status = r.status ?? 200;
    return { status, ok: status >= 200 && status < 300, json: async () => r.body } as Response;
  });
};

async function boot(opts = {}) {
  const stop = startStream(opts);
  await vi.advanceTimersByTimeAsync(0);
  return { stop, es: () => FakeES.instances[FakeES.instances.length - 1] };
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeES.instances = [];
  (globalThis as unknown as { EventSource: unknown }).EventSource = FakeES;
  resetAppStore();
  mockFetch((url) => (url.includes('/paper/portfolio') ? { body: { closed_trades: [{ id: 'c1' }] } } : { body: snap() }));
});
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe('startStream', () => {
  it('populates scanner from a snapshot and goes live', async () => {
    const { stop, es } = await boot();
    es().message(snap({ scan_cycle_count: 7 }));
    const s = appStore.getState();
    expect(s.scanner.scan_cycle_count).toBe(7);
    expect(s.meta.scanner.status).toBe('ready');
    expect(s.stream.state).toBe('live');
    stop();
  });

  it('coalesces ticks and keeps the last value', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    for (let i = 1; i <= 50; i++) es().emit('tick', JSON.stringify({ symbol: 'NIFTY', ltp: 100 + i }));
    expect(appStore.getState().scanner.radar.NIFTY.close).toBe(100);
    const spy = vi.fn();
    appStore.subscribe(spy);
    await vi.advanceTimersByTimeAsync(300);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(appStore.getState().scanner.radar.NIFTY.close).toBe(150);
    stop();
  });

  it('ignores option ticks', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    es().emit('tick', JSON.stringify({ symbol: 'NIFTY', ltp: 999, is_option: true }));
    await vi.advanceTimersByTimeAsync(300);
    expect(appStore.getState().scanner.radar.NIFTY.close).toBe(100);
    stop();
  });

  it('keeps previous state on malformed JSON and records the error', async () => {
    const { stop, es } = await boot();
    es().message(snap({ scan_cycle_count: 3 }));
    expect(() => es().message('{not json')).not.toThrow();
    const s = appStore.getState();
    expect(s.scanner.scan_cycle_count).toBe(3);
    expect(s.meta.stream.error).toMatch(/Malformed/);
    stop();
  });

  it('keeps object identity for duplicate snapshots', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    const first = appStore.getState().scanner.signals;
    es().message(snap());
    expect(appStore.getState().scanner.signals).toBe(first);
    stop();
  });

  it('turns stale after 16 s of silence', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    await vi.advanceTimersByTimeAsync(16_500);
    const s = appStore.getState();
    expect(s.stream.state).toBe('stale');
    expect(s.meta.stream.status).toBe('stale');
    es().message(snap());
    expect(appStore.getState().stream.state).toBe('live');
    expect(appStore.getState().meta.stream.status).toBe('ready');
    stop();
  });

  it('reconnects once after 3 s even under an error storm', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    const first = es();
    for (let i = 0; i < 20; i++) first.onerror?.();
    expect(appStore.getState().stream.state).toBe('reconnecting');
    expect(first.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(3100);
    expect(FakeES.instances.length).toBe(2);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(FakeES.instances.length).toBe(2);
    stop();
  });

  it('refetches closed trades only when the count or mode changes', async () => {
    const { stop, es } = await boot();
    const closedCalls = () => (apiFetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter((c) => String(c[0]).includes('/paper/portfolio')).length;
    es().message(snap());
    await vi.advanceTimersByTimeAsync(0);
    const n = closedCalls();
    expect(n).toBe(1);
    es().message(snap({ scan_cycle_count: 9 }));
    await vi.advanceTimersByTimeAsync(0);
    expect(closedCalls()).toBe(n);
    es().message(snap({ paper_portfolio: { closed_trades_count: 2, active_positions: [], closed_trades: [] } }));
    await vi.advanceTimersByTimeAsync(0);
    expect(closedCalls()).toBe(n + 1);
    expect(appStore.getState().closedTrades).toEqual([{ id: 'c1' }]);
    stop();
  });

  it('flags a missing capability on 401', async () => {
    mockFetch(() => ({ status: 401, body: {} }));
    const { stop } = await boot();
    expect(appStore.getState().ui.needsCapability).toBe(true);
    expect(FakeES.instances.length).toBe(0);
    stop();
  });

  it('stop() closes the source and clears timers', async () => {
    const { stop, es } = await boot();
    es().message(snap());
    const src = es();
    stop();
    expect(src.closed).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
