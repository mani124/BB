export interface RiskRow {
  id: string; symbol: string; strike_symbol: string; side: 'CE' | 'PE'; setup: string; pool: string; qty: number;
  entry: number; stop: number; risk_rupees: number; notional: number; distance_pct: number | null; t1: number;
}
export interface RiskGroup { key: string; count: number; risk_rupees: number; notional: number }
export interface RiskReport {
  open: RiskRow[];
  totals: { risk_rupees: number; notional: number; count: number; max_open: number | null; max_open_key: string };
  by_underlying: RiskGroup[]; by_side: RiskGroup[]; by_pool: RiskGroup[]; by_setup: RiskGroup[];
  generated_at: string;
}

export interface Bucket {
  key?: string; trades: number; wins?: number; losses?: number; win_rate?: number; net_pnl?: number; gross_pnl?: number; charges?: number;
  slippage_cost?: number; expectancy?: number; profit_factor?: number | null; payoff_ratio?: number | null; avg_r?: number | null;
  max_drawdown?: number; avg_minutes_held?: number | null; cost_drag_pct?: number | null; low_sample?: boolean;
  avg_win?: number; avg_loss?: number; best_trade?: number; worst_trade?: number; max_consecutive_losses?: number;
}
export interface AttributionReport { group: string; buckets: Bucket[]; overall: Bucket; generated_at: string; excluded: number }

export interface EquityPoint { t: string; equity: number; day_pnl: number; drawdown: number }
export interface DrawdownEpisode { start: string; trough: string; end: string | null; depth: number }
export interface EquityReport {
  points: EquityPoint[];
  summary: { net: number; max_drawdown: number; current_drawdown: number; longest_drawdown_days: number; drawdowns: DrawdownEpisode[] };
  generated_at: string; excluded: number;
}

export interface HistBin { lo: number; hi: number; count: number }
export interface Percentiles { p10: number | null; p50: number | null; p90: number | null }
export interface DistributionReport {
  pnl: HistBin[]; r: HistBin[]; hold_minutes: HistBin[];
  mfe_mae: { id: string; mfe: number; mae: number; final: number }[];
  medians: { pnl: Percentiles; r: Percentiles; hold_minutes: Percentiles };
  generated_at: string; excluded: number;
}

export interface SlipRow { key: string; trades: number; entry_avg: number | null; exit_avg: number | null; total_cost: number }
export interface ChargeRow { key: string; brokerage: number; stt: number; exchange_fee: number; sebi_fee: number; stamp_duty: number; gst: number; total: number; trades: number }
export interface ExecutionReport {
  slippage: { entry: number[]; exit: number[]; by_setup: SlipRow[]; by_hour: SlipRow[] };
  spread: { points: { spread_pct: number; slippage: number }[]; buckets: { label: string; trades: number; avg_slippage: number | null }[] };
  liquidity: { quartiles: { q: number; volume_lo: number; volume_hi: number; trades: number; avg_slippage: number | null; net_pnl: number }[] };
  charges: { totals: Record<string, number>; by_setup: ChargeRow[] };
  not_recorded: string[];
  generated_at: string; excluded: number;
}
