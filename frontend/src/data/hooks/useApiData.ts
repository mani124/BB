import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/client';
import { appStore, useApp } from '../appStore';
import { useActionEpoch } from '../actions';

export type Query = Record<string, string | number | boolean | null | undefined>;

/** `?a=1&b=2` from defined values, or an empty string. */
export function buildQuery(params: Query): string {
  const q = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return q.length ? `?${q.join('&')}` : '';
}

export interface ApiData<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Epoch ms of the last good response. */
  fetchedAt: number | null;
  reload: () => void;
}

/**
 * GET a JSON endpoint, refetch on a timer, when the closed-trade count changes and when `path` changes.
 * The last good data stays on screen under an error. Pass null to skip.
 */
export function useApiData<T>(path: string | null, opts: { refreshMs?: number; watchTrades?: boolean; watchActions?: boolean } = {}): ApiData<T> {
  const { refreshMs = 120_000, watchTrades = false, watchActions = false } = opts;
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean; fetchedAt: number | null }>({ data: null, error: null, loading: path !== null, fetchedAt: null });
  const seq = useRef(0);
  const actionEpoch = useActionEpoch();
  const actionTick = watchActions ? actionEpoch : 0;
  const tradeCount = useApp((s) => (watchTrades ? s.scanner.paper_portfolio?.total_trades_count ?? s.closedTrades.length : 0));

  const run = useCallback(async () => {
    if (path === null) return;
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await apiFetch(path);
      if (mine !== seq.current) return;
      if (res.status === 401) {
        appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } }));
        throw new Error('Dashboard key required (401)');
      }
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const json = (await res.json()) as T;
      if (mine !== seq.current) return;
      setState({ data: json, error: null, loading: false, fetchedAt: Date.now() });
    } catch (e) {
      if (mine !== seq.current) return;
      setState((s) => ({ ...s, error: e instanceof Error ? e.message : 'Request failed', loading: false }));
    }
  }, [path]);

  useEffect(() => {
    if (path === null) return undefined;
    void run();
    const id = refreshMs > 0 ? setInterval(() => { if (!document.hidden) void run(); }, refreshMs) : null;
    return () => { seq.current++; if (id) clearInterval(id); };
  }, [path, refreshMs, run, tradeCount, actionTick]);

  return { ...state, reload: () => { void run(); } };
}
