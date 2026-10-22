import type { PaperPosition, ScannerState } from '../types';
import type { DashboardTrade, DashboardWatch } from '../types/dashboard';
import type { StreamStatus } from '../components/Header';

export type SliceName = 'stream' | 'scanner' | 'portfolio' | 'closedTrades' | 'watch' | 'trades' | 'live' | 'health' | 'analytics';

export interface SliceMeta {
  asOf: number | null;
  status: 'idle' | 'loading' | 'ready' | 'stale' | 'error';
  error?: string;
}

export type SelectionKind = 'signal' | 'position' | 'candidate' | 'trade';
export type Selection = { kind: SelectionKind; id: string } | null;

export interface Alert {
  id: string;
  ts: number;
  severity: 'info' | 'warning' | 'critical';
  source: string;
  message: string;
  acked: boolean;
}

/** Loose payloads for endpoints whose panels own the detailed shape. */
export type Json = Record<string, unknown>;

export interface LiveSlice {
  status: Json | null;
  orders: Json[];
}

export interface HealthSlice {
  readiness: Json | null;
  rateLimit: Json | null;
  recorder: Json | null;
  errors: Json[];
}

export interface AppState {
  scanner: ScannerState;
  closedTrades: PaperPosition[];
  watch: DashboardWatch | null;
  trades: DashboardTrade[];
  live: LiveSlice;
  health: HealthSlice;
  analytics: Record<string, unknown>;
  stream: StreamStatus;
  meta: Record<SliceName, SliceMeta>;
  selection: Selection;
  /** Linked filter set by the attribution panel and honoured by trades and perf-summary. */
  filter: { group: string; key: string } | null;
  alerts: Alert[];
  ui: {
    density: 'compact' | 'comfortable';
    workspace: string;
    needsCapability: boolean;
    notifications: boolean;
  };
}
