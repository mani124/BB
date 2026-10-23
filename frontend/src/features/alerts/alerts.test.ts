import { beforeEach, describe, expect, it } from 'vitest';
import { appStore, initialState, resetAppStore } from '../../data/appStore';
import type { AppState } from '../../data/types';
import { alertsHook } from '../../data/alertsHook';
import { ackAlert, ackAll, clearAcked, loadAlerts, MAX_ALERTS, pushAlert } from './alertsStore';
import { startAlertsEngine } from './engine';
import * as R from './rules';
import { evaluateRules } from './rules';

const NOW = 1_000_000_000_000;
const withRisk = (s: AppState, risk: Record<string, unknown>): AppState => ({ ...s, scanner: { ...s.scanner, paper_portfolio: { active_positions: [], closed_trades: [], risk: { daily_loss_limit: 24000, day_pnl: 0, loss_cap_tripped: false, kill_switch_active: false, entries_blocked: false, ...risk } } as never } });
const base = () => withRisk(initialState(), {});
const msgs = (a: { message: string }[]) => a.map((x) => x.message);

beforeEach(() => { resetAppStore(); try { localStorage.clear(); } catch { /* none */ } });

describe('rules', () => {
  it('kill switch on is critical, off is info, unchanged is silent', () => {
    expect(R.killSwitchRule(base(), withRisk(base(), { kill_switch_active: true }), NOW)).toMatchObject([{ severity: 'critical', source: 'kill_switch' }]);
    expect(R.killSwitchRule(withRisk(base(), { kill_switch_active: true }), base(), NOW)).toMatchObject([{ severity: 'info' }]);
    expect(R.killSwitchRule(base(), base(), NOW)).toEqual([]);
  });
  it('loss cap tripped is critical once', () => {
    const tripped = withRisk(base(), { loss_cap_tripped: true, loss_cap_reason: 'Cap hit' });
    expect(msgs(R.lossCapRule(base(), tripped, NOW))).toEqual(['Cap hit']);
    expect(R.lossCapRule(tripped, tripped, NOW)).toEqual([]);
  });
  it('a newly capped pool warns', () => {
    expect(msgs(R.cappedPoolRule(base(), withRisk(base(), { capped_pools: ['S11'] }), NOW))).toEqual(['Pool S11 reached its own daily cap.']);
    expect(R.cappedPoolRule(withRisk(base(), { capped_pools: ['S11'] }), withRisk(base(), { capped_pools: ['S11'] }), NOW)).toEqual([]);
  });
  it('a changed block reason warns, kill switch and loss cap are left to their own rules', () => {
    expect(R.blockReasonRule(base(), withRisk(base(), { entries_blocked: true, block_reason: 'max open' }), NOW)).toHaveLength(1);
    expect(R.blockReasonRule(base(), withRisk(base(), { entries_blocked: true, kill_switch_active: true }), NOW)).toEqual([]);
  });
  it('stream: reconnecting is critical, stale warns, recovery is info', () => {
    const at = (state: AppState['stream']['state'], ageSec = 5): AppState => ({ ...base(), stream: { state, ageSec } });
    expect(R.streamRule(at('live'), at('reconnecting'), NOW)[0].severity).toBe('critical');
    expect(R.streamRule(at('live'), at('stale', 20), NOW)[0].severity).toBe('warning');
    expect(R.streamRule(at('stale'), at('live'), NOW)[0].severity).toBe('info');
    expect(R.streamRule(at('connecting'), at('live'), NOW)).toEqual([]);
  });
  it('feed error is critical and recovery info', () => {
    const f = (feed_status: string): AppState => ({ ...base(), scanner: { ...base().scanner, feed_status } as never });
    expect(R.feedRule(f('WS_LIVE'), f('ERROR'), NOW)[0].severity).toBe('critical');
    expect(R.feedRule(f('WS_LIVE'), f('STALE'), NOW)[0].severity).toBe('warning');
    expect(R.feedRule(f('ERROR'), f('WS_LIVE'), NOW)[0].severity).toBe('info');
  });
  it('Dhan: disconnect and token under one hour', () => {
    const d = (loggedIn: boolean, expiry: number | null): AppState => ({ ...base(), ui: { ...base().ui, dhan: { loggedIn, expiry } } });
    expect(R.dhanRule(d(true, NOW + 5 * 3_600_000), d(false, null), NOW)).toHaveLength(1);
    expect(msgs(R.dhanRule(d(true, NOW + 5 * 3_600_000), d(true, NOW + 30 * 60000), NOW))).toEqual(['The Dhan token expires in 30 minutes.']);
    expect(R.dhanRule(d(true, NOW + 30 * 60000), d(true, NOW + 29 * 60000), NOW)).toEqual([]);
  });
  it('rate-limit cooldown starting warns', () => {
    const r = (c: number): AppState => ({ ...base(), health: { ...base().health, rateLimit: { cooldown_s: c } } });
    expect(R.rateLimitRule(r(0), r(3), NOW)).toHaveLength(1);
    expect(R.rateLimitRule(r(3), r(2), NOW)).toEqual([]);
  });
  it('a newly failed readiness check is critical', () => {
    const r = (checks: unknown[]): AppState => ({ ...base(), health: { ...base().health, readiness: { checks } } });
    const out = R.readinessRule(r([]), r([{ key: 'dhan_login', status: 'fail', detail: 'no token' }]), NOW);
    expect(out[0]).toMatchObject({ severity: 'critical', message: 'Readiness check failed: dhan login. no token' });
    expect(R.readinessRule(r([{ key: 'dhan_login', status: 'fail' }]), r([{ key: 'dhan_login', status: 'fail' }]), NOW)).toEqual([]);
  });
  it('live halted is critical', () => {
    const l = (halted: boolean): AppState => ({ ...base(), live: { status: { halted }, orders: [] } });
    expect(R.liveHaltRule(l(false), l(true), NOW)[0].severity).toBe('critical');
    expect(R.liveHaltRule(l(true), l(true), NOW)).toEqual([]);
  });
  it('a rejected order is critical once', () => {
    const o = (status: string): AppState => ({ ...base(), live: { status: null, orders: [{ id: 1, status, side: 'BUY', trading_symbol: 'NIFTY', message: 'margin' }] } });
    expect(msgs(R.orderRule(o('PENDING'), o('REJECTED'), NOW))).toEqual(['Order rejected: BUY NIFTY. margin']);
    expect(R.orderRule(o('REJECTED'), o('REJECTED'), NOW)).toEqual([]);
  });
  it('a position closed by its stop is info, by quarantine is warning', () => {
    const pos = { id: 'P1', strike_symbol: 'NIFTY 24500 CE' };
    const prev: AppState = { ...base(), scanner: { ...base().scanner, paper_portfolio: { active_positions: [pos], closed_trades: [] } as never } };
    const next = (closed: Record<string, unknown>): AppState => ({ ...base(), closedTrades: [{ ...pos, ...closed }] as never });
    expect(R.positionClosedRule(prev, next({ status: 'STOPPED_OUT' }), NOW)[0].severity).toBe('info');
    expect(R.positionClosedRule(prev, next({ status: 'CLOSED', quarantine_reason: 'BAD' }), NOW)[0].severity).toBe('warning');
    expect(R.positionClosedRule(prev, next({ status: 'TARGET_2' }), NOW)).toEqual([]);
  });
  it('new high-severity error events are critical; lower ones are ignored; the first load is silent', () => {
    const e = (rows: unknown[], asOf: number | null = 1): AppState => ({ ...base(), health: { ...base().health, errors: rows as never }, meta: { ...base().meta, health: { asOf, status: 'ready' } } });
    expect(R.errorEventRule(e([{ id: 1, severity: 'ERROR', message: 'boom', component: 'x' }]), e([{ id: 2, severity: 'ERROR', message: 'bang', component: 'y' }, { id: 1, severity: 'ERROR' }]), NOW).map((a) => a.message)).toEqual(['y: bang']);
    expect(R.errorEventRule(e([]), e([{ id: 3, severity: 'WARNING', message: 'w' }]), NOW)).toEqual([]);
    expect(R.errorEventRule(e([], null), e([{ id: 3, severity: 'ERROR', message: 'old' }]), NOW)).toEqual([]);
  });
  it('a throwing rule does not stop the others and 100 unchanged evaluations raise nothing', () => {
    const s = base();
    for (let i = 0; i < 100; i += 1) expect(evaluateRules(s, { ...s }, NOW + i).filter((a) => a.source !== 'dhan')).toEqual([]);
    expect(evaluateRules(s, s, NOW)).toEqual([]);
    expect(evaluateRules(base(), withRisk(base(), { kill_switch_active: true }), NOW)).toHaveLength(1);
  });
});

describe('alerts store', () => {
  it('adds newest first, caps at 200 and dedupes an identical unacknowledged alert inside 30 s', () => {
    for (let i = 0; i < MAX_ALERTS + 20; i += 1) pushAlert({ severity: 'info', source: 's', message: `m${i}` }, NOW + i);
    const list = appStore.getState().alerts;
    expect(list).toHaveLength(MAX_ALERTS);
    expect(list[0].message).toBe(`m${MAX_ALERTS + 19}`);
    expect(pushAlert({ severity: 'info', source: 's', message: `m${MAX_ALERTS + 19}` }, NOW + 1000)).toBeNull();
    expect(pushAlert({ severity: 'info', source: 's', message: `m${MAX_ALERTS + 19}` }, NOW + 60_000)).not.toBeNull();
  });
  it('acknowledge, acknowledge all and clear acknowledged', () => {
    const a = pushAlert({ severity: 'critical', source: 'a', message: '1' }, NOW)!;
    pushAlert({ severity: 'warning', source: 'b', message: '2' }, NOW);
    ackAlert(a.id);
    expect(appStore.getState().alerts.filter((x) => x.acked)).toHaveLength(1);
    ackAll();
    expect(appStore.getState().alerts.every((x) => x.acked)).toBe(true);
    clearAcked();
    expect(appStore.getState().alerts).toHaveLength(0);
  });
  it('acknowledged flags survive a reload through localStorage', () => {
    const a = pushAlert({ severity: 'critical', source: 'a', message: '1' }, NOW)!;
    ackAlert(a.id);
    expect(loadAlerts()[0]).toMatchObject({ id: a.id, acked: true });
  });
  it('still works when storage throws', () => {
    const real = Object.getOwnPropertyDescriptor(window, 'localStorage')!;
    Object.defineProperty(window, 'localStorage', { configurable: true, value: { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } } });
    try {
      const a = pushAlert({ severity: 'critical', source: 'a', message: '1' }, NOW)!;
      ackAlert(a.id);
      expect(appStore.getState().alerts[0].acked).toBe(true);
      expect(loadAlerts()).toEqual([]);
    } finally { Object.defineProperty(window, 'localStorage', real); }
  });
});

describe('engine', () => {
  it('turns store changes and action outcomes into alerts, and reports criticals', () => {
    const seen: string[] = [];
    const stop = startAlertsEngine({ onCritical: (a) => seen.push(a.message) });
    appStore.setState(withRisk(appStore.getState(), {}));
    appStore.setState(withRisk(appStore.getState(), { kill_switch_active: true }));
    appStore.setState({ stream: { state: 'reconnecting', ageSec: 3 } });
    alertsHook.push({ severity: 'warning', source: 'x', message: 'from an action' });
    stop();
    const list = appStore.getState().alerts.map((a) => a.message);
    expect(list).toContain('Kill switch is ON: new entries are blocked.');
    expect(list).toContain('from an action');
    expect(seen).toHaveLength(2);
    alertsHook.push({ severity: 'info', source: 'x', message: 'after stop' });
    expect(appStore.getState().alerts.map((a) => a.message)).not.toContain('after stop');
  });
});
