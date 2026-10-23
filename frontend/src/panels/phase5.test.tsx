import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { renderPanel, pos } from '../test/panelHarness';
import { appStore, markReady, resetAppStore } from '../data/appStore';
import { PANELS } from './registry';
import type { PanelProps } from './registry';
import { pushAlert } from '../features/alerts/alertsStore';
import { setFilter } from '../data/selection';

const removeChart = vi.fn();
const setData = vi.fn();
vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  createChart: vi.fn(() => ({
    addAreaSeries: () => ({ setData }), addLineSeries: () => ({ setData }), priceScale: () => ({ applyOptions: vi.fn() }), timeScale: () => ({ fitContent: vi.fn() }),
    subscribeCrosshairMove: vi.fn(), applyOptions: vi.fn(), remove: removeChart,
  })),
}));

const load = async (id: string): Promise<React.ComponentType<PanelProps>> => {
  const def = PANELS.find((d) => d.id === id)!;
  const mod = await (def.component as unknown as { _payload: { _result: () => Promise<{ default: React.ComponentType<PanelProps> }> } })._payload._result();
  return mod.default;
};

type Routes = Record<string, unknown | ((url: string) => Response | unknown)>;
let calls: string[] = [];
const mockFetch = (routes: Routes) => {
  calls = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    calls.push(url);
    const key = Object.keys(routes).find((k) => url.includes(k));
    if (!key) return new Response('{}', { status: 500 });
    const v = routes[key];
    const out = typeof v === 'function' ? (v as (u: string) => unknown)(url) : v;
    if (out instanceof Response) return out;
    return new Response(JSON.stringify(out), { status: 200 });
  });
};

const GEN = '2026-10-22T10:00:00+05:30';
const risk = (over: Record<string, unknown> = {}) => ({
  open: [{ id: 'a', symbol: 'NIFTY', strike_symbol: 'NIFTY 24500 CE', side: 'CE', setup: 'Setup 1', pool: 'main', qty: 75, entry: 100, stop: 90, risk_rupees: 750, notional: 7500, distance_pct: 4.5, t1: 120 }],
  totals: { risk_rupees: 750, notional: 7500, count: 1, max_open: 5, max_open_key: 'max_open_positions' },
  by_underlying: [{ key: 'NIFTY', count: 1, risk_rupees: 750, notional: 7500 }], by_side: [{ key: 'CE', count: 1, risk_rupees: 750, notional: 7500 }], by_pool: [{ key: 'main', count: 1, risk_rupees: 750, notional: 7500 }], by_setup: [{ key: 'Setup 1', count: 1, risk_rupees: 750, notional: 7500 }],
  generated_at: GEN, ...over,
});
const portfolio = (riskOver: Record<string, unknown> = {}, over: Record<string, unknown> = {}) => ({
  active_positions: [pos()], auto_trade_enabled: true, closed_trades: [],
  risk: { daily_loss_limit: 24000, day_pnl: -6000, loss_cap_tripped: false, kill_switch_active: false, entries_blocked: false, ...riskOver }, ...over,
}) as never;
const seedPortfolio = (riskOver: Record<string, unknown> = {}, over: Record<string, unknown> = {}) => {
  appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: portfolio(riskOver, over) }, stream: { state: 'live', ageSec: 0 } }));
  markReady('portfolio');
};

beforeEach(() => { resetAppStore(); removeChart.mockClear(); vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', { status: 500 })); try { localStorage.clear(); } catch { /* none */ } });
afterEach(() => vi.restoreAllMocks());

describe('risk panel', () => {
  it('shows the cap meter with ARIA values and an Allowed or Blocked state', async () => {
    seedPortfolio();
    mockFetch({ '/api/analytics/risk': risk() });
    renderPanel(await load('risk'));
    const meter = await screen.findByRole('meter');
    expect(meter).toHaveAttribute('aria-valuenow', '25');
    expect(meter).toHaveAttribute('aria-valuemin', '0');
    expect(meter).toHaveAttribute('aria-valuemax', '100');
    expect(await screen.findByText('NIFTY 24500 CE')).toBeTruthy();
    expect(screen.getAllByText('₹750').length).toBeGreaterThan(0);
    expect(screen.getByText(/1 of 5/)).toBeTruthy();
    expect(screen.getByText(/max_open_positions/)).toBeTruthy();
  });
  it('says Loss cap off when the cap is 0', async () => {
    seedPortfolio({ daily_loss_limit: 0 });
    mockFetch({ '/api/analytics/risk': risk() });
    renderPanel(await load('risk'));
    expect(await screen.findByText(/Loss cap off/)).toBeTruthy();
    expect(screen.queryByRole('meter')).toBeNull();
  });
  it.each([
    [{ kill_switch_active: true }, {}, 'kill_switch'],
    [{ loss_cap_tripped: true, loss_cap_reason: 'Cap hit' }, {}, 'loss_cap'],
    [{ capped_pools: ['S11'] }, {}, 'capped_pools'],
    [{}, { auto_trade_enabled: false }, 'auto_enter_off'],
  ])('renders the block reason %#', async (riskOver, over, code) => {
    seedPortfolio(riskOver, over);
    mockFetch({ '/api/analytics/risk': risk() });
    const { container } = renderPanel(await load('risk'));
    await screen.findByText('NIFTY 24500 CE');
    expect(container.querySelector(`[data-reason="${code}"]`)).not.toBeNull();
  });
  it('renders max-open, market-closed and stale-stream reasons', async () => {
    seedPortfolio();
    appStore.setState({ stream: { state: 'stale', ageSec: 30 } });
    mockFetch({ '/api/analytics/risk': risk({ totals: { risk_rupees: 0, notional: 0, count: 5, max_open: 5, max_open_key: 'max_open_positions' } }) });
    const { container } = renderPanel(await load('risk'));
    await screen.findByText('NIFTY 24500 CE');
    expect(container.querySelector('[data-reason="max_open"]')).not.toBeNull();
    expect(container.querySelector('[data-reason="stream_stale"]')).not.toBeNull();
    expect(screen.getByText('Blocked')).toBeTruthy();
  });
  it('says there are no open positions', async () => {
    seedPortfolio();
    mockFetch({ '/api/analytics/risk': risk({ open: [], totals: { risk_rupees: 0, notional: 0, count: 0, max_open: 5, max_open_key: 'max_open_positions' } }) });
    renderPanel(await load('risk'));
    expect(await screen.findByText(/No open positions/)).toBeTruthy();
  });
  it('shows an error strip with Retry, then the data once the server answers', async () => {
    seedPortfolio();
    mockFetch({});
    renderPanel(await load('risk'));
    expect(await screen.findByText(/Could not load open risk/)).toBeTruthy();
    mockFetch({ '/api/analytics/risk': risk() });
    fireEvent.click(screen.getAllByRole('button', { name: /Retry/ })[0]);
    expect(await screen.findByText('NIFTY 24500 CE')).toBeTruthy();
    expect(screen.queryByText(/Could not load open risk/)).toBeNull();
  });
});

describe('exposure panel', () => {
  const two = (a: number, b: number) => risk({
    open: [risk().open[0], { ...risk().open[0], id: 'b' }],
    by_underlying: [{ key: 'NIFTY', count: 1, risk_rupees: 1, notional: a }, { key: 'BANKNIFTY', count: 1, risk_rupees: 1, notional: b }], by_side: [], by_pool: [], by_setup: [],
  });
  it('shows a concentration banner at the threshold and not below it', async () => {
    mockFetch({ '/api/analytics/risk': two(50, 50) });
    const { unmount } = renderPanel(await load('exposure'));
    expect(await screen.findByText(/Concentrated: NIFTY is 50% of premium by underlying/)).toBeTruthy();
    unmount();
    mockFetch({ '/api/analytics/risk': two(49.9, 50.1) });
    renderPanel(await load('exposure'), { params: { concentrationPct: 51 } });
    await screen.findByLabelText('Exposure By underlying');
    expect(screen.queryByText(/Concentrated/)).toBeNull();
  });
  it('validates the threshold to 10..100', async () => {
    mockFetch({ '/api/analytics/risk': two(50, 50) });
    const { setParams } = renderPanel(await load('exposure'), { params: { concentrationPct: 5 } });
    await screen.findByLabelText('Exposure By underlying');
    expect((screen.getByLabelText('Concentration alert threshold percent') as HTMLInputElement).value).toBe('10');
    fireEvent.change(screen.getByLabelText('Concentration alert threshold percent'), { target: { value: '500' } });
    expect(setParams).toHaveBeenLastCalledWith({ concentrationPct: 100 });
  });
  it('shows an empty state', async () => {
    mockFetch({ '/api/analytics/risk': risk({ open: [], by_underlying: [] }) });
    renderPanel(await load('exposure'));
    expect(await screen.findByText(/No open positions, no exposure/)).toBeTruthy();
  });
});

const attr = (n: number, extra: Record<string, unknown> = {}) => ({
  group: 'setup', excluded: 2, generated_at: GEN,
  overall: { trades: n, wins: 1, losses: 1, win_rate: 50, net_pnl: 500, gross_pnl: 600, charges: 80, slippage_cost: 20, expectancy: 250, profit_factor: 1.5, avg_r: 0.4, max_drawdown: 300, low_sample: n < 20 },
  buckets: [
    { key: 'Setup 1', trades: n, win_rate: 50, net_pnl: 500, gross_pnl: 600, charges: 80, slippage_cost: 20, cost_drag_pct: 16.7, expectancy: 250, profit_factor: 1.5, avg_r: 0.4, max_drawdown: 300, low_sample: n < 20 },
    { key: 'Setup 2', trades: 30, win_rate: 40, net_pnl: -200, gross_pnl: -100, charges: 90, slippage_cost: 10, cost_drag_pct: null, expectancy: -6, profit_factor: 0.8, avg_r: -0.1, max_drawdown: 400, low_sample: false },
  ], ...extra,
});
const eq = (points: unknown[] = [{ t: '2026-10-19T10:00:00+05:30', equity: 100, day_pnl: 100, drawdown: 0 }, { t: '2026-10-19T11:00:00+05:30', equity: -50, day_pnl: -50, drawdown: 150 }]) => ({
  points, summary: { net: -50, max_drawdown: 150, current_drawdown: 150, longest_drawdown_days: 0, drawdowns: [{ start: '2026-10-19T10:00:00+05:30', trough: '2026-10-19T11:00:00+05:30', end: null, depth: 150 }] }, generated_at: GEN, excluded: 0,
});

describe('perf-summary panel', () => {
  it('sends IST date bounds for the chosen range and the book', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25), '/api/analytics/equity': eq() });
    const { setParams } = renderPanel(await load('perf-summary'), { params: { range: 'today' } });
    await screen.findByText('Net P&L');
    const url = calls.find((c) => c.includes('/attribution'))!;
    expect(url).toMatch(/from=\d{4}-\d\d-\d\d&to=\d{4}-\d\d-\d\d/);
    expect(url).toContain('book=paper');
    expect(url).toContain('group=setup');
    fireEvent.click(screen.getByRole('button', { name: 'All books' }));
    expect(setParams).toHaveBeenCalledWith(expect.objectContaining({ book: 'all' }));
  });
  it('does not fetch for an invalid custom range and says why', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25), '/api/analytics/equity': eq() });
    renderPanel(await load('perf-summary'), { params: { range: 'custom', from: '2026-10-20', to: '2026-10-19' } });
    expect(await screen.findByRole('alert')).toHaveTextContent(/must not be after/);
    expect(calls).toEqual([]);
  });
  it('shows the KPI row and a low-sample note under 20 trades', async () => {
    mockFetch({ '/api/analytics/attribution': attr(12), '/api/analytics/equity': eq() });
    renderPanel(await load('perf-summary'), { params: { range: 'all' } });
    await screen.findByText('Profit factor');
    for (const k of ['Net P&L', 'Gross P&L', 'Charges', 'Slippage cost', 'Trades', 'Win rate', 'Expectancy', 'Average R', 'Max drawdown']) expect(screen.getByText(k)).toBeTruthy();
    expect(screen.getByRole('note')).toHaveTextContent(/Low sample: 12 trades/);
    expect(screen.getByText(/2 quarantined trades are excluded/)).toBeTruthy();
  });
  it('no note at 20 trades', async () => {
    mockFetch({ '/api/analytics/attribution': attr(20), '/api/analytics/equity': eq() });
    renderPanel(await load('perf-summary'), { params: { range: 'all' } });
    await screen.findByText('Profit factor');
    expect(screen.queryByRole('note')).toBeNull();
  });
  it('says there are no trades', async () => {
    mockFetch({ '/api/analytics/attribution': attr(0, { overall: { trades: 0, low_sample: true }, buckets: [] }), '/api/analytics/equity': eq([]) });
    renderPanel(await load('perf-summary'), { params: { range: 'all' } });
    expect(await screen.findByText(/No closed trades in this range/)).toBeTruthy();
  });
});

describe('equity panel', () => {
  it('lists the deepest drawdowns, offers the data table and disposes the chart on unmount', async () => {
    mockFetch({ '/api/analytics/equity': eq() });
    const { unmount } = renderPanel(await load('equity'), { params: { range: 'all' } });
    expect(await screen.findByText(/Net -₹50 over 2 trades/)).toBeTruthy();
    expect(screen.getByRole('table', { name: 'Deepest drawdowns' })).toBeTruthy();
    expect(screen.getByText('Not yet')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Show data table/ }));
    expect(screen.getByRole('table', { name: 'Equity points' })).toBeTruthy();
    unmount();
    expect(removeChart).toHaveBeenCalled();
  });
  it('shows the empty state', async () => {
    mockFetch({ '/api/analytics/equity': eq([]) });
    renderPanel(await load('equity'), { params: { range: 'all' } });
    expect(await screen.findByText(/No closed trades in this range/)).toBeTruthy();
  });
});

describe('attribution panel', () => {
  it('refetches with the chosen group', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25) });
    const { setParams } = renderPanel(await load('attribution'), { params: { range: 'all', group: 'setup' } });
    await screen.findByText('Setup 2');
    fireEvent.change(screen.getByLabelText(/Group by/), { target: { value: 'hour' } });
    expect(setParams).toHaveBeenCalledWith(expect.objectContaining({ group: 'hour' }));
  });
  it('requests the group from the params', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25) });
    renderPanel(await load('attribution'), { params: { range: 'all', group: 'weekday' } });
    await screen.findByText('Setup 2');
    expect(calls[0]).toContain('group=weekday');
  });
  it('marks low-sample rows and sorts by a column', async () => {
    mockFetch({ '/api/analytics/attribution': attr(5) });
    renderPanel(await load('attribution'), { params: { range: 'all' } });
    await screen.findByText('Setup 2');
    expect(screen.getByText('Low sample (5)')).toBeTruthy();
    const body = () => within(screen.getByRole('table', { name: /Attribution by/ })).getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent);
    expect(body()[0]).toMatch(/^Setup 1/);
    fireEvent.click(screen.getByRole('button', { name: /^Trades/ }));
    fireEvent.click(screen.getByRole('button', { name: /^Trades/ }));
    expect(body()[0]).toMatch(/^Setup 2/);
  });
  it('a row click sets the linked filter and a second click clears it', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25) });
    renderPanel(await load('attribution'), { params: { range: 'all', group: 'setup' } });
    const row = (await screen.findByText('Setup 2')).closest('tr')!;
    fireEvent.click(row);
    expect(appStore.getState().filter).toEqual({ group: 'setup', key: 'Setup 2' });
    fireEvent.click(row);
    expect(appStore.getState().filter).toBeNull();
  });
  it('exports exactly the visible columns', async () => {
    mockFetch({ '/api/analytics/attribution': attr(25) });
    let blobText = '';
    const orig = globalThis.Blob;
    vi.stubGlobal('Blob', class { constructor(parts: string[]) { blobText = parts.join(''); } } as unknown as typeof Blob);
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:x';
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
    renderPanel(await load('attribution'), { params: { range: 'all' } });
    await screen.findByText('Setup 2');
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    vi.stubGlobal('Blob', orig);
    const [head, ...rows] = blobText.split('\r\n');
    expect(head).toBe('Name,Trades,Win %,Net P&L,Gross,Charges,Cost drag %,Expectancy,Profit factor,Avg R,Max drawdown');
    expect(rows).toHaveLength(2);
  });
});

describe('trades panel honours the linked filter', () => {
  it('shows the filter chip and clears it', async () => {
    appStore.setState({ trades: [{ id: '1', book: 'paper', display_book: 'Main', source_id: '1', status: 'CLOSED', instrument: 'NIFTY 24500 CE', setup: 'S1', opened_at: null, closed_at: null, mode: 'demo', net_pnl: 1, net_kind: 'realized', evidence_state: 'recorded' }] as never });
    setFilter({ group: 'setup', key: 'S2' });
    renderPanel(await load('trades'));
    expect(screen.getByText(/Filtered: setup = S2/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
    expect(appStore.getState().filter).toBeNull();
  });
});

describe('distributions panel', () => {
  const dist = (over: Record<string, unknown> = {}) => ({
    pnl: [{ lo: -100, hi: 0, count: 3 }, { lo: 0, hi: 100, count: 5 }], r: [{ lo: -1, hi: 1, count: 8 }], hold_minutes: [{ lo: 1, hi: 30, count: 8 }],
    mfe_mae: [{ id: 'a', mfe: 150, mae: -20, final: 100 }], medians: { pnl: { p10: -80, p50: 20, p90: 90 }, r: { p10: -1, p50: 0.2, p90: 1 }, hold_minutes: { p10: 2, p50: 10, p90: 25 } },
    generated_at: GEN, excluded: 0, ...over,
  });
  it('honours the bin count and writes the summary sentence', async () => {
    mockFetch({ '/api/analytics/distribution': dist() });
    renderPanel(await load('distributions'), { params: { range: 'all', bins: 12 } });
    expect(await screen.findByTestId('summary-pnl')).toHaveTextContent('Net P&L: median +₹20, 10th percentile -₹80, 90th percentile +₹90.');
    expect(calls[0]).toContain('bins=12');
    expect(screen.getByRole('img', { name: 'Net P&L per trade histogram' })).toBeTruthy();
  });
  it('clamps the bin control to 1..50', async () => {
    mockFetch({ '/api/analytics/distribution': dist() });
    const { setParams } = renderPanel(await load('distributions'), { params: { bins: 500 } });
    await screen.findByTestId('summary-pnl');
    expect(calls[0]).toContain('bins=50');
    fireEvent.change(screen.getByLabelText('Number of bins'), { target: { value: '0' } });
    expect(setParams).toHaveBeenLastCalledWith(expect.objectContaining({ bins: 1 }));
  });
  it('shows the empty state and never renders NaN', async () => {
    mockFetch({ '/api/analytics/distribution': dist({ pnl: [], r: [], hold_minutes: [], mfe_mae: [], medians: { pnl: { p10: null, p50: null, p90: null }, r: { p10: null, p50: null, p90: null }, hold_minutes: { p10: null, p50: null, p90: null } } }) });
    const { container } = renderPanel(await load('distributions'), { params: { range: 'all' } });
    expect(await screen.findByText(/No closed trades in this range/)).toBeTruthy();
    expect(container.textContent).not.toMatch(/NaN|undefined|Infinity/);
  });
  it('says so when excursions were not recorded', async () => {
    mockFetch({ '/api/analytics/distribution': dist({ mfe_mae: [] }) });
    renderPanel(await load('distributions'), { params: { range: 'all' } });
    expect(await screen.findByText(/Excursions were not recorded/)).toBeTruthy();
  });
});

describe('execution panel', () => {
  const exec = (over: Record<string, unknown> = {}) => ({
    slippage: { entry: [0.5, 0.25], exit: [0.1, 0.2], by_setup: [{ key: 'Setup 1', trades: 2, entry_avg: 0.375, exit_avg: 0.15, total_cost: 12 }], by_hour: [{ key: '09:00', trades: 2, entry_avg: 0.375, exit_avg: 0.15, total_cost: 12 }] },
    spread: { points: [{ spread_pct: 1.2, slippage: 0.4 }], buckets: [{ label: '1-2%', trades: 1, avg_slippage: 0.4 }] },
    liquidity: { quartiles: [{ q: 1, volume_lo: 10, volume_hi: 20, trades: 1, avg_slippage: 0.4, net_pnl: 10 }] },
    charges: { totals: { brokerage: 20, stt: 5, exchange_fee: 1, sebi_fee: 0.1, stamp_duty: 0.5, gst: 4 }, by_setup: [{ key: 'Setup 1', brokerage: 20, stt: 5, exchange_fee: 1, sebi_fee: 0.1, stamp_duty: 0.5, gst: 4, total: 30.6, trades: 2 }] },
    not_recorded: [], generated_at: GEN, excluded: 0, ...over,
  });
  it('renders not-recorded messages and hides the dependent charts', async () => {
    mockFetch({ '/api/analytics/execution': exec({ not_recorded: ['entry_spread_pct', 'option_volume', 'charges_breakdown'] }), '/api/analytics/attribution': attr(25) });
    renderPanel(await load('execution'), { params: { range: 'all' } });
    expect(await screen.findByTestId('not-recorded-entry_spread_pct')).toHaveTextContent('Not recorded: entry_spread_pct');
    expect(screen.getByTestId('not-recorded-option_volume')).toBeTruthy();
    expect(screen.getByTestId('not-recorded-charges_breakdown')).toBeTruthy();
    expect(screen.queryByRole('img', { name: /Spread at entry against entry slippage/ })).toBeNull();
  });
  it('the charges table total equals the sum of its parts', async () => {
    mockFetch({ '/api/analytics/execution': exec(), '/api/analytics/attribution': attr(25) });
    renderPanel(await load('execution'), { params: { range: 'all' } });
    await screen.findByRole('heading', { name: 'Charges' });
    fireEvent.click(screen.getByRole('button', { name: /Show data table: charges by setup/ }));
    const all = within(screen.getByRole('table', { name: 'Charges by setup' })).getByText('All').closest('tr')!;
    const cells = within(all).getAllByRole('cell').map((c) => c.textContent);
    expect(cells[cells.length - 1]).toBe('₹31');
    expect(cells.slice(0, 6)).toEqual(['₹20', '₹5', '₹1', '₹0', '₹1', '₹4']);
  });
  it('shows the cost drag per setup and the empty state', async () => {
    mockFetch({ '/api/analytics/execution': exec(), '/api/analytics/attribution': attr(25) });
    const { unmount } = renderPanel(await load('execution'), { params: { range: 'all' } });
    expect(await screen.findByRole('table', { name: 'Cost drag per setup' })).toBeTruthy();
    unmount();
    mockFetch({ '/api/analytics/execution': exec({ slippage: { entry: [], exit: [], by_setup: [], by_hour: [] } }), '/api/analytics/attribution': attr(0, { buckets: [] }) });
    renderPanel(await load('execution'), { params: { range: 'all' } });
    expect(await screen.findByText(/No closed trades in this range/)).toBeTruthy();
  });
});

describe('orders panel', () => {
  it('shows status as text with a colour class and says why when empty', async () => {
    renderPanel(await load('orders'));
    expect(screen.getByText(/Live routing is off/)).toBeTruthy();
  });
  it('lists orders', async () => {
    appStore.setState({ live: { status: { mode: 'dry_run' }, orders: [{ id: 1, ts: '2026-10-22T10:00:00+05:30', side: 'BUY', trading_symbol: 'NIFTY', qty: 75, status: 'REJECTED', price: 100, message: 'margin' }] } });
    markReady('live');
    renderPanel(await load('orders'));
    expect(screen.getByText('REJECTED').className).toContain('down');
    expect(screen.getByText('margin')).toBeTruthy();
  });
});

describe('audit panel', () => {
  it('merges the three sources newest first, and a failing source shows a strip while the others still list', async () => {
    mockFetch({
      '/api/audit/actions': [{ id: 1, ts: '2026-10-22T10:00:00+05:30', action: 'paper.close', target: 'P1', outcome: 'ok', method: 'POST', route: '/x', status: 200 }],
      '/api/settings/audit': [{ changed_at: '2026-10-22T11:00:00+05:30', key: 'max_open_positions', old_value: '5', new_value: '6', actor: 'dashboard' }],
      '/api/live/audit': () => new Response('{}', { status: 500 }),
    });
    renderPanel(await load('audit'));
    await screen.findByText('paper.close');
    const rows = within(screen.getByRole('table', { name: 'Audit rows' })).getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('setting.change');
    expect(rows[1]).toHaveTextContent('paper.close');
    expect(screen.getByRole('alert')).toHaveTextContent(/Could not load live routing/);
    expect(screen.queryByRole('button', { name: /delete|clear/i })).toBeNull();
  });
  it('expands a settings row to before and after', async () => {
    mockFetch({ '/api/audit/actions': [], '/api/settings/audit': [{ changed_at: '2026-10-22T11:00:00+05:30', key: 'k', old_value: '5', new_value: '6', actor: 'dashboard' }], '/api/live/audit': [] });
    renderPanel(await load('audit'));
    fireEvent.click(await screen.findByRole('button', { name: '5 → 6' }));
    expect(screen.getByText('Before')).toBeTruthy();
  });
  it('CSV escapes formulas', async () => {
    let blobText = '';
    vi.stubGlobal('Blob', class { constructor(parts: string[]) { blobText = parts.join(''); } } as unknown as typeof Blob);
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:x';
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
    mockFetch({ '/api/audit/actions': [{ id: 1, ts: '2026-10-22T10:00:00+05:30', action: '=HYPERLINK("x")', target: '', outcome: 'ok' }], '/api/settings/audit': [], '/api/live/audit': [] });
    renderPanel(await load('audit'));
    await screen.findByText('=HYPERLINK("x")');
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(blobText).toContain(`"'=HYPERLINK(""x"")"`);
  });
});

describe('readiness, recorder and universe panels', () => {
  it('readiness lists checks with a state word', async () => {
    appStore.setState((s) => ({ health: { ...s.health, readiness: { status: 'warn', checks: [{ key: 'dhan_login', status: 'warn', detail: 'soon' }, { key: 'disk', status: 'ok', detail: 'fine' }] } } }));
    markReady('health');
    renderPanel(await load('readiness'));
    expect(screen.getByText('dhan login')).toBeTruthy();
    expect(screen.getAllByText('Warning').length).toBeGreaterThan(0);
  });
  it('recorder shows counts and dropped bars', async () => {
    appStore.setState((s) => ({ health: { ...s.health, recorder: { enabled: true, recorded_this_run: 40, buffered: 2, dropped: 1, kinds: { spot: { bars: 100, keys: 3, first: '2026-10-20T09:15:00+05:30', last: '2026-10-22T15:25:00+05:30' } } } } }));
    renderPanel(await load('recorder'));
    expect(screen.getByText(/40 bars this run/)).toBeTruthy();
    expect(screen.getByRole('table', { name: 'Stored bars' })).toBeTruthy();
  });
  it('universe lists and searches', async () => {
    mockFetch({ '/api/universe': { indices: [{ symbol: 'NIFTY', name: 'Nifty 50', security_id: '1', exchange_segment: 'IDX_I', instrument_type: 'INDEX', default_timeframe: '5m', sector: 'Index' }], stocks: [], fno_stocks: [{ symbol: 'TCS', name: 'TCS', security_id: '2', exchange_segment: 'NSE_EQ', instrument_type: 'EQUITY', default_timeframe: '5m', sector: 'IT' }], total_count: 2, fno_count: 1 } });
    renderPanel(await load('universe'));
    await screen.findByText('TCS');
    fireEvent.change(screen.getByLabelText('Search universe'), { target: { value: 'nifty' } });
    expect(screen.queryByText('TCS')).toBeNull();
    expect(screen.getByText('NIFTY')).toBeTruthy();
  });
});

describe('health panel', () => {
  it('renders every tile with a state word and copies diagnostics without credentials', async () => {
    mockFetch({ '/api/health': { version: '9.9.9' } });
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    appStore.setState({ stream: { state: 'live', ageSec: 0 } });
    renderPanel(await load('health'));
    const list = screen.getByRole('list', { name: 'Health tiles' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(10);
    await screen.findByText('9.9.9');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostics' })); });
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const keys: string[] = [];
    const walk = (v: unknown) => { if (Array.isArray(v)) v.forEach(walk); else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => { keys.push(k); walk(x); }); };
    walk(JSON.parse((writeText.mock.calls[0] as unknown as string[])[0]));
    expect(keys.length).toBeGreaterThan(5);
    expect(keys.filter((k) => /token|secret|key|password|capability/i.test(k))).toEqual([]);
  });
});

describe('alerts panel', () => {
  it('lists alerts newest first, acknowledges them and shows the rules', async () => {
    pushAlert({ severity: 'warning', source: 'a', message: 'older' }, 1000);
    pushAlert({ severity: 'critical', source: 'b', message: 'newer' }, 2000);
    renderPanel(await load('alerts'));
    const items = within(screen.getByRole('list', { name: /Alerts, newest first/ })).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('newer');
    fireEvent.click(screen.getByRole('button', { name: /Acknowledge: newer/ }));
    expect(items[0]).toHaveAttribute('data-acked', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge all' }));
    expect(appStore.getState().alerts.every((a) => a.acked)).toBe(true);
    expect(screen.getByRole('region', { name: 'Alert rules' })).toBeTruthy();
  });
  it('browser notifications are off by default', async () => {
    renderPanel(await load('alerts'));
    expect((screen.getByLabelText(/Browser notifications/) as HTMLInputElement).checked).toBe(false);
  });
});
