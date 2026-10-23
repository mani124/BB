import { describe, it, expect } from 'vitest';
import { addDays, cleanRange, rangeError, rangeQuery, validDate } from './range';

// 2026-10-22 20:00 UTC is already 2026-10-23 01:30 in IST.
const lateUtc = new Date('2026-10-22T20:00:00Z');
const noon = new Date('2026-10-22T06:30:00Z');

describe('range', () => {
  it('uses the IST date, not the UTC date', () => {
    expect(rangeQuery({ range: 'today' }, lateUtc)).toEqual({ from: '2026-10-23', to: '2026-10-23' });
    expect(rangeQuery({ range: 'today' }, noon)).toEqual({ from: '2026-10-22', to: '2026-10-22' });
  });
  it('5D and 20D count calendar days including today', () => {
    expect(rangeQuery({ range: '5d' }, noon)).toEqual({ from: '2026-10-18', to: '2026-10-22' });
    expect(rangeQuery({ range: '20d' }, noon)).toEqual({ from: '2026-10-03', to: '2026-10-22' });
  });
  it('All sends no bounds', () => { expect(rangeQuery({ range: 'all' }, noon)).toEqual({}); });
  it('addDays crosses month and year ends', () => {
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
  });
  it('custom range needs valid dates with from <= to', () => {
    expect(rangeError({ range: 'custom', from: '2026-10-20', to: '2026-10-19' })).toMatch(/must not be after/);
    expect(rangeError({ range: 'custom', from: '2026-10-20' })).toMatch(/both dates/);
    expect(rangeError({ range: 'custom', from: '2026-02-30', to: '2026-03-01' })).toMatch(/both dates/);
    expect(rangeError({ range: 'custom', from: '2026-10-19', to: '2026-10-19' })).toBeNull();
    expect(rangeQuery({ range: 'custom', from: '2026-10-20', to: '2026-10-19' })).toEqual({});
    expect(rangeQuery({ range: 'custom', from: '2026-10-01', to: '2026-10-05' })).toEqual({ from: '2026-10-01', to: '2026-10-05' });
  });
  it('validDate rejects impossible dates', () => { expect(validDate('2026-13-01')).toBe(false); expect(validDate('2026-10-22')).toBe(true); });
  it('cleanRange drops unknown ranges and bad dates', () => {
    expect(cleanRange({ range: 'bogus', from: 'x' })).toEqual({ range: 'all', from: undefined, to: undefined });
  });
});
