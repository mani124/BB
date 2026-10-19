export type DashboardBook = 'paper' | 'cx' | 'earnings';
export type WatchBook = DashboardBook | 'setup16';
export type SourceState = 'ready' | 'stale' | 'error' | 'disabled' | 'unknown';

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
