import { describe, it, expect } from 'vitest';
import { isIndexSymbol } from './instruments';

describe('isIndexSymbol', () => {
  it('recognises index names and aliases, case-insensitively', () => {
    for (const s of ['NIFTY 50', 'nifty bank', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY']) {
      expect(isIndexSymbol(s)).toBe(true);
    }
  });
  it('treats stocks and missing symbols as non-index', () => {
    expect(isIndexSymbol('RELIANCE')).toBe(false);
    expect(isIndexSymbol(undefined)).toBe(false);
  });
});
