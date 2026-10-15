import { describe, it, expect } from 'vitest';
import { setupIndicators } from './PositionChartModal';

describe('setupIndicators', () => {
  it('maps each setup to the overlays it is evaluated on', () => {
    expect(setupIndicators('Setup 2: Walking the Bands (9 EMA)')).toEqual(['bb', 'ema']);
    expect(setupIndicators('Setup 4: 9:30 AM Opening Range Breakout')).toEqual(['orb', 'vwap']);
    expect(setupIndicators('Setup 5: Option Chart BB Scalp')).toEqual(['bb', 'vwap', 'ema']);
    expect(setupIndicators('Setup 7: 2.5σ Puncture & Inside Bar')).toContain('bb25');
    expect(setupIndicators('Setup 1: BB Squeeze Breakout')).toEqual(['bb']);
  });
});
