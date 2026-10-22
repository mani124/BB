import { describe, it, expect } from 'vitest';
import { inr, pct, points, signedClass } from './numbers';

describe('numbers', () => {
  it('formats rupees with Indian grouping', () => {
    expect(inr(1234567)).toBe('₹12,34,567');
    expect(inr(-5, { sign: true })).toBe('-₹5');
    expect(inr(5, { sign: true })).toBe('+₹5');
    expect(inr(0, { sign: true })).toBe('₹0');
    expect(inr(-0.2, { sign: true })).toBe('₹0');
    expect(inr(null)).toBe('—');
    expect(inr(NaN)).toBe('—');
  });
  it('formats percent and points', () => {
    expect(pct(12.345)).toBe('12.3%');
    expect(pct(12.345, 2)).toBe('12.35%');
    expect(pct(undefined)).toBe('—');
    expect(points(1.5)).toBe('1.50');
  });
  it('signedClass', () => {
    expect(signedClass(1)).toBe('desk-up');
    expect(signedClass(-1)).toBe('desk-down');
    expect(signedClass(0)).toBe('');
  });
});
