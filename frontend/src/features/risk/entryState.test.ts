import { describe, it, expect } from 'vitest';
import { cleanConcentration, concentration, entriesAllowed, entryReasons, lossCapUsage, type EntryInputs } from './entryState';

const base: EntryInputs = { risk: { daily_loss_limit: 24000, day_pnl: 0, loss_cap_tripped: false, kill_switch_active: false, entries_blocked: false }, autoTrade: true, openCount: 1, maxOpen: 5, session: 'open', stream: 'live' };
const codes = (o: Partial<EntryInputs>) => entryReasons({ ...base, ...o }).map((r) => r.code);

describe('entryReasons', () => {
  it('allows entries when nothing blocks', () => { const r = entryReasons(base); expect(r).toEqual([]); expect(entriesAllowed(r)).toBe(true); });
  it('lists each reason', () => {
    expect(codes({ risk: { ...base.risk!, kill_switch_active: true } })).toEqual(['kill_switch']);
    expect(codes({ risk: { ...base.risk!, loss_cap_tripped: true } })).toEqual(['loss_cap']);
    expect(codes({ autoTrade: false })).toEqual(['auto_enter_off']);
    expect(codes({ openCount: 5 })).toEqual(['max_open']);
    expect(codes({ session: 'closed' })).toEqual(['market_closed']);
    expect(codes({ stream: 'stale' })).toEqual(['stream_stale']);
    expect(codes({ stream: 'reconnecting' })).toEqual(['stream_stale']);
  });
  it('orders reasons by importance and a capped pool alone does not block', () => {
    const r = entryReasons({ ...base, risk: { ...base.risk!, kill_switch_active: true, loss_cap_tripped: true, capped_pools: ['S11'] }, autoTrade: false, openCount: 9, session: 'weekend', stream: 'stale' });
    expect(r.map((x) => x.code)).toEqual(['kill_switch', 'loss_cap', 'capped_pools', 'auto_enter_off', 'max_open', 'market_closed', 'stream_stale']);
    const only = entryReasons({ ...base, risk: { ...base.risk!, capped_pools: ['S11'] } });
    expect(only).toHaveLength(1);
    expect(entriesAllowed(only)).toBe(true);
  });
  it('max open of 0 or null means no limit', () => { expect(codes({ maxOpen: 0, openCount: 50 })).toEqual([]); expect(codes({ maxOpen: null, openCount: 50 })).toEqual([]); });
  it('missing risk and autoTrade do not invent blocks', () => { expect(codes({ risk: null, autoTrade: undefined })).toEqual([]); });
});

describe('lossCapUsage', () => {
  it('is null when the cap is off', () => { expect(lossCapUsage({ ...base.risk!, daily_loss_limit: 0 })).toBeNull(); expect(lossCapUsage(null)).toBeNull(); });
  it('uses the loss share, clamps and ignores profit', () => {
    expect(lossCapUsage({ ...base.risk!, day_pnl: -12000 })).toBe(0.5);
    expect(lossCapUsage({ ...base.risk!, day_pnl: -99999 })).toBe(1);
    expect(lossCapUsage({ ...base.risk!, day_pnl: 500 })).toBe(0);
  });
});

describe('concentration', () => {
  const rows = (a: number, b: number) => [{ key: 'A', count: 1, risk_rupees: 1, notional: a }, { key: 'B', count: 1, risk_rupees: 1, notional: b }];
  it('reports the largest share', () => { expect(concentration(rows(50, 50))).toEqual({ pct: 50, key: 'A' }); expect(concentration(rows(49, 51)).key).toBe('B'); });
  it('is zero for no notional', () => { expect(concentration([])).toEqual({ pct: 0, key: null }); expect(concentration(rows(0, 0)).pct).toBe(0); });
  it('validates the threshold to 10..100', () => {
    expect(cleanConcentration(5)).toBe(10); expect(cleanConcentration(500)).toBe(100); expect(cleanConcentration('x')).toBe(50); expect(cleanConcentration(NaN)).toBe(50); expect(cleanConcentration(33.4)).toBe(33);
  });
});
