import { describe, it, expect } from 'vitest';
import { setupIndicators, snap } from './PositionChartModal';

describe('setupIndicators', () => {
  it('maps each setup to the overlays it is evaluated on', () => {
    expect(setupIndicators('Setup 2: Walking the Bands (9 EMA)')).toEqual(['bb', 'ema']);
    expect(setupIndicators('Setup 4: 9:30 AM Opening Range Breakout')).toEqual(['orb', 'vwap']);
    expect(setupIndicators('Setup 5: Option Chart BB Scalp')).toEqual(['bb', 'vwap', 'ema']);
    expect(setupIndicators('Setup 7: 2.5σ Puncture & Inside Bar')).toContain('bb25');
    expect(setupIndicators('Setup 9: Relative Strength vs NIFTY (9 EMA Pullback)')).toEqual(['ema', 'vwap']);
    expect(setupIndicators('Setup 1: BB Squeeze Breakout')).toEqual(['bb']);
  });
});

describe('snap', () => {
  const candles = [300, 600, 900].map((time) => ({ time, open: 1, high: 1, low: 1, close: 1 }));
  it('returns the candle that contains the time', () => {
    expect(snap(candles, 650)).toBe(600);
    expect(snap(candles, 2000)).toBe(900);
  });
  it('returns null when the time is before the first held candle', () => {
    expect(snap(candles, 100)).toBeNull();
    expect(snap(candles, null)).toBeNull();
  });
});
