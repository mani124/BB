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
  risk: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
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

export interface ScannerState {
  signals: Signal[];
  radar: Record<string, IndexRadarItem>;
  last_scan_time: string;
  scan_cycle_count: number;
  is_scanning: boolean;
  scan_progress: number;
  universe_count: number;
  active_mode: 'live' | 'demo';
}
