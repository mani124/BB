import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { appStore, resetAppStore, sliceStale, useSliceMeta, markReady, markError, applyPortfolio } from './appStore';

beforeEach(() => resetAppStore());

describe('appStore', () => {
  it('sliceStale honours status and age', () => {
    expect(sliceStale({ asOf: 1000, status: 'ready' }, 'watch', 1000 + 59_000)).toBe(false);
    expect(sliceStale({ asOf: 1000, status: 'ready' }, 'watch', 1000 + 61_000)).toBe(true);
    expect(sliceStale({ asOf: null, status: 'stale' }, 'trades', 0)).toBe(true);
    expect(sliceStale({ asOf: 1, status: 'ready' }, 'closedTrades', 10 ** 12)).toBe(false);
  });

  it('useSliceMeta reports age and error', () => {
    vi.useFakeTimers();
    let latest: ReturnType<typeof useSliceMeta> | undefined;
    const C = () => { latest = useSliceMeta('watch'); return null; };
    render(React.createElement(C));
    act(() => markReady('watch'));
    act(() => { vi.advanceTimersByTime(65_000); });
    expect(latest?.stale).toBe(true);
    expect(latest?.ageSec).toBeGreaterThanOrEqual(65);
    act(() => markError('watch', 'boom'));
    expect(latest?.status).toBe('error');
    expect(latest?.error).toBe('boom');
    vi.useRealTimers();
  });

  it('applyPortfolio replaces portfolio and closed trades', () => {
    applyPortfolio({ active_positions: [], closed_trades: [{ id: 'x' } as never] } as never);
    expect(appStore.getState().closedTrades).toHaveLength(1);
    expect(appStore.getState().meta.portfolio.status).toBe('ready');
  });
});
