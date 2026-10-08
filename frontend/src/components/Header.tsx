import React, { useState } from 'react';
import { Activity, ShieldCheck, Key, RefreshCw, LogOut, Radio, Zap } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';

interface HeaderProps {
  activeMode: 'live' | 'demo';
  scanCycleCount: number;
  lastScanTime: string;
  isScanning: boolean;
  scanProgress: number;
  onScanNow: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeMode,
  scanCycleCount,
  lastScanTime,
  isScanning,
  scanProgress,
  onScanNow,
}) => {
  const { isLoggedIn, clientId, connect, disconnect, error } = useDhanAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [inputClientId, setInputClientId] = useState('');
  const [inputToken, setInputToken] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
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

  return (
    <>
      <header className="border-b border-dark-700 bg-dark-800/80 backdrop-blur sticky top-0 z-40 px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
                BB Options Trading PRO
              </span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-950/70 border border-cyan-800 text-cyan-400">
                NSE Derivatives
              </span>
            </div>
            <p className="text-xs text-slate-400">
              High-Velocity Bollinger Band Setups (Setups 1, 3, 2, 4) • Zero-Token Persistence
            </p>
          </div>
        </div>

        {/* Center Heartbeat & Progress */}
        <div className="flex items-center gap-3 bg-dark-900/80 border border-dark-700 rounded-xl px-4 py-2">
          <div className="flex items-center gap-2">
            <Radio className={`h-4 w-4 ${isScanning ? 'text-cyan-400 animate-pulse' : 'text-slate-500'}`} />
            <span className="text-xs font-semibold text-slate-300">
              Cycle #{scanCycleCount}
            </span>
          </div>

          <div className="h-3 w-[1px] bg-dark-600" />

          <span className="text-xs text-slate-400">
            Last: <strong className="text-slate-200 font-mono">{lastScanTime || 'Ready'}</strong>
          </span>

          <div className="h-3 w-[1px] bg-dark-600" />

          {/* Mode Badge */}
          {activeMode === 'live' ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-700 text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
              Live Market Feed
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-950/80 border border-amber-700 text-amber-400">
              <Zap className="h-3 w-3" />
              Simulated / Demo Feed
            </span>
          )}

          <button
            onClick={onScanNow}
            disabled={isScanning}
            className="ml-2 p-1.5 text-slate-400 hover:text-cyan-400 hover:bg-dark-800 rounded-lg transition"
            title="Scan Now"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isScanning ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>

        {/* Auth CTA */}
        <div className="flex items-center gap-3">
          {isLoggedIn ? (
            <div className="flex items-center gap-2 bg-emerald-950/40 border border-emerald-800/80 rounded-xl px-3 py-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <div className="text-left">
                <span className="block text-[11px] font-semibold text-emerald-300">
                  Dhan Active: {clientId}
                </span>
                <span className="block text-[10px] text-emerald-500">Session Secure</span>
              </div>
              <button
                onClick={disconnect}
                className="ml-2 text-slate-400 hover:text-rose-400 transition"
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
              Enter 24h Dhan Token
            </button>
          )}
        </div>
      </header>

      {/* Zero Token Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-dark-800 border border-dark-600 rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 rounded-xl bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400">
                <Key className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Enter 24h Dhan Token</h3>
                <p className="text-xs text-slate-400">Zero-Persistence: Never saved to disk or git</p>
              </div>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
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
          </div>
        </div>
      )}
    </>
  );
};
