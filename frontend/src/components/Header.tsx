import React, { useState } from 'react';
import { ShieldCheck, Key, RefreshCw, LogOut, Sun, Moon, KeyRound } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { useTheme } from '../context/ThemeContext';
import { RiskControls } from './RiskControls';
import { Tabs } from './Tabs';
import { Dialog } from './Dialog';
import { ConnectionStatus } from './ConnectionStatus';
import { connectionState } from '../lib/connectionState';
import type { AppTab, RiskStatus } from '../types';

export interface HeaderProps {
  activeMode: 'live' | 'demo' | 'stale' | 'error' | string;
  scanCycleCount: number;
  lastScanTime: string;
  isScanning: boolean;
  scanProgress: number;
  onScanNow: () => void;
  feedStatus?: 'WS_LIVE' | 'LIVE' | 'STALE' | 'ERROR' | 'DEMO' | 'HTTP_POLLING' | string;
  wsConnected?: boolean;
  tokenExpiryCountdown?: string;
  activeTab?: AppTab;
  onTabChange?: (tab: AppTab) => void;
  openPositionsCount?: number;
  onOpenAccessKey?: () => void;
  risk?: RiskStatus | null;
  onKillSwitch?: (engage: boolean) => void;
  /** Browser-to-server stream health, separate from the exchange feed pill. */
  stream?: StreamStatus;
}

export type StreamStatus = { state: 'connecting' | 'live' | 'reconnecting' | 'stale'; ageSec: number };

export const Header: React.FC<HeaderProps> = ({
  activeMode,
  scanCycleCount,
  lastScanTime,
  isScanning,
  scanProgress,
  onScanNow,
  feedStatus,
  wsConnected,
  tokenExpiryCountdown: propCountdown,
  activeTab,
  onTabChange,
  openPositionsCount = 0,
  onOpenAccessKey,
  risk,
  onKillSwitch,
  stream,
}) => {
  const {
    isLoggedIn,
    clientId,
    connect,
    loginWithOAuth,
    disconnect,
    clearError,
    error,
    tokenExpiryCountdown: contextCountdown,
  } = useDhanAuth();
  const { theme, toggleTheme } = useTheme();

  const [modalOpen, setModalOpen] = useState(false);
  const [authTab, setAuthTab] = useState<'oauth' | 'manual'>('oauth');
  const [inputClientId, setInputClientId] = useState('');
  const [inputToken, setInputToken] = useState('');
  const [oauthClientId, setOauthClientId] = useState(
    typeof window !== 'undefined' ? localStorage.getItem('dhan_client_id') || '' : ''
  );
  const [oauthAppId, setOauthAppId] = useState(
    typeof window !== 'undefined' ? localStorage.getItem('dhan_oauth_app_id') || '' : ''
  );
  const [oauthAppSecret, setOauthAppSecret] = useState(
    typeof window !== 'undefined' ? sessionStorage.getItem('dhan_oauth_app_secret') || '' : ''
  );
  const [loading, setLoading] = useState(false);

  const countdown = propCountdown || contextCountdown;
  const showAuthenticated = (isLoggedIn || Boolean(propCountdown)) && activeMode !== 'demo';
  const isWsLive = feedStatus === 'WS_LIVE' || wsConnected === true;

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const success = await connect(inputClientId, inputToken);
    setLoading(false);
    if (success) {
      setModalOpen(false);
      setInputClientId('');
      setInputToken('');
    }
  };

  const handleOAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await loginWithOAuth(oauthAppId, oauthAppSecret, oauthClientId);
    } catch {
      setLoading(false);
    }
  };

  const inputCls = 'desk-input';
  const labelCls = 'block text-xs font-semibold mb-1 desk-muted';

  return (
    <>
      <header
        className="shrink-0 z-40 px-4 sm:px-6 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-2"
        style={{ background: 'var(--bg)', borderBottom: '1px solid var(--line)' }}
      >
        <h1 className="font-semibold text-base tracking-tight m-0 lg:hidden">BB Options</h1>

        {onTabChange && (
          <Tabs<AppTab>
            idPrefix="main"
            label="Sections"
            className="flex items-center gap-1 order-3 w-full justify-between sm:order-none sm:w-auto sm:justify-start"
            tabClassName="desk-tab"
            value={activeTab ?? 'watch'}
            onChange={onTabChange}
            items={[
              { id: 'watch', label: 'Watch' },
              { id: 'trades', label: 'Trades' },
              { id: 'session', label: 'Session' },
              { id: 'control', label: 'Control' },
            ]}
          />
        )}

        <div className="ml-auto hidden sm:flex flex-wrap items-center gap-x-3 gap-y-2 text-xs desk-muted">
          <RiskControls risk={risk ?? undefined} onKillSwitch={onKillSwitch} />
          <ConnectionStatus activeMode={activeMode} feedStatus={feedStatus} wsConnected={isWsLive} stream={stream} />

          <span className="desk-num hidden 2xl:inline" title="Scan cycle and last scan time">
            Cycle {scanCycleCount} · {lastScanTime || 'Ready'}
          </span>

          <button
            type="button"
            onClick={onScanNow}
            disabled={isScanning}
            className="desk-btn"
            title="Scan Now"
            aria-label="Scan now"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isScanning ? 'animate-spin' : ''}`} />
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            className="desk-btn"
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            aria-label="Toggle theme"
          >
            {theme === 'light' ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
          </button>

          {onOpenAccessKey && (
            <button
              type="button"
              onClick={onOpenAccessKey}
              className="desk-btn"
              title="Enter dashboard key"
              aria-label="Dashboard key"
            >
              <KeyRound className="h-3.5 w-3.5" />
            </button>
          )}

          {showAuthenticated ? (
            <div className="flex items-center gap-2 desk-pill up" style={{ padding: '4px 10px' }}>
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>Dhan Active: {clientId || 'Connected'}</span>
              <span className="desk-num" title={`Remaining session hours: ${countdown || '24h 00m'}`}>
                Token: {countdown || '24h 00m'}
              </span>
              <button type="button" onClick={disconnect} title="Disconnect Token" aria-label="Disconnect">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <button type="button" onClick={() => setModalOpen(true)} className="desk-btn accent">
              <Key className="h-3.5 w-3.5" />
              Connect Dhan
            </button>
          )}
        </div>
        <div className="sm:hidden ml-auto flex items-center gap-2">
          <button type="button" onClick={toggleTheme} className="desk-btn" aria-label="Toggle theme">
            {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </button>
          <details className="relative desk-tools-menu">
            <summary className="desk-btn">Tools</summary>
            <div className="absolute right-0 top-11 z-50 w-72 max-w-[calc(100vw-2rem)] desk-panel p-3 shadow-lg flex flex-col items-start gap-3">
              <p className="desk-label">Risk and connection</p>
              <RiskControls risk={risk ?? undefined} onKillSwitch={onKillSwitch} />
              <ConnectionStatus activeMode={activeMode} feedStatus={feedStatus} wsConnected={isWsLive} stream={stream} />
              <button type="button" className="desk-btn" onClick={onScanNow} disabled={isScanning}>Scan now</button>
              {onOpenAccessKey && <button type="button" className="desk-btn" onClick={onOpenAccessKey}>Dashboard key</button>}
              {showAuthenticated ? <button type="button" className="desk-btn" onClick={disconnect}>Disconnect Dhan</button>
                : <button type="button" className="desk-btn accent" onClick={() => setModalOpen(true)}>Connect Dhan</button>}
            </div>
          </details>
        </div>
      </header>

      {/* Connect Modal */}
      {modalOpen && (
        <Dialog label="Connect Dhan" onClose={() => setModalOpen(false)} className="p-5" closeOnBackdrop={false}>
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="desk-pill" style={{ padding: 8, borderRadius: 8 }}>
                <Key className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold">Connect Dhan Live Trading</h3>
                <p className="text-xs desk-muted">Zero-Persistence: Stored only in browser session memory</p>
              </div>
            </div>

            <div className="flex mb-4" role="group" aria-label="Login method" style={{ borderBottom: '1px solid var(--line)' }}>
              <button
                type="button"
                aria-pressed={authTab === 'oauth'}
                onClick={() => { setAuthTab('oauth'); clearError(); }}
                className="flex-1 py-2 text-xs font-semibold"
                style={{ borderBottom: `2px solid ${authTab === 'oauth' ? 'var(--accent)' : 'transparent'}`, color: authTab === 'oauth' ? 'var(--accent)' : 'var(--muted)' }}
              >
                1-Click Dhan OAuth
              </button>
              <button
                type="button"
                aria-pressed={authTab === 'manual'}
                onClick={() => { setAuthTab('manual'); clearError(); }}
                className="flex-1 py-2 text-xs font-semibold"
                style={{ borderBottom: `2px solid ${authTab === 'manual' ? 'var(--accent)' : 'transparent'}`, color: authTab === 'manual' ? 'var(--accent)' : 'var(--muted)' }}
              >
                Manual 24h JWT
              </button>
            </div>

            {error && <div className="desk-alert mb-4">{error}</div>}

            {authTab === 'oauth' ? (
              <form onSubmit={handleOAuthSubmit} className="space-y-4">
                <div>
                  <label htmlFor="dhan-f1" className={labelCls}>Dhan Client ID</label>
                  <input id="dhan-f1" type="text" required placeholder="Your 10-digit Dhan ID (e.g. 1000000001)" value={oauthClientId} onChange={(e) => setOauthClientId(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label htmlFor="dhan-f2" className={labelCls}>Dhan App ID / API Key</label>
                  <input id="dhan-f2" type="text" required placeholder="API Key generated in Dhan Developer Portal" value={oauthAppId} onChange={(e) => setOauthAppId(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label htmlFor="dhan-f3" className={labelCls}>Dhan App Secret</label>
                  <input id="dhan-f3" type="password" required placeholder="API Secret generated in Dhan Developer Portal" value={oauthAppSecret} onChange={(e) => setOauthAppSecret(e.target.value)} className={inputCls} />
                </div>
                <div className="p-3 rounded-md text-xs space-y-1 desk-muted" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
                  <p className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
                    <ShieldCheck className="h-3.5 w-3.5" /> 1-Click Official Dhan Login
                  </p>
                  <p>Redirects securely to Dhan login portal. Your credentials and generated token remain strictly in session memory.</p>
                </div>
                <div className="flex items-center justify-end gap-3 pt-2">
                  <button type="button" onClick={() => setModalOpen(false)} className="desk-btn">Cancel</button>
                  <button type="submit" disabled={loading} className="desk-btn solid">
                    {loading ? 'Redirecting...' : 'Connect with Dhan'}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleManualSubmit} className="space-y-4">
                <div>
                  <label htmlFor="dhan-f4" className={labelCls}>Dhan Client ID</label>
                  <input id="dhan-f4" type="text" required placeholder="e.g. 1000000001" value={inputClientId} onChange={(e) => setInputClientId(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label htmlFor="dhan-f5" className={labelCls}>24-Hour Access Token (JWT)</label>
                  <textarea id="dhan-f5" required rows={3} placeholder="Paste your 24h JWT token from Dhan Web Settings" value={inputToken} onChange={(e) => setInputToken(e.target.value)} className={`${inputCls} font-mono text-xs`} />
                </div>
                <div className="p-3 rounded-md text-xs space-y-1 desk-muted" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
                  <p className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
                    <ShieldCheck className="h-3.5 w-3.5" /> Zero Token Persistence Guarantee
                  </p>
                  <p>Tokens remain strictly in your browser session memory and are passed via secure HTTP headers. Automatically cleared upon tab close.</p>
                </div>
                <div className="flex items-center justify-end gap-3 pt-2">
                  <button type="button" onClick={() => setModalOpen(false)} className="desk-btn">Cancel</button>
                  <button type="submit" disabled={loading} className="desk-btn solid">
                    {loading ? 'Verifying...' : 'Connect Session'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </Dialog>
      )}
    </>
  );
};
