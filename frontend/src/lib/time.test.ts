import { describe, it, expect } from 'vitest';
import { ageSeconds, formatIst, istToday, marketSession, toIst } from './time';

describe('time', () => {
  it('formats a UTC instant as IST wall time', () => {
    expect(formatIst('2026-10-22T03:45:10Z', 'time')).toBe('09:15:10');
    expect(formatIst('2026-10-22T03:45:10Z', 'date')).toBe('2026-10-22');
    expect(formatIst('2026-10-22T20:00:00Z', 'datetime')).toBe('2026-10-23 01:30:00');
    expect(formatIst('2026-10-22T09:30:00+05:30', 'time')).toBe('09:30:00');
    expect(formatIst('garbage')).toBe('');
  });
  it('toIst gives weekday and parts', () => {
    const t = toIst('2026-10-24T05:00:00Z'); // Saturday 10:30 IST
    expect(t.weekday).toBe(6);
    expect(t.hour).toBe(10);
    expect(t.minute).toBe(30);
  });
  it('ageSeconds never goes negative', () => {
    expect(ageSeconds(10_000, 15_000)).toBe(5);
    expect(ageSeconds(20_000, 15_000)).toBe(0);
  });
  it('marketSession boundaries', () => {
    const at = (ist: string) => new Date(`${ist}+05:30`);
    expect(marketSession(at('2026-10-22T09:14:00'))).toBe('pre-open');
    expect(marketSession(at('2026-10-22T09:15:00'))).toBe('open');
    expect(marketSession(at('2026-10-22T15:29:59'))).toBe('open');
    expect(marketSession(at('2026-10-22T15:30:00'))).toBe('closed');
    expect(marketSession(at('2026-10-22T15:31:00'))).toBe('closed');
    expect(marketSession(at('2026-10-24T11:00:00'))).toBe('weekend');
    expect(marketSession(at('2026-10-25T11:00:00'))).toBe('weekend');
  });
  it('istToday uses the IST date near midnight UTC', () => {
    expect(istToday(new Date('2026-10-22T19:00:00Z'))).toBe('2026-10-23');
  });
});
