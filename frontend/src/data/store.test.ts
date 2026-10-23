import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { createStore, keepIdentity, shallowEqual, useStore } from './store';

describe('createStore', () => {
  it('notifies once per setState and stops after unsubscribe', () => {
    const s = createStore({ a: 1, b: 2 });
    const fn = vi.fn();
    const off = s.subscribe(fn);
    s.setState({ a: 2 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(s.getState()).toEqual({ a: 2, b: 2 });
    off();
    s.setState((st) => ({ b: st.b + 1 }));
    expect(fn).toHaveBeenCalledTimes(1);
    expect(s.getState().b).toBe(3);
  });

  it('re-renders a selector only when the selected value changes', () => {
    const s = createStore({ a: 1, b: 1 });
    let renders = 0;
    const C = () => { renders += 1; const a = useStore(s, (x) => x.a); return React.createElement('span', null, a); };
    const { container } = render(React.createElement(C));
    expect(renders).toBe(1);
    act(() => s.setState({ b: 2 }));
    expect(renders).toBe(1);
    act(() => s.setState({ a: 5 }));
    expect(renders).toBe(2);
    expect(container.textContent).toBe('5');
  });

  it('honours a custom equality function', () => {
    const s = createStore({ list: [1, 2] });
    let renders = 0;
    const C = () => { renders += 1; useStore(s, (x) => ({ n: x.list.length }), shallowEqual); return null; };
    render(React.createElement(C));
    act(() => s.setState({ list: [3, 4] }));
    expect(renders).toBe(1);
  });
});

describe('keepIdentity', () => {
  it('returns prev for deep-equal input', () => {
    const prev = { a: [1, { x: 1 }], b: 'k' };
    expect(keepIdentity(prev, JSON.parse(JSON.stringify(prev)))).toBe(prev);
  });
  it('reuses unchanged children', () => {
    const prev = { keep: { n: 1 }, change: { n: 1 }, list: [{ id: 1 }, { id: 2 }] };
    const next = { keep: { n: 1 }, change: { n: 2 }, list: [{ id: 1 }, { id: 3 }] };
    const out = keepIdentity(prev, next);
    expect(out).not.toBe(prev);
    expect(out.keep).toBe(prev.keep);
    expect(out.change).toEqual({ n: 2 });
    expect(out.list[0]).toBe(prev.list[0]);
    expect(out.list[1]).toEqual({ id: 3 });
  });
  it('handles type changes and null', () => {
    expect(keepIdentity({ a: 1 } as unknown, [1] as unknown)).toEqual([1]);
    expect(keepIdentity(null as unknown, { a: 1 } as unknown)).toEqual({ a: 1 });
  });
});

describe('shallowEqual', () => {
  it('compares one level', () => {
    expect(shallowEqual({ a: 1 }, { a: 1 })).toBe(true);
    expect(shallowEqual({ a: 1 }, { a: 2 })).toBe(false);
    expect(shallowEqual({ a: {} }, { a: {} })).toBe(false);
    expect(shallowEqual(1, 1)).toBe(true);
  });
});
