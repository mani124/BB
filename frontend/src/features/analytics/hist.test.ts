import { describe, it, expect } from 'vitest';
import { histogram } from './hist';

describe('histogram', () => {
  it('counts every value once and puts the maximum in the last bin', () => {
    const h = histogram([0, 1, 2, 3, 4, 10], 5);
    expect(h).toHaveLength(5);
    expect(h.reduce((a, b) => a + b.count, 0)).toBe(6);
    expect(h[4].count).toBe(1);
  });
  it('handles empty, equal and non-finite values', () => {
    expect(histogram([], 5)).toEqual([]);
    expect(histogram([2, 2, 2], 5)).toEqual([{ lo: 2, hi: 2, count: 3 }]);
    expect(histogram([NaN, 1], 3)).toEqual([{ lo: 1, hi: 1, count: 1 }]);
  });
});
