import { describe, it, expect } from 'vitest';
import { filterToQuery, tradeMatches } from './filter';
import type { DashboardTrade } from '../../types/dashboard';

const t = (o: Partial<DashboardTrade> = {}): DashboardTrade => ({ id: '1', book: 'paper', display_book: 'Main', source_id: '1', status: 'CLOSED', instrument: 'NIFTY 24500 CE', setup: 'SETUP_1_SQUEEZE_EXPANSION', opened_at: '2026-10-19T03:45:00Z', closed_at: null, mode: 'demo', net_pnl: 1, net_kind: 'realized', evidence_state: 'recorded', exit_reason: 'STOP (x)', ...o });

describe('linked filter', () => {
  it('no filter matches everything', () => { expect(tradeMatches(t(), null)).toBe(true); });
  it('matches setup, symbol, side, exit reason', () => {
    expect(tradeMatches(t(), { group: 'setup', key: 'SETUP_1_SQUEEZE_EXPANSION' })).toBe(true);
    expect(tradeMatches(t(), { group: 'setup', key: 'SETUP_2' })).toBe(false);
    expect(tradeMatches(t(), { group: 'symbol', key: 'NIFTY' })).toBe(true);
    expect(tradeMatches(t(), { group: 'symbol', key: 'BANKNIFTY' })).toBe(false);
    expect(tradeMatches(t(), { group: 'side', key: 'CE' })).toBe(true);
    expect(tradeMatches(t(), { group: 'side', key: 'PE' })).toBe(false);
    expect(tradeMatches(t(), { group: 'exit_reason', key: 'STOP' })).toBe(true);
  });
  it('hour and weekday use IST', () => {
    expect(tradeMatches(t(), { group: 'hour', key: '09:00' })).toBe(true);
    expect(tradeMatches(t(), { group: 'weekday', key: 'Monday' })).toBe(true);
    expect(tradeMatches(t({ opened_at: null }), { group: 'hour', key: '09:00' })).toBe(false);
  });
  it('maps to API query for setup and side only', () => {
    expect(filterToQuery({ group: 'setup', key: 'S' })).toEqual({ setup: 'S' });
    expect(filterToQuery({ group: 'side', key: 'PE' })).toEqual({ side: 'PE' });
    expect(filterToQuery({ group: 'hour', key: '09:00' })).toEqual({});
  });
});
