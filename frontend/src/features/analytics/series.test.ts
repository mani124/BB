import { describe, it, expect } from 'vitest';
import { toChartSeries } from './series';

const p = (t: string, equity: number, drawdown = 0) => ({ t, equity, drawdown, day_pnl: 0 });

describe('toChartSeries', () => {
  it('keeps times strictly ascending when trades share a second', () => {
    const s = toChartSeries([p('2026-10-19T10:00:00+05:30', 1), p('2026-10-19T10:00:00+05:30', 2), p('2026-10-19T09:59:59+05:30', 3)]);
    const times = s.equity.map((x) => x.time);
    expect(times[1]).toBe(times[0] + 1);
    expect(times[2]).toBe(times[1] + 1);
  });
  it('plots drawdown below zero and skips unreadable times', () => {
    const s = toChartSeries([p('bad', 1), p('2026-10-19T10:00:00+05:30', 5, 3)]);
    expect(s.equity).toHaveLength(1);
    expect(s.drawdown[0].value).toBe(-3);
  });
});
