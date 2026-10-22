import { useRef, useSyncExternalStore } from 'react';

export interface Store<T> {
  getState(): T;
  setState(patch: Partial<T> | ((s: T) => Partial<T>)): void;
  subscribe(fn: () => void): () => void;
}

export function createStore<T extends object>(initial: T): Store<T> {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    getState: () => state,
    setState(patch) {
      const part = typeof patch === 'function' ? patch(state) : patch;
      state = { ...state, ...part };
      listeners.forEach((l) => l());
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => { listeners.delete(fn); };
    },
  };
}

export function shallowEqual<T>(a: T, b: T): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  const ka = Object.keys(a as object);
  const kb = Object.keys(b as object);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && Object.is((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
}

/** Returns `prev` when deep-equal to `next`; otherwise `next` with unchanged sub-trees replaced by their previous references. */
export function keepIdentity<T>(prev: T, next: T): T {
  if (Object.is(prev, next)) return prev;
  if (typeof prev !== 'object' || typeof next !== 'object' || prev === null || next === null) return next;
  if (Array.isArray(prev) !== Array.isArray(next)) return next;
  if (Array.isArray(prev) && Array.isArray(next)) {
    const merged = next.map((item, i) => (i < prev.length ? keepIdentity(prev[i], item) : item));
    if (merged.length === prev.length && merged.every((m, i) => m === prev[i])) return prev;
    return merged as unknown as T;
  }
  const p = prev as Record<string, unknown>;
  const n = next as Record<string, unknown>;
  const keys = Object.keys(n);
  const out: Record<string, unknown> = {};
  let same = keys.length === Object.keys(p).length;
  for (const k of keys) {
    out[k] = k in p ? keepIdentity(p[k], n[k]) : n[k];
    if (out[k] !== p[k]) same = false;
  }
  return (same ? prev : out) as T;
}

export function useStore<T, S>(store: Store<T>, selector: (s: T) => S, isEqual: (a: S, b: S) => boolean = Object.is): S {
  const last = useRef<{ value: S } | null>(null);
  const getSnapshot = () => {
    const next = selector(store.getState());
    if (last.current && isEqual(last.current.value, next)) return last.current.value;
    last.current = { value: next };
    return next;
  };
  return useSyncExternalStore(store.subscribe, getSnapshot, getSnapshot);
}
