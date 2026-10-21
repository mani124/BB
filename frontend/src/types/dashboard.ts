export type DashboardBook = 'paper' | 'cx' | 'earnings';
export type WatchBook = DashboardBook;
export type SourceState = 'ready' | 'stale' | 'error' | 'disabled' | 'idle' | 'unknown';

export interface DashboardSource {
  book: WatchBook;
  mode: string;
  as_of: string | null;
  state: SourceState;
  message: string;
}

export interface DashboardCandidate {
  id: string;
  book: WatchBook;
  stage: string;
  observed_at: string | null;
  is_preview: boolean;
  checks: { name: string; value: unknown }[];
  block_reason: string | null;
  instrument: string;
  setup: string;
  detail: string;
  source_ref: Record<string, unknown>;
}

export interface DashboardWatch {
  observed_at: string;
  sources: DashboardSource[];
  candidates: DashboardCandidate[];
}

export interface DashboardTrade {
  id: string;
  book: DashboardBook;
  display_book: string;
  source_id: string;
  status: string;
  instrument: string;
  setup: string;
  opened_at: string | null;
  closed_at: string | null;
  mode: string;
  net_pnl: number | null;
  net_kind: 'estimated' | 'realized';
  evidence_state: 'recorded' | 'unavailable';
  exit_reason?: string | null;
  signal_id?: string | null;
  quarantine_reason?: string | null;
}

export interface DashboardTradeDetail extends DashboardTrade {
  reason_state: 'recorded' | 'unavailable';
  decision: Record<string, unknown> | null;
}

export interface DashboardCandle { time: number; open: number; high: number; low: number; close: number }
export interface DashboardChartSeries {
  key: string;
  label: string;
  candles: DashboardCandle[];
  indicators: Record<string, { time: number; value: number }[]>;
  levels: Record<string, number>;
  interval: string;
}
export interface DashboardChart {
  candle_state: 'recorded' | 'unavailable';
  entry_time: number | null;
  exit_time: number | null;
  series: DashboardChartSeries[];
}

export interface DashboardSessionEvent {
  id: string;
  at: string;
  type: 'decision' | 'entry' | 'exit' | 'error' | 'control';
  book: string | null;
  trade_id: string | null;
  instrument: string | null;
  title: string;
  reason: string | null;
  metrics: Record<string, unknown>;
  evidence_id: string | null;
  evidence_state: 'recorded' | 'unavailable';
}

export interface DashboardSession {
  day: string;
  timezone: string;
  events: DashboardSessionEvent[];
  by_book: { book: DashboardBook; mode?: string | null; display_book: string; entries: number; exits: number; open_positions?: number | null; realized_net: number | null; estimated_net: number | null }[];
  observations: { id: string; title: string; detail: string; event_ids: string[] }[];
}
