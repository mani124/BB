import { describe, expect, it } from 'vitest';
import { countOpenTrades } from './dashboardCounts';
import type { DashboardTrade } from '../types/dashboard';

describe('countOpenTrades', () => {
  it('counts active positions once across all recorded books', () => {
    const rows = [
      { book: 'paper', status: 'TARGET_1' },
      { book: 'earnings', status: 'OPEN' },
      { book: 'paper', status: 'CLOSED' },
    ] as DashboardTrade[];
    expect(countOpenTrades(rows)).toBe(2);
  });
});
