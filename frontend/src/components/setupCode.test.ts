import { describe, expect, it } from 'vitest';
import { setupCode } from './setupCode';

describe('setupCode', () => {
  it('reads two-digit setup numbers', () => {
    expect(setupCode('Setup 10: ATM Straddle Premium Squeeze')).toBe('S10');
    expect(setupCode('SETUP_10_STRADDLE_SQUEEZE')).toBe('S10');
  });
  it('keeps single-digit setups unchanged', () => {
    expect(setupCode('Setup 1: BB Squeeze Breakout')).toBe('S1');
    expect(setupCode('Setup 9: Relative Strength vs NIFTY (9 EMA Pullback)')).toBe('S9');
  });
});
