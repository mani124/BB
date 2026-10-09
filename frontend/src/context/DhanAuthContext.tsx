import React, { createContext, useContext, useState, useEffect } from 'react';

export function formatTokenExpiryCountdown(expiryMs: number): string {
  const diff = expiryMs - Date.now();
  if (diff <= 0) return 'Expired';
  const totalMinutes = Math.ceil(diff / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
}

interface DhanAuthContextType {
  clientId: string | null;
  accessToken: string | null;
  isLoggedIn: boolean;
  tokenExpiry: number | null;
  tokenExpiryCountdown: string | null;
  connect: (id: string, token: string) => Promise<boolean>;
  loginWithOAuth: (appId: string, appSecret: string, clientId?: string) => Promise<void>;
  exchangeOAuthToken: (appId: string, appSecret: string, consentId: string) => Promise<boolean>;
  disconnect: () => void;
  clearError: () => void;
  error: string | null;
}

const DhanAuthContext = createContext<DhanAuthContextType | undefined>(undefined);

export const DhanAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [clientId, setClientId] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [tokenExpiry, setTokenExpiry] = useState<number | null>(null);
  const [tokenExpiryCountdown, setTokenExpiryCountdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Update countdown every 30 seconds if expiry is set
  useEffect(() => {
    if (!tokenExpiry) return;
    setTokenExpiryCountdown(formatTokenExpiryCountdown(tokenExpiry));
    const interval = setInterval(() => {
      setTokenExpiryCountdown(formatTokenExpiryCountdown(tokenExpiry));
    }, 30000);
    return () => clearInterval(interval);
  }, [tokenExpiry]);

  // On mount: check for OAuth redirect param (consentId) or restored session in sessionStorage
  useEffect(() => {
    // 1. Detect OAuth redirect (DhanHQ redirects with ?tokenId=... or ?consentId=...)
    const params = new URLSearchParams(window.location.search);
    const consentId = params.get('tokenId') || params.get('consentId') || params.get('token_id');
    if (consentId) {
      const appId = sessionStorage.getItem('dhan_oauth_app_id');
      const appSecret = sessionStorage.getItem('dhan_oauth_app_secret');
      if (appId && appSecret) {
        exchangeOAuthToken(appId, appSecret, consentId);
      }
      // Clean URL without reloading page
      window.history.replaceState({}, document.title, window.location.pathname);
      return;
    }

    // 2. Restore and verify from sessionStorage on reload/reopen
    const savedId = sessionStorage.getItem('dhan_client_id');
    const savedToken = sessionStorage.getItem('dhan_access_token');
    const savedExpiry = sessionStorage.getItem('dhan_token_expiry');

    if (savedExpiry) {
      const exp = Number(savedExpiry);
      if (!isNaN(exp) && exp > Date.now()) {
        setTokenExpiry(exp);
        setTokenExpiryCountdown(formatTokenExpiryCountdown(exp));
      }
    }

    fetch('/api/auth/status')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.authenticated) {
          const cid = data.client_id || savedId || 'Active';
          setClientId(cid);
          setAccessToken('server_active');
          setError(null);
          sessionStorage.setItem('dhan_client_id', cid);
          sessionStorage.setItem('dhan_access_token', 'server_active');
          return;
        }

        if (savedId && savedToken) {
          if (savedToken.includes('*') || savedToken === 'server_active') {
            setClientId(savedId);
            setAccessToken(savedToken);
          } else {
            connect(savedId, savedToken);
          }
        }
      })
      .catch(() => {
        if (savedId && savedToken) {
          if (savedToken.includes('*') || savedToken === 'server_active') {
            setClientId(savedId);
            setAccessToken(savedToken);
          } else {
            connect(savedId, savedToken);
          }
        }
      });
  }, []);

  const connect = async (id: string, token: string): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: {
          'X-Dhan-Client-Id': id.trim(),
          'X-Dhan-Access-Token': token.trim(),
        },
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || 'Authentication failed');
        return false;
      }

      const data = await res.json();
      if (!data.valid) {
        setError(data.error || 'Invalid credentials');
        return false;
      }

      // Store in sessionStorage for zero-token persistence guarantee
      const expiryMs = Date.now() + 24 * 3600 * 1000;
      sessionStorage.setItem('dhan_client_id', id.trim());
      sessionStorage.setItem('dhan_access_token', token.trim());
      sessionStorage.setItem('dhan_token_expiry', expiryMs.toString());

      setClientId(id.trim());
      setAccessToken(token.trim());
      setTokenExpiry(expiryMs);
      setTokenExpiryCountdown(formatTokenExpiryCountdown(expiryMs));
      return true;
    } catch (e: any) {
      setError(e.message || 'Connection error');
      return false;
    }
  };

  const loginWithOAuth = async (appId: string, appSecret: string, clientId?: string): Promise<void> => {
    setError(null);
    try {
      sessionStorage.setItem('dhan_oauth_app_id', appId.trim());
      sessionStorage.setItem('dhan_oauth_app_secret', appSecret.trim());
      if (clientId && clientId.trim()) {
        sessionStorage.setItem('dhan_client_id', clientId.trim());
      }
      const redirectUri = window.location.origin + window.location.pathname;
      let url = `/api/auth/oauth/login-url?app_id=${encodeURIComponent(appId.trim())}&app_secret=${encodeURIComponent(appSecret.trim())}&redirect_uri=${encodeURIComponent(redirectUri)}`;
      if (clientId && clientId.trim()) {
        url += `&client_id=${encodeURIComponent(clientId.trim())}`;
      }
      const res = await fetch(url);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to generate Dhan OAuth login URL');
      }
      const data = await res.json();
      if (data.login_url) {
        window.location.href = data.login_url;
      } else {
        throw new Error('No login URL returned from Dhan auth service');
      }
    } catch (err: any) {
      setError(err.message || 'OAuth initiation failed');
      throw err;
    }
  };

  const exchangeOAuthToken = async (appId: string, appSecret: string, consentId: string): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch('/api/auth/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          app_id: appId.trim(),
          app_secret: appSecret.trim(),
          consent_id: consentId.trim(),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || 'OAuth token exchange failed');
        return false;
      }

      const data = await res.json();
      const cId = data.client_id;
      if (!cId) {
        setError('No client ID received from OAuth token exchange');
        return false;
      }

      const hours = Number(data.expires_in_hours) || 24;
      const expiryMs = Date.now() + hours * 3600 * 1000;
      const maskedToken = data.masked_token || 'oauth_connected';

      sessionStorage.setItem('dhan_client_id', cId);
      sessionStorage.setItem('dhan_access_token', maskedToken);
      sessionStorage.setItem('dhan_token_expiry', expiryMs.toString());

      setClientId(cId);
      setAccessToken(maskedToken);
      setTokenExpiry(expiryMs);
      setTokenExpiryCountdown(formatTokenExpiryCountdown(expiryMs));
      return true;
    } catch (err: any) {
      setError(err.message || 'OAuth token exchange network error');
      return false;
    } finally {
      sessionStorage.removeItem('dhan_oauth_app_secret');
    }
  };

  const disconnect = () => {
    sessionStorage.removeItem('dhan_client_id');
    sessionStorage.removeItem('dhan_access_token');
    sessionStorage.removeItem('dhan_token_expiry');
    sessionStorage.removeItem('dhan_oauth_app_secret');
    localStorage.removeItem('dhan_client_id');
    localStorage.removeItem('dhan_access_token');
    setClientId(null);
    setAccessToken(null);
    setTokenExpiry(null);
    setTokenExpiryCountdown(null);
    fetch('/api/auth/disconnect', { method: 'POST' }).catch(() => {});
  };

  return (
    <DhanAuthContext.Provider
      value={{
        clientId,
        accessToken,
        isLoggedIn: !!clientId && !!accessToken,
        tokenExpiry,
        tokenExpiryCountdown,
        connect,
        loginWithOAuth,
        exchangeOAuthToken,
        disconnect,
        clearError: () => setError(null),
        error,
      }}
    >
      {children}
    </DhanAuthContext.Provider>
  );
};

export const useDhanAuth = () => {
  const context = useContext(DhanAuthContext);
  if (!context) {
    throw new Error('useDhanAuth must be used within a DhanAuthProvider');
  }
  return context;
};
