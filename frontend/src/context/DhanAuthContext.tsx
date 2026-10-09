import React, { createContext, useContext, useState, useEffect } from 'react';

interface DhanAuthContextType {
  clientId: string | null;
  accessToken: string | null;
  isLoggedIn: boolean;
  connect: (id: string, token: string) => Promise<boolean>;
  disconnect: () => void;
  error: string | null;
}

const DhanAuthContext = createContext<DhanAuthContextType | undefined>(undefined);

export const DhanAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [clientId, setClientId] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Restore and verify from localStorage on reload/reopen
    const savedId = localStorage.getItem('dhan_client_id');
    const savedToken = localStorage.getItem('dhan_access_token');
    if (savedId && savedToken) {
      connect(savedId, savedToken);
    }
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

      // Store in localStorage for continuous intraday session
      localStorage.setItem('dhan_client_id', id.trim());
      localStorage.setItem('dhan_access_token', token.trim());
      setClientId(id.trim());
      setAccessToken(token.trim());
      return true;
    } catch (e: any) {
      setError(e.message || 'Connection error');
      return false;
    }
  };

  const disconnect = () => {
    localStorage.removeItem('dhan_client_id');
    localStorage.removeItem('dhan_access_token');
    setClientId(null);
    setAccessToken(null);
    fetch('/api/auth/disconnect', { method: 'POST' }).catch(() => {});
  };

  return (
    <DhanAuthContext.Provider
      value={{
        clientId,
        accessToken,
        isLoggedIn: !!clientId && !!accessToken,
        connect,
        disconnect,
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
