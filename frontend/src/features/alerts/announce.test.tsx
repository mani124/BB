import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { newSignalMessage, riskMessage, useAnnouncements } from './announce';
import { appStore, resetAppStore } from '../../data/appStore';

const sig = (id: string, extra: object = {}) => ({ id, symbol: 'NIFTY', option_type: 'CE', ...extra });

describe('announcements', () => {
  it('names the first new confirmed signal and counts the rest', () => {
    const seen = new Set<string>(['a']);
    expect(newSignalMessage(seen, [sig('a'), sig('b'), sig('c')])).toBe('New signal: NIFTY CE and 1 more');
    expect(newSignalMessage(seen, [sig('a'), sig('b'), sig('c')])).toBe('');
  });
  it('ignores unconfirmed signals', () => {
    expect(newSignalMessage(new Set(), [sig('x', { is_confirmed: false })])).toBe('');
  });
  it('words the risk states', () => {
    expect(riskMessage({ kill_switch_active: true })).toMatch(/Kill switch is on/);
    expect(riskMessage({ loss_cap_tripped: true })).toMatch(/loss cap/);
    expect(riskMessage(undefined)).toBe('');
  });
});

describe('useAnnouncements', () => {
  beforeEach(() => resetAppStore());
  it('stays quiet for signals present at load and announces later ones and the kill switch', () => {
    const announce = vi.fn();
    const scan = (signals: unknown[], risk?: object) => appStore.setState((s) => ({ scanner: { ...s.scanner, last_scan_time: '2026-10-22T10:00:00', signals, paper_portfolio: risk ? { ...(s.scanner.paper_portfolio ?? {}), risk } : s.scanner.paper_portfolio } as never }));
    act(() => scan([sig('old')]));
    renderHook(() => useAnnouncements(announce));
    expect(announce).not.toHaveBeenCalled();
    act(() => scan([sig('old'), sig('new')]));
    expect(announce).toHaveBeenCalledWith('New signal: NIFTY CE');
    act(() => scan([sig('old'), sig('new')], { kill_switch_active: true }));
    expect(announce).toHaveBeenCalledWith('Kill switch is on. New entries are paused.');
  });
});
