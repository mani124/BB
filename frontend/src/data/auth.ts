import { apiFetch, bootstrapDashboardSession, getDashboardCapability } from '../api/client';
import { appStore } from './appStore';

export { getDashboardCapability };

/** Exchange the stored key for a session cookie. Opens the key dialog when the server says 401. Returns true when signed in. */
export async function ensureSession(): Promise<boolean> {
  const ok = await bootstrapDashboardSession();
  if (ok) {
    appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: false } }));
    return true;
  }
  const check = await apiFetch('/api/signals').catch(() => null);
  if (check && check.status === 401) {
    appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } }));
    return false;
  }
  return check !== null && check.ok;
}

/** Try a key typed into the dialog. */
export async function submitCapability(key: string): Promise<boolean> {
  const ok = await bootstrapDashboardSession(key);
  if (ok) appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: false } }));
  return ok;
}

export function openCapabilityDialog(): void {
  appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: true } }));
}

export function closeCapabilityDialog(): void {
  appStore.setState((s) => ({ ui: { ...s.ui, needsCapability: false } }));
}
