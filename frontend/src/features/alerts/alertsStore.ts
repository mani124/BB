import { alertsHook, type AlertInput } from '../../data/alertsHook';
import { appStore, useApp } from '../../data/appStore';
import type { Alert } from '../../data/types';

export const MAX_ALERTS = 200;
export const DEDUPE_MS = 30_000;
const STORAGE_KEY = 'bb_alerts';

let seq = 0;

function persist(alerts: Alert[]): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts)); } catch { /* storage unavailable: alerts stay in memory */ }
}

/** Alerts saved by an earlier page load (with their acknowledged flags). */
export function loadAlerts(): Alert[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as unknown;
    if (!Array.isArray(raw)) return [];
    return raw.filter((a): a is Alert => Boolean(a) && typeof a.id === 'string' && typeof a.message === 'string' && typeof a.ts === 'number').slice(0, MAX_ALERTS);
  } catch {
    return [];
  }
}

export function restoreAlerts(): void {
  const saved = loadAlerts();
  if (saved.length) appStore.setState({ alerts: saved });
}

/** Adds an alert unless an identical unacknowledged one was raised in the last 30 s. Newest first, capped at 200. */
export function pushAlert(input: AlertInput, now: number = Date.now()): Alert | null {
  const cur = appStore.getState().alerts;
  if (cur.some((a) => !a.acked && a.source === input.source && a.message === input.message && now - a.ts < DEDUPE_MS)) return null;
  const alert: Alert = { id: `a${now.toString(36)}-${++seq}`, ts: now, acked: false, ...input };
  const next = [alert, ...cur].slice(0, MAX_ALERTS);
  appStore.setState({ alerts: next });
  persist(next);
  return alert;
}

export function ackAlert(id: string): void {
  const next = appStore.getState().alerts.map((a) => (a.id === id ? { ...a, acked: true } : a));
  appStore.setState({ alerts: next });
  persist(next);
}

export function ackAll(): void {
  const next = appStore.getState().alerts.map((a) => (a.acked ? a : { ...a, acked: true }));
  appStore.setState({ alerts: next });
  persist(next);
}

export function clearAcked(): void {
  const next = appStore.getState().alerts.filter((a) => !a.acked);
  appStore.setState({ alerts: next });
  persist(next);
}

export const useAlerts = (): Alert[] => useApp((s) => s.alerts);
export const useUnackedCritical = (): number => useApp((s) => s.alerts.filter((a) => !a.acked && a.severity === 'critical').length);

/** Installs the sink that actions use, so every action outcome and every rule lands in one list. */
export function installAlertSink(): () => void {
  return alertsHook.setSink((a) => { pushAlert(a); });
}
