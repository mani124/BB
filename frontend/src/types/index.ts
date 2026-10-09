export type OptionType = 'CE' | 'PE';

export type SetupType = 
  | 'Setup 1: BB Squeeze Breakout'
  | 'Setup 2: Walking the Bands (9 EMA)'
  | 'Setup 3: W/M Reversal'
  | 'Setup 4: 9:30 AM Opening Range Breakout';

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
  exit_reason?: string;
  initial_lots?: number;
  initial_quantity?: number;
  booked_lots?: number;
  booked_pnl_rupees?: number;
  option_security_id?: string;
}

export interface PaperPortfolio {
  active_positions: PaperPosition[];
  closed_trades: PaperPosition[];
  auto_trade_enabled: boolean;
  default_lots: number;
  max_risk_per_trade?: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_pnl: number;
  win_rate_pct: number;
  total_trades_count: number;
  winning_trades_count: number;
  losing_trades_count: number;
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
  is_scanning: boolean;
  scan_progress: number;
  universe_count: number;
  active_mode: 'live' | 'demo';
}
