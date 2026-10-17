export const CAPABILITY_STORAGE_KEY = 'dashboard_capability';
// The old public default key; it is never sent and is dropped if found in storage.
const LEGACY_PUBLIC_KEY = 'bb-options-local-capability';

// The key lives in sessionStorage (this tab only, gone when it closes). The HttpOnly session cookie is what keeps
// a returning visitor signed in; an older copy left in localStorage is removed.
export function getDashboardCapability(): string {
  try { localStorage.removeItem(CAPABILITY_STORAGE_KEY); } catch { /* storage unavailable */ }
  const stored = sessionStorage.getItem(CAPABILITY_STORAGE_KEY) || '';
  return stored === LEGACY_PUBLIC_KEY ? '' : stored;
}

export function setDashboardCapability(token: string): void {
  sessionStorage.setItem(CAPABILITY_STORAGE_KEY, token);
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
