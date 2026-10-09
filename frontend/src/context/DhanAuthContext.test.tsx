import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import { DhanAuthProvider, useDhanAuth, formatTokenExpiryCountdown } from './DhanAuthContext';

describe('formatTokenExpiryCountdown', () => {
  it('formats remaining hours and minutes correctly', () => {
    const futureMs = Date.now() + 23 * 3600 * 1000 + 45 * 60 * 1000;
    const result = formatTokenExpiryCountdown(futureMs);
    expect(result).toBe('23h 45m');
  });

  it('returns Expired for past timestamps', () => {
    const pastMs = Date.now() - 1000;
    const result = formatTokenExpiryCountdown(pastMs);
    expect(result).toBe('Expired');
  });
});

describe('DhanAuthContext OAuth and Zero-Persistence Flow', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loginWithOAuth stores credentials in sessionStorage and navigates to login_url', async () => {
    const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <DhanAuthProvider>{children}</DhanAuthProvider>
    );

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ login_url: 'https://auth.dhan.co/login?client_id=test_app' }),
    });
    global.fetch = mockFetch;

    delete (window as any).location;
    (window as any).location = { href: '', origin: 'http://localhost', pathname: '/' };

    const { result } = renderHook(() => useDhanAuth(), { wrapper });

    await act(async () => {
      await result.current.loginWithOAuth('test_app_id', 'test_app_secret');
    });

    expect(sessionStorage.getItem('dhan_oauth_app_id')).toBe('test_app_id');
    expect(sessionStorage.getItem('dhan_oauth_app_secret')).toBe('test_app_secret');
    expect(window.location.href).toBe('https://auth.dhan.co/login?client_id=test_app');
  });

  it('exchanges consentId automatically when returning from redirect and clears URL', async () => {
    sessionStorage.setItem('dhan_oauth_app_id', 'my_app_123');
    sessionStorage.setItem('dhan_oauth_app_secret', 'sec_456');

    // Simulate returning to dashboard with ?consentId=consent_abc
    delete (window as any).location;
    (window as any).location = {
      search: '?consentId=consent_abc',
      pathname: '/',
      origin: 'http://localhost',
    };

    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'connected',
        client_id: '1000000001',
        masked_token: 'dhan_***',
        expires_in_hours: 24,
      }),
    });
    global.fetch = mockFetch;

    const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <DhanAuthProvider>{children}</DhanAuthProvider>
    );

    const { result } = renderHook(() => useDhanAuth(), { wrapper });

    // Wait for async effect to resolve
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/auth/oauth/token',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          app_id: 'my_app_123',
          app_secret: 'sec_456',
          consent_id: 'consent_abc',
        }),
      })
    );

    expect(result.current.clientId).toBe('1000000001');
    expect(result.current.isLoggedIn).toBe(true);
    expect(sessionStorage.getItem('dhan_client_id')).toBe('1000000001');
    expect(sessionStorage.getItem('dhan_access_token')).toBe('dhan_***');
    expect(sessionStorage.getItem('dhan_token_expiry')).toBeTruthy();
    expect(replaceStateSpy).toHaveBeenCalledWith({}, document.title, '/');
  });

  it('disconnects and wipes tokens strictly from sessionStorage', () => {
    sessionStorage.setItem('dhan_client_id', '1000000001');
    sessionStorage.setItem('dhan_access_token', 'test_tok');
    sessionStorage.setItem('dhan_token_expiry', '123456');

    const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
      <DhanAuthProvider>{children}</DhanAuthProvider>
    );

    const { result } = renderHook(() => useDhanAuth(), { wrapper });

    act(() => {
      result.current.disconnect();
    });

    expect(result.current.isLoggedIn).toBe(false);
    expect(result.current.clientId).toBeNull();
    expect(sessionStorage.getItem('dhan_client_id')).toBeNull();
    expect(sessionStorage.getItem('dhan_access_token')).toBeNull();
    expect(sessionStorage.getItem('dhan_token_expiry')).toBeNull();
  });
});
