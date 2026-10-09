import React, { useState } from 'react';
import { Activity, ShieldCheck, Key, RefreshCw, LogOut, Radio, Zap, Sun, Moon } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { useTheme } from '../context/ThemeContext';

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
}

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
}) => {
  const {
    isLoggedIn,
    clientId,
    connect,
    loginWithOAuth,
    disconnect,
    error,
    tokenExpiryCountdown: contextCountdown,
  } = useDhanAuth();
  const { theme, toggleTheme } = useTheme();

  const [modalOpen, setModalOpen] = useState(false);
  const [authTab, setAuthTab] = useState<'oauth' | 'manual'>('oauth');
  const [inputClientId, setInputClientId] = useState('');
  const [inputToken, setInputToken] = useState('');
  const [oauthClientId, setOauthClientId] = useState(
    typeof window !== 'undefined' ? sessionStorage.getItem('dhan_client_id') || '' : ''
  );
  const [oauthAppId, setOauthAppId] = useState(
    typeof window !== 'undefined' ? sessionStorage.getItem('dhan_oauth_app_id') || '' : ''
  );
  const [oauthAppSecret, setOauthAppSecret] = useState(
    typeof window !== 'undefined' ? sessionStorage.getItem('dhan_oauth_app_secret') || '' : ''
  );
  const [loading, setLoading] = useState(false);

  const countdown = propCountdown || contextCountdown;
  const showAuthenticated = isLoggedIn || Boolean(propCountdown);
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

  return (
    <>
      <header className="border-b border-slate-200 dark:border-dark-700 bg-white/90 dark:bg-dark-800/80 backdrop-blur sticky top-0 z-40 px-6 py-3.5 flex flex-wrap items-center justify-between gap-4 shadow-sm dark:shadow-none transition-colors">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight text-slate-900 dark:bg-gradient-to-r dark:from-white dark:via-slate-200 dark:to-cyan-400 dark:bg-clip-text dark:text-transparent">
                BB Options Trading PRO
              </span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-100 dark:bg-cyan-950/70 border border-cyan-300 dark:border-cyan-800 text-cyan-800 dark:text-cyan-400">
                NSE Derivatives
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              High-Velocity Bollinger Band Setups (Setups 1, 3, 2, 4) • Zero-Token Persistence
            </p>
          </div>
        </div>

        {/* Center Heartbeat & Progress */}
        <div className="flex items-center gap-3 bg-slate-100 dark:bg-dark-900/80 border border-slate-200 dark:border-dark-700 rounded-xl px-4 py-2">
          <div className="flex items-center gap-2">
            <Radio className={`h-4 w-4 ${isScanning ? 'text-cyan-600 dark:text-cyan-400 animate-pulse' : 'text-slate-500'}`} />
            <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              Cycle #{scanCycleCount}
            </span>
          </div>

          <div className="h-3 w-[1px] bg-slate-300 dark:bg-dark-600" />

          <span className="text-xs text-slate-600 dark:text-slate-400">
            Last: <strong className="text-slate-800 dark:text-slate-200 font-mono">{lastScanTime || 'Ready'}</strong>
          </span>

          <div className="h-3 w-[1px] bg-slate-300 dark:bg-dark-600" />

          {/* Mode & WebSocket Live Pill Badge */}
          {isWsLive ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/80 border border-emerald-400 dark:border-emerald-600 text-emerald-800 dark:text-emerald-300 shadow-sm shadow-emerald-500/20">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse ring-2 ring-emerald-400/50" />
              ⚡ WS LIVE (Sub-second)
            </span>
          ) : activeMode === 'live' || feedStatus === 'HTTP_POLLING' || feedStatus === 'LIVE' ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/80 border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-400">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              HTTP Polling
            </span>
          ) : activeMode === 'stale' ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-orange-100 dark:bg-orange-950/80 border border-orange-300 dark:border-orange-700 text-orange-800 dark:text-orange-400">
              <Radio className="h-3 w-3 text-orange-500" />
              Feed Stale (&gt;30s)
            </span>
          ) : activeMode === 'error' ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/80 border border-rose-300 dark:border-rose-700 text-rose-800 dark:text-rose-400">
              <Radio className="h-3 w-3 text-rose-500" />
              Feed Disconnected / Error
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/80 border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-400">
              <Zap className="h-3 w-3" />
              Simulated / Demo Feed
            </span>
          )}

          <button
            onClick={onScanNow}
            disabled={isScanning}
            className="ml-2 p-1.5 text-slate-500 dark:text-slate-400 hover:text-cyan-600 dark:hover:text-cyan-400 hover:bg-slate-200 dark:hover:bg-dark-800 rounded-lg transition"
            title="Scan Now"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isScanning ? 'animate-spin text-cyan-500 dark:text-cyan-400' : ''}`} />
          </button>
        </div>

        {/* Right Actions: Theme Toggle & Auth CTA */}
        <div className="flex items-center gap-3">
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-dark-700 bg-slate-100 dark:bg-dark-900 text-slate-700 dark:text-slate-300 hover:text-cyan-600 dark:hover:text-cyan-400 hover:border-cyan-400 dark:hover:border-cyan-600 shadow-sm transition flex items-center justify-center"
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            aria-label="Toggle theme"
          >
            {theme === 'light' ? (
              <Moon className="h-4 w-4 text-slate-700" />
            ) : (
              <Sun className="h-4 w-4 text-amber-400" />
            )}
          </button>

          {showAuthenticated ? (
            <div className="flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800/80 rounded-xl px-3 py-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              <div className="text-left">
                <span className="block text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
                  Dhan Active: {clientId || 'Connected'}
                </span>
                <span
                  className="block text-[10px] text-emerald-600 dark:text-emerald-400 font-mono"
                  title={`Remaining session hours: ${countdown || '24h 00m'}`}
                >
                  Token: {countdown || '24h 00m'}
                </span>
              </div>
              <button
                onClick={disconnect}
                className="ml-2 text-slate-500 dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition"
                title="Disconnect Token"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setModalOpen(true)}
              className="flex items-center gap-2 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-cyan-600/20 transition active:scale-95"
            >
              <Key className="h-4 w-4" />
              Connect Dhan Feed
            </button>
          )}
        </div>
      </header>

      {/* Connect Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-dark-800 border border-dark-600 rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 rounded-xl bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400">
                <Key className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Connect Dhan Live Trading</h3>
                <p className="text-xs text-slate-400">Zero-Persistence: Stored only in browser session memory</p>
              </div>
            </div>

            {/* Mode Switch Tabs */}
            <div className="flex border-b border-dark-600 mb-4">
              <button
                type="button"
                onClick={() => setAuthTab('oauth')}
                className={`flex-1 py-2 text-xs font-bold transition border-b-2 ${
                  authTab === 'oauth'
                    ? 'border-cyan-500 text-cyan-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                1-Click Dhan OAuth
              </button>
              <button
                type="button"
                onClick={() => setAuthTab('manual')}
                className={`flex-1 py-2 text-xs font-bold transition border-b-2 ${
                  authTab === 'manual'
                    ? 'border-cyan-500 text-cyan-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Manual 24h JWT
              </button>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {error}
              </div>
            )}

            {authTab === 'oauth' ? (
              <form onSubmit={handleOAuthSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Dhan Client ID
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Your 10-digit Dhan ID (e.g. 1000000001)"
                    value={oauthClientId}
                    onChange={(e) => setOauthClientId(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-600 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Dhan App ID / API Key
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="API Key generated in Dhan Developer Portal"
                    value={oauthAppId}
                    onChange={(e) => setOauthAppId(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-600 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Dhan App Secret
                  </label>
                  <input
                    type="password"
                    required
                    placeholder="API Secret generated in Dhan Developer Portal"
                    value={oauthAppSecret}
                    onChange={(e) => setOauthAppSecret(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-600 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                <div className="p-3 bg-dark-900/60 border border-dark-700 rounded-xl text-[11px] text-slate-400 space-y-1">
                  <p className="flex items-center gap-1.5 text-cyan-400 font-semibold">
                    <ShieldCheck className="h-3.5 w-3.5" /> 1-Click Official Dhan Login
                  </p>
                  <p>
                    Redirects securely to Dhan login portal. Your credentials and generated token remain strictly in session memory.
                  </p>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-5 py-2.5 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition shadow-md shadow-cyan-600/20"
                  >
                    {loading ? 'Redirecting...' : 'Connect with Dhan'}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleManualSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Dhan Client ID
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. 1000000001"
                    value={inputClientId}
                    onChange={(e) => setInputClientId(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-600 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    24-Hour Access Token (JWT)
                  </label>
                  <textarea
                    required
                    rows={3}
                    placeholder="Paste your 24h JWT token from Dhan Web Settings"
                    value={inputToken}
                    onChange={(e) => setInputToken(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-600 rounded-xl px-3.5 py-2 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
                  />
                </div>

                <div className="p-3 bg-dark-900/60 border border-dark-700 rounded-xl text-[11px] text-slate-400 space-y-1">
                  <p className="flex items-center gap-1.5 text-cyan-400 font-semibold">
                    <ShieldCheck className="h-3.5 w-3.5" /> Zero Token Persistence Guarantee
                  </p>
                  <p>
                    Tokens remain strictly in your browser session memory and are passed via secure HTTP headers. Automatically cleared upon tab close.
                  </p>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-5 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition"
                  >
                    {loading ? 'Verifying...' : 'Connect Session'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
};
