export const CAPABILITY_STORAGE_KEY = 'dashboard_capability';
export const DEFAULT_CAPABILITY = 'bb-options-local-capability';

export function getDashboardCapability(): string {
  return localStorage.getItem(CAPABILITY_STORAGE_KEY) || DEFAULT_CAPABILITY;
}

export function setDashboardCapability(token: string): void {
  localStorage.setItem(CAPABILITY_STORAGE_KEY, token);
}

export async function bootstrapDashboardSession(customToken?: string): Promise<boolean> {
  const secret = (customToken !== undefined ? customToken : getDashboardCapability()).trim();
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
