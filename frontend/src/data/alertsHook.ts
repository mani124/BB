import type { Alert } from './types';

export type AlertInput = Omit<Alert, 'id' | 'ts' | 'acked'>;

let sink: (a: AlertInput) => void = () => {};

/** Actions report their outcome here. The alerts engine installs the real sink (Task 5.9). */
export const alertsHook = {
  push(a: AlertInput): void { sink(a); },
  setSink(fn: (a: AlertInput) => void): () => void {
    sink = fn;
    return () => { sink = () => {}; };
  },
};
