import type { Page } from '@playwright/test';

export const position = (id = 'pos-1') => ({
  id, signal_id: 'sig-1', symbol: 'NIFTY', option_type: 'CE', strike_symbol: 'NIFTY 22000 CE', timeframe: '5m', setup_type: 'SETUP_1', entry_time: '10:15',
  underlying_entry: 22000, underlying_sl: 21950, underlying_target_1: 22050, underlying_target_2: 22100, option_entry: 100, option_sl: 80, option_target_1: 120, option_target_2: 140,
  lot_size: 50, lots: 1, quantity: 50, current_underlying: 22010, current_option_price: 105, pnl_points: 5, pnl_rupees: 250, status: 'OPEN', est_net_pnl: 200,
});

export const snapshot = (positions: unknown[] = [], extra: Record<string, unknown> = {}) => ({
  signals: [], radar: {}, last_scan_time: new Date().toISOString(), scan_cycle_count: 1, is_scanning: false, scan_progress: 100, universe_count: 10,
  active_mode: 'demo', feed_status: 'WS_LIVE',
  paper_portfolio: {
    active_positions: positions, closed_trades: [], closed_trades_count: 0, auto_trade_enabled: false, default_lots: 1, total_realized_pnl: 0, total_unrealized_pnl: 0, total_pnl: 0,
    win_rate_pct: 0, total_trades_count: 0, winning_trades_count: 0, losing_trades_count: 0,
    risk: { daily_loss_limit: 24000, day_pnl: 0, loss_cap_tripped: false, kill_switch_active: false, entries_blocked: false },
  },
  ...extra,
});

/** Replaces EventSource with one that sends `data` once and then, if `keepAlive`, again every second. Returns nothing; call before goto. */
export async function installFakeStream(page: Page, data: unknown, keepAlive: boolean): Promise<void> {
  await page.route('**/api/signals', (route) => route.fulfill({ json: data }));
  await page.addInitScript(({ payload, alive }) => {
    class FakeSource {
      listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;
      timer = 0;
      constructor() {
        const send = () => this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }));
        window.setTimeout(send, 50);
        if (alive) this.timer = window.setInterval(send, 1000);
      }
      addEventListener(t: string, f: (e: MessageEvent) => void) { (this.listeners[t] ??= []).push(f); }
      close() { clearInterval(this.timer); }
    }
    (window as unknown as { EventSource: unknown }).EventSource = FakeSource;
  }, { payload: data, alive: keepAlive });
}
