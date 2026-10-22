import { useEffect, useState } from 'react';
import type { ScannerState, PaperPortfolio } from '../types';
import { createStore, useStore, type Store } from './store';
import type { AppState, SliceMeta, SliceName } from './types';

const SLICES: SliceName[] = ['stream', 'scanner', 'portfolio', 'closedTrades', 'watch', 'trades', 'live', 'health', 'analytics'];

/** Age (ms) after which a slice is shown as stale. null = never stale by age alone. */
export const STALE_AFTER_MS: Record<SliceName, number | null> = {
  stream: 15_000,
  scanner: 15_000,
  portfolio: 15_000,
  closedTrades: null,
  watch: 60_000,
  trades: 60_000,
  live: 30_000,
  health: 120_000,
  analytics: 240_000,
};

function readDensity(): 'compact' | 'comfortable' {
  try { return localStorage.getItem('bb_density') === 'comfortable' ? 'comfortable' : 'compact'; } catch { return 'compact'; }
}

export function initialScanner(): ScannerState {
  return {
    signals: [], radar: {}, last_scan_time: '', scan_cycle_count: 0, is_scanning: false,
    scan_progress: 0, universe_count: 34, active_mode: 'demo',
  };
}

export function initialState(): AppState {
  const meta = {} as Record<SliceName, SliceMeta>;
  SLICES.forEach((s) => { meta[s] = { asOf: null, status: 'idle' }; });
  return {
    scanner: initialScanner(),
    closedTrades: [],
    watch: null,
    trades: [],
    live: { status: null, orders: [] },
    health: { readiness: null, rateLimit: null, recorder: null, errors: [] },
    analytics: {},
    stream: { state: 'connecting', ageSec: 0 },
    meta,
    selection: null,
    filter: null,
    alerts: [],
    ui: { density: readDensity(), workspace: 'Trading', needsCapability: false, notifications: false },
  };
}

export const appStore: Store<AppState> = createStore<AppState>(initialState());

export function resetAppStore(): void {
  appStore.setState(initialState());
}

export function useApp<S>(selector: (s: AppState) => S, isEqual?: (a: S, b: S) => boolean): S {
  return useStore(appStore, selector, isEqual);
}

export function setSlice<K extends SliceName>(name: K, patch: Partial<SliceMeta>): void {
  appStore.setState((s) => ({ meta: { ...s.meta, [name]: { ...s.meta[name], ...patch } } }));
}

/** Mark a slice ready now and clear any error. */
export function markReady(name: SliceName, now: number = Date.now()): void {
  setSlice(name, { asOf: now, status: 'ready', error: undefined });
}

export function markError(name: SliceName, error: string): void {
  setSlice(name, { status: 'error', error });
}

/** Replace the paper portfolio (and the closed-trade journal when it is included). */
export function applyPortfolio(portfolio: PaperPortfolio): void {
  appStore.setState((s) => ({
    scanner: { ...s.scanner, paper_portfolio: portfolio },
    closedTrades: portfolio.closed_trades ?? s.closedTrades,
    meta: {
      ...s.meta,
      portfolio: { asOf: Date.now(), status: 'ready' },
      closedTrades: { asOf: Date.now(), status: 'ready' },
    },
  }));
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function sliceStale(meta: SliceMeta, name: SliceName, now: number): boolean {
  if (meta.status === 'stale') return true;
  const limit = STALE_AFTER_MS[name];
  return limit !== null && meta.asOf !== null && now - meta.asOf > limit;
}

export function useSliceMeta(name: SliceName): SliceMeta & { stale: boolean; ageSec: number } {
  const meta = useApp((s) => s.meta[name]);
  const now = useNow();
  return { ...meta, stale: sliceStale(meta, name, now), ageSec: meta.asOf === null ? 0 : Math.max(0, Math.round((now - meta.asOf) / 1000)) };
}
