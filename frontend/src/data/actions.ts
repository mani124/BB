import { useSyncExternalStore } from 'react';
import { apiFetch } from '../api/client';
import type { PaperPortfolio, SetupMode, Signal } from '../types';
import { alertsHook } from './alertsHook';
import { appStore, applyPortfolio } from './appStore';
import { pushToast } from './toasts';
import { createStore } from './store';

export interface ActionResult { ok: boolean; message: string; detail?: unknown }

const TIMEOUT_MS = 10_000;
const UNKNOWN = 'No answer from the server. Outcome unknown; check positions.';

const inflight = createStore<{ keys: Record<string, boolean> }>({ keys: {} });
const setFlight = (key: string, on: boolean) => {
  const keys = { ...inflight.getState().keys };
  if (on) keys[key] = true; else delete keys[key];
  inflight.setState({ keys });
};
/** Counts finished mutating requests, so panels that list their audit trail can refetch. */
const epoch = createStore<{ n: number }>({ n: 0 });
export function useActionEpoch(): number {
  const get = () => epoch.getState().n;
  return useSyncExternalStore(epoch.subscribe, get, get);
}
export const isInFlight = (key: string): boolean => Boolean(inflight.getState().keys[key]);
export function useInFlight(key: string): boolean {
  const get = () => Boolean(inflight.getState().keys[key]);
  return useSyncExternalStore(inflight.subscribe, get, get);
}
/** Test helper. */
export function resetInFlight(): void { inflight.setState({ keys: {} }); }

export async function refreshPortfolio(): Promise<PaperPortfolio | null> {
  try {
    const res = await apiFetch('/api/paper/portfolio');
    if (!res.ok) return null;
    const data = (await res.json()) as PaperPortfolio;
    applyPortfolio(data);
    return data;
  } catch {
    return null;
  }
}

export async function refreshLive(): Promise<void> {
  try {
    const res = await apiFetch('/api/live/status');
    if (res.ok) {
      const status = await res.json();
      appStore.setState((s) => ({ live: { ...s.live, status }, meta: { ...s.meta, live: { asOf: Date.now(), status: 'ready' } } }));
    }
  } catch { /* the poller will retry */ }
}

interface RunOptions {
  key: string;
  path: string;
  method?: 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  okMessage: string;
  failPrefix?: string;
  /** Refetches canonical state; runs after success and after an unknown outcome. */
  refetch?: () => Promise<unknown>;
  severity?: 'info' | 'critical';
  source?: string;
  /** Use the response body as state instead of refetching. */
  onBody?: (body: unknown) => void;
}

async function run(o: RunOptions): Promise<ActionResult & { body?: Record<string, unknown> }> {
  const r = await runInner(o);
  if (r.message !== 'Already running') pushToast(r.ok, r.message);
  return r;
}

async function runInner(o: RunOptions): Promise<ActionResult & { body?: Record<string, unknown> }> {
  if (isInFlight(o.key)) return { ok: false, message: 'Already running' };
  setFlight(o.key, true);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const source = o.source ?? o.key;
  try {
    const res = await apiFetch(o.path, {
      method: o.method ?? 'POST',
      headers: o.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
      signal: ctrl.signal,
    });
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 401) {
      appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } }));
      const message = 'Unauthorized: dashboard key required.';
      alertsHook.push({ severity: 'warning', source, message });
      return { ok: false, message, detail: body, body };
    }
    if (!res.ok) {
      const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`;
      const message = `${o.failPrefix ?? 'Request failed'}: ${detail}`;
      alertsHook.push({ severity: 'warning', source, message });
      return { ok: false, message, detail: body, body };
    }
    if (o.onBody) o.onBody(body);
    else if (o.refetch) await o.refetch();
    alertsHook.push({ severity: o.severity ?? 'info', source, message: o.okMessage });
    return { ok: true, message: o.okMessage, detail: body, body };
  } catch {
    if (o.refetch) void o.refetch();
    alertsHook.push({ severity: 'warning', source, message: UNKNOWN });
    return { ok: false, message: UNKNOWN };
  } finally {
    clearTimeout(timer);
    setFlight(o.key, false);
    epoch.setState({ n: epoch.getState().n + 1 });
  }
}

const j = (path: string, key: string, okMessage: string, body?: unknown, extra: Partial<RunOptions> = {}) =>
  run({ key, path, body, okMessage, refetch: refreshLive, ...extra });

/** Generic audited request for panels whose endpoints have no dedicated action (earnings, live routing). */
export function request(path: string, opts: { key: string; method?: 'POST' | 'PUT' | 'DELETE'; body?: unknown; okMessage: string; failPrefix?: string; source?: string; severity?: 'info' | 'critical'; refetch?: () => Promise<unknown> }) {
  return run({ path, ...opts });
}

export const actions = {
  scanNow: () => run({ key: 'scanNow', path: '/api/signals/scan-now', okMessage: 'Scan requested.', failPrefix: 'Scan failed' }),

  paperBuy: (signal: Signal) => {
    const lots = appStore.getState().scanner.paper_portfolio?.default_lots || 2;
    return run({ key: 'paperBuy', path: '/api/paper/trade', body: { signal, lots }, okMessage: `Paper buy placed: ${signal.symbol} ${signal.option_type}.`, failPrefix: 'Trade rejected', refetch: refreshPortfolio });
  },

  closePosition: (id: string) =>
    run({ key: `close:${id}`, path: `/api/paper/close/${encodeURIComponent(id)}`, okMessage: 'Position closed.', failPrefix: 'Failed to close position', refetch: refreshPortfolio, source: 'paper.close' }),

  async toggleAutoTrade(enabled: boolean): Promise<ActionResult> {
    const r = await run({ key: 'autoTrade', path: '/api/paper/settings', body: { auto_trade_enabled: enabled }, okMessage: enabled ? 'Auto-enter is on.' : 'Auto-enter is off.', failPrefix: 'Could not change auto-trade', refetch: refreshPortfolio });
    if (!r.ok) return r;
    const now = appStore.getState().scanner.paper_portfolio?.auto_trade_enabled;
    if (now !== enabled) return { ok: false, message: 'Could not verify entry state: the server did not apply the change.' };
    return r;
  },

  setSetupMode: (setup: string, mode: SetupMode) =>
    run({ key: `setupMode:${setup}`, path: '/api/paper/settings', body: { setup_modes: { [setup]: mode } }, okMessage: `Setup ${setup} set to ${mode}.`, failPrefix: 'Could not change the setup mode', onBody: (b) => { if (b && typeof b === 'object' && 'active_positions' in b) applyPortfolio(b as unknown as PaperPortfolio); else void refreshPortfolio(); } }),

  async killSwitch(engage: boolean): Promise<ActionResult & { failed: string[] }> {
    const r = await run({ key: 'killSwitch', path: engage ? '/api/paper/kill-switch' : '/api/paper/kill-switch/release', body: { confirm: true }, okMessage: engage ? 'Kill switch engaged.' : 'Kill switch released.', failPrefix: 'Kill switch request failed', refetch: refreshPortfolio, severity: engage ? 'critical' : 'info', source: engage ? 'kill_switch.engage' : 'kill_switch.release' });
    const failed = Array.isArray(r.body?.failed) ? (r.body!.failed as unknown[]).map(String) : [];
    if (r.ok && failed.length > 0) {
      const message = `Kill switch engaged, but ${failed.length} position(s) could not be closed: ${failed.join(', ')}. Close them by hand.`;
      alertsHook.push({ severity: 'critical', source: 'kill_switch.engage', message });
      return { ok: true, message, detail: r.detail, failed };
    }
    return { ok: r.ok, message: r.message, detail: r.detail, failed };
  },

  resetPortfolio: () => run({ key: 'resetPortfolio', path: '/api/paper/reset', okMessage: 'Paper portfolio reset (trades archived, not deleted).', failPrefix: 'Failed to reset paper portfolio', refetch: refreshPortfolio, source: 'paper.reset' }),

  updateSettings: (changes: Record<string, unknown>) =>
    run({ key: 'updateSettings', path: '/api/settings', method: 'PUT', body: { changes }, okMessage: 'Settings saved.', failPrefix: 'Save failed', source: 'settings.update' }),

  resetSetting: (key: string) =>
    run({ key: `resetSetting:${key}`, path: `/api/settings/${encodeURIComponent(key)}/reset`, okMessage: `Setting ${key} reset to default.`, failPrefix: 'Reset failed', source: 'settings.reset' }),

  live: {
    setMode: (mode: 'off' | 'dry_run') => j('/api/live/mode', 'live.mode', `Live routing mode: ${mode}.`, { mode }, { source: 'live.mode', severity: 'critical' }),
    arm: () => j('/api/live/arm', 'live.arm', 'Live arming code issued.', undefined, { source: 'live.arm' }),
    enable: (code: string, phrase: string) => j('/api/live/enable', 'live.enable', 'LIVE routing enabled.', { code, phrase }, { source: 'live.enable', severity: 'critical' }),
    resume: () => j('/api/live/resume', 'live.resume', 'Live routing resumed.', undefined, { source: 'live.resume' }),
    reconcile: () => j('/api/live/reconcile', 'live.reconcile', 'Reconcile requested.', undefined, { source: 'live.reconcile' }),
    retryExit: (positionId: string) => j(`/api/live/positions/${encodeURIComponent(positionId)}/retry-exit`, `live.retry:${positionId}`, 'Exit retry requested.', undefined, { source: 'live.retry_exit' }),
    brokerLogin: (totp: string) => j('/api/live/broker/login', 'live.brokerLogin', 'Broker login requested.', { totp }, { source: 'live.broker_login' }),
    brokerLogout: () => j('/api/live/broker/logout', 'live.brokerLogout', 'Broker logged out.', undefined, { source: 'live.broker_logout' }),
  },

  earnings: {
    syncCalendar: () => run({ key: 'earnings.sync', path: '/api/earnings/calendar/sync', okMessage: 'Calendar updated from NSE', source: 'earnings.calendar_sync' }),
    saveCalendarRow: (row: Record<string, unknown>) => run({ key: 'earnings.save', path: '/api/earnings/calendar', body: { rows: [row] }, okMessage: `Saved ${String(row.symbol ?? '').toUpperCase()}`, source: 'earnings.calendar_save' }),
    deleteCalendarRow: (symbol: string, date: string) => run({ key: `earnings.delete:${symbol}:${date}`, path: `/api/earnings/calendar/${encodeURIComponent(symbol)}/${encodeURIComponent(date)}`, method: 'DELETE', okMessage: `Removed ${symbol}`, source: 'earnings.calendar_delete' }),
    runCycle: () => run({ key: 'earnings.cycle', path: '/api/earnings/run-cycle', okMessage: 'Cycle run', source: 'earnings.run_cycle' }),
    squareOff: () => run({ key: 'earnings.squareOff', path: '/api/earnings/square-off', okMessage: 'Positions closed', source: 'earnings.square_off', severity: 'critical' }),
    importIv: (body: unknown) => run({ key: 'earnings.iv', path: '/api/earnings/iv-history', body, okMessage: 'IV history imported', source: 'earnings.iv_import' }),
  },

  journal: {
    save: (id: string, body: unknown) => run({ key: `journal:${id}`, path: `/api/journal/trades/${encodeURIComponent(id)}`, method: 'PUT', body, okMessage: 'Note saved.', failPrefix: 'Could not save note', source: 'journal.save' }),
  },
};
