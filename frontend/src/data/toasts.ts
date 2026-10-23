import { createStore, useStore } from './store';

export interface Toast { id: number; ok: boolean; message: string }

const store = createStore<{ toasts: Toast[] }>({ toasts: [] });
let nextId = 1;
const TTL_MS = 8000;

export function pushToast(ok: boolean, message: string): void {
  const id = nextId++;
  store.setState((s) => ({ toasts: [...s.toasts.slice(-4), { id, ok, message }] }));
  setTimeout(() => dismissToast(id), TTL_MS);
}

export function dismissToast(id: number): void {
  store.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
}

export function clearToasts(): void { store.setState({ toasts: [] }); }

export const useToasts = (): Toast[] => useStore(store, (s) => s.toasts);
