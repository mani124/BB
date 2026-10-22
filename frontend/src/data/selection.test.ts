import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';
import { appStore, resetAppStore } from './appStore';
import { defaultSelection, effectiveSelection, resolveSelection, select, useSelection, type Selection } from './selection';

const sig = (id: string) => ({ id, symbol: id }) as never;
const withData = () => appStore.setState((s) => ({
  scanner: { ...s.scanner, signals: [sig('s1'), sig('s2')], paper_portfolio: { active_positions: [{ id: 'p1' }] } as never },
  trades: [{ id: 't1' } as never],
  watch: { candidates: [{ id: 'c1' }], sources: [], observed_at: '' } as never,
}));

beforeEach(() => resetAppStore());

describe('selection', () => {
  it('select and clear', () => {
    select({ kind: 'signal', id: 's1' });
    expect(appStore.getState().selection).toEqual({ kind: 'signal', id: 's1' });
    select(null);
    expect(appStore.getState().selection).toBeNull();
  });

  it('default rule: first open position, else newest signal, else nothing', () => {
    expect(defaultSelection(appStore.getState())).toBeNull();
    withData();
    expect(defaultSelection(appStore.getState())).toEqual({ kind: 'position', id: 'p1' });
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: { active_positions: [] } as never } }));
    expect(effectiveSelection(appStore.getState())).toEqual({ kind: 'signal', id: 's1' });
  });

  it('resolves by id in refreshed data', () => {
    withData();
    select({ kind: 'signal', id: 's2' });
    expect(resolveSelection(appStore.getState()).signal?.id).toBe('s2');
    appStore.setState((s) => ({ scanner: { ...s.scanner, signals: [{ id: 's2', symbol: 'NEW' } as never] } }));
    expect((resolveSelection(appStore.getState()).signal as { symbol: string }).symbol).toBe('NEW');
    select({ kind: 'trade', id: 't1' });
    expect(resolveSelection(appStore.getState()).trade?.id).toBe('t1');
    select({ kind: 'candidate', id: 'c1' });
    expect(resolveSelection(appStore.getState()).candidate?.id).toBe('c1');
    select({ kind: 'signal', id: 'gone' });
    expect(resolveSelection(appStore.getState()).signal).toBeUndefined();
  });

  it('a pinned panel ignores later selection changes', () => {
    withData();
    select({ kind: 'signal', id: 's1' });
    let seen: Selection = null;
    const C = ({ pinned }: { pinned: boolean }) => { seen = useSelection({ pinned }); return null; };
    const { rerender } = render(React.createElement(C, { pinned: false }));
    expect(seen).toEqual({ kind: 'signal', id: 's1' });
    rerender(React.createElement(C, { pinned: true }));
    act(() => select({ kind: 'signal', id: 's2' }));
    expect(seen).toEqual({ kind: 'signal', id: 's1' });
    rerender(React.createElement(C, { pinned: false }));
    expect(seen).toEqual({ kind: 'signal', id: 's2' });
  });
});
