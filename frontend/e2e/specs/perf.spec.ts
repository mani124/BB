import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';

const SECONDS = Number(process.env.PERF_SECONDS ?? 60);

const signal = (i: number) => ({
  id: `perf-${i}`, symbol: ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS', 'INFY'][i % 5], timeframe: ['3m', '5m', '15m'][i % 3], setup_type: 'SETUP_1', option_type: i % 2 ? 'CE' : 'PE',
  timestamp: new Date(Date.now() - i * 1000).toISOString(), is_confirmed: true, entry_price: 100 + i, stop_loss: 95 + i, target_1: 110 + i, target_2: 120 + i,
  strike_recommendation: { strike: 22000 + i, option_type: i % 2 ? 'CE' : 'PE', symbol: `NIFTY${22000 + i}` },
  indicators_snapshot: { close: 100, bb_upper: 105, bb_middle: 100, bb_lower: 95, bandwidth: 0.1, percent_b: 0.5, vwap: 100, rsi: 55, ema_9: 100, adx: 25 }, rationale: 'perf fixture',
});
const trade = (i: number) => ({
  id: `t-${i}`, book: 'paper', display_book: 'Paper', source_id: `s-${i}`, status: 'CLOSED', instrument: `NIFTY${22000 + i}CE`, setup: 'SETUP_1',
  opened_at: new Date(Date.now() - 3_600_000).toISOString(), closed_at: new Date(Date.now() - 1_800_000).toISOString(), mode: 'demo', net_pnl: (i % 7) * 100 - 200,
  net_kind: 'realized', evidence_state: 'recorded', exit_reason: 'TARGET_1',
});

test('300 signals, 200 trades and 10 ticks a second for a minute stay smooth and do not leak', async ({ page }) => {
  test.setTimeout((SECONDS + 90) * 1000);
  await new DashboardPage(page).injectAuthKey(getDashboardKey());
  await resetServerLayouts(page, getDashboardKey());
  const signals = Array.from({ length: 300 }, (_, i) => signal(i));
  await page.route('**/api/signals', (route) => route.fulfill({ json: { signals, radar: {}, last_scan_time: new Date().toISOString(), scan_cycle_count: 1, is_scanning: false, scan_progress: 100, universe_count: 300, active_mode: 'demo', feed_status: 'WS_LIVE' } }));
  await page.route('**/api/dashboard/trades', (route) => route.fulfill({ json: Array.from({ length: 200 }, (_, i) => trade(i)) }));
  await page.addInitScript((snapshotSignals) => {
    const w = window as unknown as { __longTasks: number[] };
    w.__longTasks = [];
    try { new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__longTasks.push(e.duration); }).observe({ entryTypes: ['longtask'] }); } catch { /* unsupported */ }
    // A fake stream: one snapshot a second, ten index ticks a second.
    class FakeSource {
      listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;
      timers: number[] = [];
      constructor() {
        const fire = (type: string, data: unknown) => { const ev = new MessageEvent(type, { data: JSON.stringify(data) }); if (type === 'message') this.onmessage?.(ev); (this.listeners[type] ?? []).forEach((f) => f(ev)); };
        let n = 0;
        this.timers.push(window.setInterval(() => fire('message', { signals: snapshotSignals, radar: {}, last_scan_time: new Date().toISOString(), scan_cycle_count: ++n, is_scanning: false, scan_progress: 100, universe_count: 300, active_mode: 'demo', feed_status: 'WS_LIVE' }), 1000));
        this.timers.push(window.setInterval(() => fire('tick', { symbol: 'NIFTY', ltp: 22000 + Math.random() * 50, is_option: false }), 100));
      }
      addEventListener(t: string, f: (e: MessageEvent) => void) { (this.listeners[t] ??= []).push(f); }
      close() { this.timers.forEach((t) => clearInterval(t)); }
    }
    (window as unknown as { EventSource: unknown }).EventSource = FakeSource;
  }, signals);
  await page.goto('/?shell=dock&workspace=Trading');
  await expect(page.getByRole('tab', { name: 'Signals' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText('300', { exact: true }).first()).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const heap = () => page.evaluate(() => (performance as unknown as { memory: { usedJSHeapSize: number } }).memory.usedJSHeapSize / 1048576);
  const client = await page.context().newCDPSession(page);
  await client.send('HeapProfiler.collectGarbage');
  const before = await heap();
  await page.evaluate(() => { (window as unknown as { __longTasks: number[] }).__longTasks.length = 0; });
  await page.waitForTimeout(SECONDS * 1000);
  await client.send('HeapProfiler.collectGarbage');
  const after = await heap();
  const long = await page.evaluate(() => (window as unknown as { __longTasks: number[] }).__longTasks.filter((d) => d > 100));
  console.log(`heap ${before.toFixed(1)} -> ${after.toFixed(1)} MB, long tasks over 100 ms: ${long.length} ${JSON.stringify(long.map(Math.round))}`);
  expect(long.length).toBeLessThanOrEqual(3);
  expect(after - before).toBeLessThan(30);
  await expect(page.getByTestId('dock-app')).toBeVisible();
});
