import { apiFetch } from '../api/client';
import { appStore, markError, markReady } from './appStore';
import type { Json, SliceName } from './types';
import { keepIdentity } from './store';

export type PollKey = 'trades' | 'watch' | 'live' | 'readiness' | 'rateLimit' | 'recorder' | 'errors' | 'analytics';

export const DEFAULT_INTERVALS: Record<PollKey, number> = {
  trades: 30_000, watch: 30_000, live: 15_000, readiness: 60_000, rateLimit: 60_000, recorder: 60_000, errors: 60_000, analytics: 120_000,
};

async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (res.status === 401) {
    appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } }));
    throw new Error('Dashboard key required (401)');
  }
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return (await res.json()) as T;
}

interface PollerDef {
  key: PollKey;
  slice: SliceName;
  run: () => Promise<void>;
  interval?: (base: number) => number;
}

const analyticsHooks = new Set<() => void | Promise<void>>();
/** Panels with analytics data register a refresher here; it runs on the analytics cadence. */
export function onAnalyticsRefresh(fn: () => void | Promise<void>): () => void {
  analyticsHooks.add(fn);
  return () => { analyticsHooks.delete(fn); };
}

const DEFS: PollerDef[] = [
  { key: 'trades', slice: 'trades', run: async () => { const d = await getJson<unknown[]>('/api/dashboard/trades'); appStore.setState((s) => ({ trades: keepIdentity(s.trades, d as never) })); } },
  { key: 'watch', slice: 'watch', run: async () => { const d = await getJson<never>('/api/dashboard/watch'); appStore.setState((s) => ({ watch: keepIdentity(s.watch, d) })); } },
  {
    key: 'live', slice: 'live',
    interval: (base) => (appStore.getState().live.status?.mode && appStore.getState().live.status?.mode !== 'off' ? base : 60_000),
    run: async () => {
      const status = await getJson<Json>('/api/live/status');
      let orders = appStore.getState().live.orders;
      if (status.mode && status.mode !== 'off') {
        const o = await getJson<Json[] | { orders?: Json[] }>('/api/live/orders').catch(() => null);
        if (o) orders = Array.isArray(o) ? o : (o.orders ?? []);
      }
      appStore.setState((s) => ({ live: { status: keepIdentity(s.live.status, status), orders: keepIdentity(s.live.orders, orders) } }));
    },
  },
  { key: 'readiness', slice: 'health', run: async () => { const d = await getJson<Json>('/api/readiness'); appStore.setState((s) => ({ health: { ...s.health, readiness: keepIdentity(s.health.readiness, d) } })); } },
  { key: 'rateLimit', slice: 'health', run: async () => { const d = await getJson<Json>('/api/telemetry/dhan-rate-limit'); appStore.setState((s) => ({ health: { ...s.health, rateLimit: keepIdentity(s.health.rateLimit, d) } })); } },
  { key: 'recorder', slice: 'health', run: async () => { const d = await getJson<Json>('/api/recorder/status'); appStore.setState((s) => ({ health: { ...s.health, recorder: keepIdentity(s.health.recorder, d) } })); } },
  {
    key: 'errors', slice: 'health',
    run: async () => {
      const d = await getJson<Json[] | { errors?: Json[] }>('/api/telemetry/errors?limit=20');
      const rows = Array.isArray(d) ? d : (d.errors ?? []);
      appStore.setState((s) => ({ health: { ...s.health, errors: keepIdentity(s.health.errors, rows) } }));
    },
  },
  { key: 'analytics', slice: 'analytics', run: async () => { await Promise.all([...analyticsHooks].map((f) => f())); } },
];

export function startPollers(opts: { intervals?: Partial<Record<PollKey, number>> } = {}): () => void {
  const base = { ...DEFAULT_INTERVALS, ...(opts.intervals ?? {}) };
  const timers = new Map<PollKey, ReturnType<typeof setTimeout>>();
  let stopped = false;

  const runOne = async (def: PollerDef) => {
    if (def.key === 'analytics' && analyticsHooks.size === 0) return;
    try {
      await def.run();
      // The health slice is fed by four pollers; each marks it ready, the first error wins until the next success.
      markReady(def.slice);
    } catch (e) {
      markError(def.slice, e instanceof Error ? e.message : 'request failed');
    }
  };

  const schedule = (def: PollerDef) => {
    if (stopped) return;
    const ms = def.interval ? def.interval(base[def.key]) : base[def.key];
    timers.set(def.key, setTimeout(async () => {
      if (!document.hidden) await runOne(def);
      schedule(def);
    }, ms));
  };

  const onVisible = () => {
    if (document.hidden || stopped) return;
    DEFS.forEach((def) => { void runOne(def); });
  };

  DEFS.forEach((def) => {
    void runOne(def).finally(() => schedule(def));
  });
  document.addEventListener('visibilitychange', onVisible);

  return () => {
    stopped = true;
    timers.forEach((t) => clearTimeout(t));
    timers.clear();
    document.removeEventListener('visibilitychange', onVisible);
  };
}

/** Re-runs every poller now (used by the error strip's Retry button). */
export function pollNow(): void {
  DEFS.forEach((def) => {
    if (def.key === 'analytics' && analyticsHooks.size === 0) return;
    void def.run().then(() => markReady(def.slice)).catch((e: unknown) => markError(def.slice, e instanceof Error ? e.message : 'request failed'));
  });
}
