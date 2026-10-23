import { apiFetch } from '../api/client';
import type { PaperPortfolio, ScannerState } from '../types';
import { appStore, markError, markReady, setSlice } from './appStore';
import { keepIdentity } from './store';

export interface StreamOptions {
  url?: string;
  staleAfterMs?: number;
  reconnectMs?: number;
  flushMs?: number;
}

/** Starts the snapshot fetch and the SSE connection. Returns stop(). */
export function startStream(opts: StreamOptions = {}): () => void {
  const url = opts.url ?? '/api/signals/stream';
  const staleAfterMs = opts.staleAfterMs ?? 15_000;
  const reconnectMs = opts.reconnectMs ?? 3_000;
  const flushMs = opts.flushMs ?? 250;

  let source: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  let healthTimer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;
  let lastMessageAt = 0;
  let errored = false;
  let parseErrors = 0;
  let closedKey = '';
  let tickBuffer: Record<string, number> = {};

  const setStream = (state: 'connecting' | 'live' | 'reconnecting' | 'stale', ageSec = 0) => {
    const cur = appStore.getState().stream;
    if (cur.state === state && (state === 'live' || cur.ageSec === ageSec)) return;
    appStore.setState({ stream: { state, ageSec } });
  };

  const touch = () => { lastMessageAt = Date.now(); };

  const refetchClosed = async () => {
    try {
      const res = await apiFetch('/api/paper/portfolio');
      if (res.status === 401) { appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } })); return; }
      if (!res.ok) { markError('closedTrades', `Closed trades unavailable (${res.status})`); return; }
      const data = (await res.json()) as PaperPortfolio;
      if (!stopped) appStore.setState((s) => ({ closedTrades: data.closed_trades ?? [], meta: { ...s.meta, closedTrades: { asOf: Date.now(), status: 'ready' } } }));
    } catch (e) {
      markError('closedTrades', e instanceof Error ? e.message : 'Closed trades unavailable');
    }
  };

  const maybeRefetchClosed = (scanner: ScannerState) => {
    const key = `${scanner.paper_portfolio?.closed_trades_count ?? ''}|${scanner.active_mode}`;
    if (key !== closedKey) {
      closedKey = key;
      void refetchClosed();
    }
  };

  const applySnapshot = (data: ScannerState) => {
    appStore.setState((s) => {
      const merged = keepIdentity(s.scanner, data);
      return { scanner: merged, meta: { ...s.meta, scanner: { asOf: Date.now(), status: 'ready' }, portfolio: data.paper_portfolio ? { asOf: Date.now(), status: 'ready' } : s.meta.portfolio } };
    });
    maybeRefetchClosed(data);
  };

  const flushTicks = () => {
    flushTimer = null;
    const buf = tickBuffer;
    tickBuffer = {};
    const syms = Object.keys(buf);
    if (syms.length === 0) return;
    appStore.setState((s) => {
      let radar = s.scanner.radar;
      let changed = false;
      const next = { ...radar };
      for (const sym of syms) {
        const prev = radar[sym];
        if (prev && prev.close !== buf[sym]) { next[sym] = { ...prev, close: buf[sym] }; changed = true; }
      }
      if (!changed) return {};
      radar = next;
      return { scanner: { ...s.scanner, radar } };
    });
  };

  const parse = (raw: string): unknown => {
    try {
      return JSON.parse(raw);
    } catch {
      parseErrors += 1;
      setSlice('stream', { error: `Malformed stream message (${parseErrors})` });
      return undefined;
    }
  };

  const connect = () => {
    if (stopped) return;
    source?.close();
    const es = new EventSource(url);
    source = es;

    es.addEventListener('tick', (event: Event) => {
      const data = parse((event as MessageEvent).data) as { symbol?: string; ltp?: number; is_option?: boolean } | undefined;
      if (!data || !data.symbol || !data.ltp || data.is_option) return;
      tickBuffer[data.symbol] = data.ltp;
      if (!flushTimer) flushTimer = setTimeout(flushTicks, flushMs);
    });

    es.addEventListener('portfolio', (event: Event) => {
      const data = parse((event as MessageEvent).data) as { paper_portfolio?: PaperPortfolio } | undefined;
      if (!data?.paper_portfolio) return;
      touch();
      const pp = data.paper_portfolio;
      appStore.setState((s) => ({
        scanner: { ...s.scanner, paper_portfolio: keepIdentity(s.scanner.paper_portfolio, pp) as PaperPortfolio },
        meta: { ...s.meta, portfolio: { asOf: Date.now(), status: 'ready' } },
      }));
      maybeRefetchClosed(appStore.getState().scanner);
    });

    es.onmessage = (event: MessageEvent) => {
      const data = parse(event.data) as ScannerState | undefined;
      if (!data || typeof data !== 'object') return;
      touch();
      errored = false;
      setStream('live');
      markReady('stream');
      applySnapshot(data);
    };

    es.onerror = () => {
      es.close();
      if (source === es) source = null;
      errored = true;
      if (lastMessageAt === 0) touch();
      setStream('reconnecting');
      if (!stopped) {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, reconnectMs);
      }
    };
  };

  const fetchSnapshot = async () => {
    try {
      const res = await apiFetch('/api/signals');
      if (res.status === 401) { appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } })); return false; }
      if (res.ok) {
        const data = (await res.json()) as ScannerState;
        if (!stopped) applySnapshot({ ...appStore.getState().scanner, ...data });
      }
    } catch {
      /* the stream will hydrate the state */
    }
    return true;
  };

  healthTimer = setInterval(() => {
    if (lastMessageAt === 0) return;
    const age = Math.round((Date.now() - lastMessageAt) / 1000);
    if (errored) { setStream('reconnecting', age); return; }
    if (Date.now() - lastMessageAt > staleAfterMs) {
      setStream('stale', age);
      appStore.setState((s) => ({ meta: { ...s.meta, stream: { ...s.meta.stream, status: 'stale' }, scanner: { ...s.meta.scanner, status: 'stale' }, portfolio: { ...s.meta.portfolio, status: 'stale' } } }));
    }
  }, 1000);

  void (async () => {
    const ok = await fetchSnapshot();
    if (!stopped && ok) connect();
  })();

  return () => {
    stopped = true;
    source?.close();
    source = null;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (flushTimer) clearTimeout(flushTimer);
    if (healthTimer) clearInterval(healthTimer);
    reconnectTimer = flushTimer = null;
    healthTimer = null;
  };
}

