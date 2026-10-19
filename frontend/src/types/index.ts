export type OptionType = 'CE' | 'PE';

export type SetupType = 
  | 'Setup 1: BB Squeeze Breakout'
  | 'Setup 2: Walking the Bands (9 EMA)'
  | 'Setup 3: W/M Reversal'
  | 'Setup 4: 9:30 AM Opening Range Breakout'
  | 'Setup 5: Option Chart BB Scalp'
  | 'Setup 6: Pin Bar Exhaustion Snapback'
  | 'Setup 7: 2.5σ Puncture & Inside Bar'
  | 'Setup 8: Climax Swing Divergence Fade'
  | 'Setup 9: Relative Strength vs NIFTY (9 EMA Pullback)'
  | 'Setup 10: ATM Straddle Premium Squeeze'
  | 'Setup 11: Filtered Option Chart Scalp'
  | 'Setup 12: ADX + EMA 20 Trend Cross'
  | 'Setup 13: Option VWAP Reclaim'
  | 'Setup 14: OI Wall Bounce'
  | 'Setup 16: Option Squeeze Breakout'
  | 'SETUP_1_SQUEEZE_EXPANSION'
  | 'SETUP_2_WALKING_BANDS'
  | 'SETUP_3_WM_REVERSAL'
  | 'SETUP_4_ORB'
  | 'SETUP_5_OPTION_BB_SCALP'
  | 'SETUP_6_PINBAR_SNAPBACK'
  | 'SETUP_7_INSIDE_BAR_SNAPBACK'
  | 'SETUP_8_DIVERGENCE_SNAPBACK'
  | 'SETUP_9_RELATIVE_STRENGTH'
  | 'SETUP_10_STRADDLE_SQUEEZE'
  | 'SETUP_11_FILTERED_OPTION_BB'
  | 'SETUP_12_ADX_EMA_CROSS'
  | 'SETUP_13_OPTION_VWAP_RECLAIM'
  | 'SETUP_14_OI_WALL_BOUNCE'
  | 'SETUP_16_OPTION_SQUEEZE_BREAK';

export interface OptionStrikeRecommendation {
  symbol: string;
  underlying_price: number;
  option_type: OptionType;
  atm_strike: number;
  recommended_strike: number;
  strike_symbol: string;
  lot_size: number;
  // Spot levels
  risk: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  // Option premium levels (Delta ~0.55)
  estimated_option_entry: number;
  option_sl_pts: number;
  option_target_1_pts: number;
  option_target_2_pts: number;
  option_sl_price: number;
  option_target_1_price: number;
  option_target_2_price: number;
  option_security_id?: string;
  expiry_date?: string;
  real_ask_price?: number;
  real_bid_price?: number;
  real_ltp?: number;
  real_delta?: number;
  is_live_quote?: boolean;
}

export interface Signal {
  id: string;
  symbol: string;
  timeframe: string;
  setup_type: SetupType;
  option_type: OptionType;
  timestamp: string;
  is_confirmed?: boolean;
  entry_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  strike_recommendation: OptionStrikeRecommendation;
  indicators_snapshot: {
    close: number;
    bb_upper: number;
    bb_middle: number;
    bb_lower: number;
    bandwidth: number;
    percent_b: number;
    vwap: number;
    rsi: number;
    ema_9: number;
    adx: number;
  };
  rationale: string;
}

export interface IndexRadarItem {
  symbol: string;
  close: number;
  change_pct: number;
  percent_b: number;
  bandwidth: number;
  is_squeeze: boolean;
  vwap_bias: 'ABOVE_VWAP' | 'BELOW_VWAP';
  rsi: number;
  trend_state: 'BULLISH_WALK' | 'BEARISH_WALK' | 'SQUEEZE' | 'RANGE';
}

export interface TradeChargesBreakdown {
  buy_turnover: number;
  sell_turnover: number;
  total_turnover: number;
  orders_count: number;
  brokerage: number;
  stt: number;
  exchange_fee: number;
  sebi_fee: number;
  stamp_duty: number;
  gst: number;
  total_charges: number;
}

export interface PaperPosition {
  id: string;
  signal_id: string;
  symbol: string;
  option_type: OptionType;
  strike_symbol: string;
  timeframe: string;
  setup_type: string;
  entry_time: string;
  underlying_entry: number;
  underlying_sl: number;
  underlying_target_1: number;
  underlying_target_2: number;
  option_entry: number;
  option_sl: number;
  option_target_1: number;
  option_target_2: number;
  lot_size: number;
  lots: number;
  quantity: number;
  current_underlying: number;
  current_option_price: number;
  pnl_points: number;
  pnl_rupees: number;
  status: 'OPEN' | 'TARGET_1' | 'TARGET_2' | 'STOPPED_OUT' | 'CLOSED';
  exit_time?: string;
  entry_datetime?: string | null;
  exit_datetime?: string | null;
  quarantine_reason?: string | null;
  entry_estimated?: boolean;
  // Liquidity at entry (absent when the feed did not supply it).
  entry_bid?: number | null;
  entry_spread_pct?: number | null;
  option_volume?: number | null;
  option_oi?: number | null;
  bid_qty?: number | null;
  ask_qty?: number | null;
  exit_reason?: string;
  initial_lots?: number;
  initial_quantity?: number;
  booked_lots?: number;
  booked_pnl_rupees?: number;
  unrealized_pnl_rupees?: number;
  est_exit_charges?: number;
  est_net_pnl?: number;
  option_security_id?: string;
  theoretical_entry?: number;
  entry_slippage?: number;
  theoretical_exit?: number;
  exit_slippage?: number;
  total_slippage_cost?: number;
  gross_pnl?: number;
  total_charges?: number;
  net_pnl?: number;
  charges_breakdown?: TradeChargesBreakdown;
}

export type SetupMode = 'off' | 'index' | 'stocks' | 'all';

export interface RiskStatus {
  daily_loss_limit: number; // 0 = cap disabled
  day_pnl: number;
  loss_cap_tripped: boolean;
  loss_cap_reason?: string | null;
  kill_switch_active: boolean;
  kill_switch_since?: string | null;
  entries_blocked: boolean;
  block_reason?: string | null;
}

export interface PaperPortfolio {
  active_positions: PaperPosition[];
  // Empty in the live stream; filled by GET /api/paper/portfolio.
  closed_trades: PaperPosition[];
  closed_trades_count?: number;
  risk?: RiskStatus | null;
  auto_trade_enabled: boolean;
  // Setup number ('1'..'11') -> off | index | stocks | all
  setup_modes?: Record<string, SetupMode>;
  default_lots: number;
  max_risk_per_trade?: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_unrealized_charges?: number;
  total_unrealized_net?: number;
  total_pnl: number;
  win_rate_pct: number;
  total_trades_count: number;
  winning_trades_count: number;
  losing_trades_count: number;
  total_gross_pnl?: number;
  total_slippage_cost?: number;
  avg_slippage_points?: number;
  total_charges?: number;
  total_net_pnl?: number;
}

export interface ScannerState {
  signals: Signal[];
  radar: Record<string, IndexRadarItem>;
  top_bullish?: string[];
  top_bearish?: string[];
  market_bias?: string;
  paper_portfolio?: PaperPortfolio;
  last_scan_time: string;
  scan_cycle_count: number;
  last_scan_seconds?: number;
  is_scanning: boolean;
  scan_progress: number;
  universe_count: number;
  active_mode: 'live' | 'demo' | 'stale' | 'error' | string;
  feed_status?: 'WS_LIVE' | 'LIVE' | 'STALE' | 'ERROR' | 'DEMO' | 'HTTP_POLLING' | string;
  feed_mode?: 'websocket_live' | 'http_polling' | 'demo' | 'disconnected' | string;
  ws_connected?: boolean;
  last_quote_time?: string;
}


// ---- runtime settings, telemetry and earnings ----
export type AppTab = 'scanner' | 'paper' | 'setup16' | 'earnings' | 'settings';

export interface RuntimeSetting {
  key: string;
  label: string;
  group: string;
  type: 'int' | 'float' | 'bool' | 'str' | 'time';
  unit: string;
  description: string;
  value: number | boolean | string;
  default: number | boolean | string;
  overridden: boolean;
  min: number | null;
  max: number | null;
  choices: string[];
  zero_disables: boolean;
}
export interface RuntimeSettingsPayload { groups: string[]; settings: RuntimeSetting[] }
export interface SettingAuditRow { changed_at: string; key: string; old_value: string; new_value: string; actor: string }

export interface PerfBucket {
  key?: string;
  trades: number;
  wins?: number;
  losses?: number;
  win_rate?: number;
  net_pnl?: number;
  gross_pnl?: number;
  charges?: number;
  slippage_cost?: number;
  avg_win?: number;
  avg_loss?: number;
  expectancy?: number;
  profit_factor?: number | null;
  payoff_ratio?: number | null;
  avg_r?: number | null;
  max_drawdown?: number;
  max_consecutive_losses?: number;
  avg_minutes_held?: number | null;
  excursion_trades?: number;
  avg_mfe?: number | null;
  avg_mae?: number | null;
  avg_capture_pct?: number | null;
  losers_that_were_green?: number;
}
export interface PerformanceReport {
  book: string;
  overall: PerfBucket;
  by_setup: PerfBucket[];
  by_symbol: PerfBucket[];
  by_side: PerfBucket[];
  by_entry_hour: PerfBucket[];
  by_exit_reason: PerfBucket[];
  equity_curve: { t: string; equity: number; id: string }[];
}
export interface TelemetryInsights {
  hours: number;
  decisions: { ENTERED: number; SKIPPED: number; EXITED: number; HELD: number; total: number };
  by_strategy: Record<string, Record<string, number>>;
  top_skip_reasons: { reason: string; strategy: string; n: number }[];
  errors: { code: string; component: string; severity: string; n: number; last_seen: string }[];
  excursions: { strategy: string; trades: number; avg_mfe: number; avg_mae: number; avg_final: number }[];
}
export interface DecisionRow {
  id: number; ts: string; book: string; strategy: string; symbol: string; side: string;
  decision: string; reason: string; metrics: Record<string, unknown>;
}
export interface ErrorRow {
  id: number; ts: string; code: string; component: string; severity: string; message: string; stack: string;
}

export interface EarningsLeg {
  security_id: string; opt: 'CE' | 'PE'; strike: number; side: 'BUY' | 'SELL'; entry_price: number;
  current_bid?: number; current_ask?: number;
}
export interface EarningsPosition {
  id: string; mode: string; symbol: string; sector: string; status: 'OPEN' | 'CLOSED';
  opened_at: string; closed_at?: string; earnings_date: string; session: string; expiry: string; exit_date: string;
  lots: number; qty: number; legs: EarningsLeg[]; net_unit: number; max_risk: number;
  spot_entry: number; spot_current: number; unrealized_net: number; mfe: number; mae: number;
  exit_reason?: string; net_pnl?: number; charges?: number;
}
export interface EarningsSummary {
  starting_capital: number; realized_net_pnl: number; unrealized_net_pnl: number; equity: number;
  open_positions: number; closed_trades: number; win_rate: number; profit_factor: number | null;
  avg_win: number; avg_loss: number; total_charges: number; enabled: boolean;
  by_mode: Record<string, { trades: number; net_pnl: number; win_rate: number }>;
  last_cycle: { status?: string; at?: string; error?: string };
}
export interface EarningsCandidate {
  symbol: string; mode: string; ready: boolean; code: string; detail: string;
  earnings_date?: string; expiry?: string; exit_date?: string; net_unit?: number; max_risk?: number;
}
export interface EarningsCalendarRow { symbol: string; earnings_date: string; session: string; sector: string; note: string; source?: string;
  effective_session?: string; session_origin?: 'manual' | 'inferred' | 'default' | 'skip' }

export interface LivePositionRow {
  position_id: string; strike_symbol: string; setup: string; mode: 'LIVE' | 'DRY'; state: string;
  held: number; pending_sell: number; last_error?: string | null;
}
export interface LiveStatus {
  mode: 'off' | 'dry_run' | 'live'; halted: string; broker: string; broker_session: boolean; env_confirmed: boolean;
  armed: boolean; preconditions: string[]; entries_today: number; orders_today: number; realized_today: number;
  positions: LivePositionRow[];
}
export interface LiveOrderRow {
  id: number; ts: string; side: 'BUY' | 'SELL'; mode: 'LIVE' | 'DRY'; trading_symbol: string | null; qty: number;
  order_type: string | null; price: number | null; status: string; filled_qty: number; message: string | null;
}

export interface WatchlistCandidate {
  symbol: string;
  bw_percentile: number;
  bandwidth: number;
  nr7: boolean;
  avg_value_cr: number;
  reasons: string[];
}

export interface WatchlistState {
  enabled?: boolean;
  built_for?: string;
  built_on?: string;
  built_at?: string;
  last_bar_day?: string | null;
  screened?: number;
  candidates?: WatchlistCandidate[];
  last_cycle?: { status?: string };
}

export interface Setup16Contract {
  symbol: string;
  side: 'CE' | 'PE';
  strike_symbol: string;
  source: 'scan' | 'watchlist';
  stage: string;
  bar_time?: string;
  close?: number;
  upper_bb?: number;
  lower_bb?: number;
  pct_to_upper?: number;
  bandwidth?: number;
  session_bw_min?: number;
  recent_bw_min?: number;
  squeeze_limit?: number;
  in_squeeze?: boolean;
  volume?: number;
  stop?: number;
  session_bars?: number;
  needed_bars?: number;
  updated_at?: string;
  stale?: boolean;
}

export interface Setup16Trade {
  id: string;
  strike_symbol: string;
  symbol: string;
  side: string;
  entry_time?: string;
  exit_time?: string | null;
  entry: number;
  stop: number;
  target_1: number;
  target_2: number;
  price: number;
  status: string;
  exit_reason?: string | null;
  lots: number;
  net_pnl: number;
}

export interface Setup16Overview {
  mode: string;
  settings: { stop_pct: number; window_start: string; window_end: string };
  watchlist: WatchlistState;
  funnel: Record<string, number>;
  contracts_checked: number;
  contracts: Setup16Contract[];
  open_positions: Setup16Trade[];
  today_closed: Setup16Trade[];
  today_net_pnl: number;
  stats_all_time: { trades: number; wins: number; win_rate: number; net_pnl: number; avg_r: number | null } | null;
  decisions: { ts: string; symbol: string; side: string; decision: string; reason: string }[];
  as_of: string;
}
