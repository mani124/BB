import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getDashboardCapability,
  setDashboardCapability,
  bootstrapDashboardSession,
  apiFetch,
  CAPABILITY_STORAGE_KEY,
} from './client';

describe('client api and capability helper', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('moves a key an older version kept in sessionStorage to localStorage', () => {
    sessionStorage.setItem(CAPABILITY_STORAGE_KEY, 'tab-secret');
    expect(getDashboardCapability()).toBe('tab-secret');
    expect(localStorage.getItem(CAPABILITY_STORAGE_KEY)).toBe('tab-secret');
    expect(sessionStorage.getItem(CAPABILITY_STORAGE_KEY)).toBeNull();
  });

  it('has no built-in key when none is stored', () => {
    expect(getDashboardCapability()).toBe('');
  });

  it('ignores the old public default key left in storage', () => {
    localStorage.setItem(CAPABILITY_STORAGE_KEY, 'bb-options-local-capability');
    expect(getDashboardCapability()).toBe('');
  });

  it('bootstrapDashboardSession does not call the server without a key', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    expect(await bootstrapDashboardSession()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('stores and retrieves custom capability token', () => {
    setDashboardCapability('custom-secret-123');
    expect(getDashboardCapability()).toBe('custom-secret-123');
    expect(localStorage.getItem(CAPABILITY_STORAGE_KEY)).toBe('custom-secret-123');
    expect(sessionStorage.getItem(CAPABILITY_STORAGE_KEY)).toBeNull();
  });

  it('bootstrapDashboardSession calls /api/auth/session and saves secret on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'authenticated' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await bootstrapDashboardSession('my-test-token');
    expect(result).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ secret: 'my-test-token' }),
    });
    expect(getDashboardCapability()).toBe('my-test-token');
  });

  it('bootstrapDashboardSession returns false on HTTP error', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid secret' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await bootstrapDashboardSession('wrong-token');
    expect(result).toBe(false);
  });

  it('apiFetch automatically injects X-Dashboard-Capability header and same-origin credentials', async () => {
    setDashboardCapability('active-token-456');
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('/api/signals/scan-now', { method: 'POST' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/signals/scan-now');
    expect(init.credentials).toBe('same-origin');
    expect((init.headers as Headers).get('X-Dashboard-Capability')).toBe('active-token-456');
  });
});
