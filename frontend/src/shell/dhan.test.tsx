import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook } from '@testing-library/react';

const connect = vi.fn(async () => true);
vi.mock('../context/DhanAuthContext', async () => {
  const actual = await vi.importActual<typeof import('../context/DhanAuthContext')>('../context/DhanAuthContext');
  return { ...actual, useDhanAuth: () => ({ connect, isLoggedIn: false, tokenExpiry: null, clientId: '', disconnect: vi.fn(), tokenExpiryCountdown: '' }) };
});
import { useDhanAutoReconnect } from './useDhanAutoReconnect';
import { appStore, resetAppStore } from '../data/appStore';
import { Chrome } from './Chrome';
import { ThemeProvider } from '../context/ThemeContext';
import { ConfirmProvider } from '../features/confirm/ConfirmProvider';

const setMode = (active_mode: string) => appStore.setState((s) => ({ scanner: { ...s.scanner, active_mode } }));

beforeEach(() => { connect.mockClear(); localStorage.clear(); resetAppStore(); });

describe('Dhan auto reconnect (parity 15)', () => {
  it('reconnects once in demo mode with a real saved token', () => {
    localStorage.setItem('dhan_client_id', '1000'); localStorage.setItem('dhan_access_token', 'abc.def.ghi');
    setMode('demo');
    renderHook(() => useDhanAutoReconnect());
    expect(connect).toHaveBeenCalledWith('1000', 'abc.def.ghi');
    expect(connect).toHaveBeenCalledTimes(1);
  });
  it.each(['server_active', 'oauth_connected', 'abc***def'])('ignores the sentinel token %s', (token) => {
    localStorage.setItem('dhan_client_id', '1000'); localStorage.setItem('dhan_access_token', token);
    setMode('demo');
    renderHook(() => useDhanAutoReconnect());
    expect(connect).not.toHaveBeenCalled();
  });
  it('does nothing in live mode or without a saved token', () => {
    localStorage.setItem('dhan_client_id', '1000'); localStorage.setItem('dhan_access_token', 'abc.def.ghi');
    setMode('live');
    renderHook(() => useDhanAutoReconnect());
    localStorage.clear(); setMode('demo');
    renderHook(() => useDhanAutoReconnect());
    expect(connect).not.toHaveBeenCalled();
  });
  it('mirrors the session into the store', () => {
    renderHook(() => useDhanAutoReconnect());
    expect(appStore.getState().ui.dhan).toEqual({ loggedIn: false, expiry: null });
  });
});

describe('Dhan connect from the dock chrome (parity 12)', () => {
  it('opens the connect dialog and Escape closes it', () => {
    render(<ThemeProvider><ConfirmProvider><Chrome /></ConfirmProvider></ThemeProvider>);
    fireEvent.click(screen.getByRole('button', { name: /Connect Dhan/ }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
