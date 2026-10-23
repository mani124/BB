import { useEffect, useRef } from 'react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { appStore, useApp } from '../data/appStore';

/** Demo mode with a real saved token: reconnect once, as the legacy shell does (sentinel tokens are ignored). */
export function useDhanAutoReconnect(): void {
  const { connect, isLoggedIn, tokenExpiry } = useDhanAuth();
  useEffect(() => { appStore.setState((st) => ({ ui: { ...st.ui, dhan: { loggedIn: isLoggedIn, expiry: tokenExpiry } } })); }, [isLoggedIn, tokenExpiry]);
  const activeMode = useApp((s) => s.scanner.active_mode);
  const busy = useRef(false);
  useEffect(() => {
    if (activeMode !== 'demo' || busy.current) return;
    let savedId: string | null = null;
    let savedToken: string | null = null;
    try { savedId = localStorage.getItem('dhan_client_id'); savedToken = localStorage.getItem('dhan_access_token'); } catch { return; }
    if (savedId && savedToken && !savedToken.includes('*') && savedToken !== 'server_active' && savedToken !== 'oauth_connected') {
      busy.current = true;
      void connect(savedId, savedToken).finally(() => { setTimeout(() => { busy.current = false; }, 15000); });
    }
  }, [activeMode, connect]);
}
