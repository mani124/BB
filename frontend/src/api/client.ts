export const CAPABILITY_STORAGE_KEY = 'dashboard_capability';
// The old public default key; it is never sent and is dropped if found in storage.
const LEGACY_PUBLIC_KEY = 'bb-options-local-capability';

// The key is remembered on this device (localStorage) so every tab and every later visit stays signed in. A copy a
// previous version kept in sessionStorage is moved over. Clear it with forgetDashboardCapability().
export function getDashboardCapability(): string {
  try {
    let stored = localStorage.getItem(CAPABILITY_STORAGE_KEY) || '';
    if (!stored) {
      stored = sessionStorage.getItem(CAPABILITY_STORAGE_KEY) || '';
      if (stored && stored !== LEGACY_PUBLIC_KEY) localStorage.setItem(CAPABILITY_STORAGE_KEY, stored);
    }
    try { sessionStorage.removeItem(CAPABILITY_STORAGE_KEY); } catch { /* storage unavailable */ }
    if (stored === LEGACY_PUBLIC_KEY) {
      localStorage.removeItem(CAPABILITY_STORAGE_KEY);
      return '';
    }
    return stored;
  } catch {
    return '';
  }
}

export function setDashboardCapability(token: string): void {
  try { localStorage.setItem(CAPABILITY_STORAGE_KEY, token); } catch { /* storage unavailable */ }
}

export function forgetDashboardCapability(): void {
  try { localStorage.removeItem(CAPABILITY_STORAGE_KEY); sessionStorage.removeItem(CAPABILITY_STORAGE_KEY); } catch { /* storage unavailable */ }
}

export async function bootstrapDashboardSession(customToken?: string): Promise<boolean> {
  const secret = (customToken !== undefined ? customToken : getDashboardCapability()).trim();
  if (!secret) return false; // no key yet: the sign-in dialog asks for it
  try {
    const res = await fetch('/api/auth/session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ secret }),
    });
    if (res.ok) {
      setDashboardCapability(secret);
      return true;
    }
  } catch (err) {
    console.error('Failed to bootstrap dashboard session:', err);
  }
  return false;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const cap = getDashboardCapability();
  if (cap && !headers.has('X-Dashboard-Capability')) {
    headers.set('X-Dashboard-Capability', cap);
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: init.credentials || 'same-origin',
  });

  return response;
}
