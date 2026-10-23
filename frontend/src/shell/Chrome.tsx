import React, { useState } from 'react';
import { KeyRound, Key, LogOut, Moon, RefreshCw, Rows3, Search, ShieldCheck, Sun } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { useTheme } from '../context/ThemeContext';
import { DhanConnectDialog } from '../components/DhanConnectDialog';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { actions, useInFlight } from '../data/actions';
import { openCapabilityDialog } from '../data/auth';
import { appStore, useApp, useNow } from '../data/appStore';
import { formatIst, marketSession } from '../lib/time';
import { KillSwitchButton, LossCapMeter } from './KillSwitch';
import { useTradingMode } from './ModeBanner';

export function setDensity(density: 'compact' | 'comfortable'): void {
  appStore.setState((s) => ({ ui: { ...s.ui, density } }));
  try { document.documentElement.dataset.density = density; } catch { /* no document */ }
  try { localStorage.setItem('bb_density', density); } catch { /* storage unavailable */ }
}

export interface ChromeProps {
  /** Slot for the workspace switcher (Task 3.3). */
  workspaceSlot?: React.ReactNode;
  /** Slot for the command palette trigger (Task 6.1). */
  paletteSlot?: React.ReactNode;
  /** Slot for the alerts badge (Task 5.9). */
  alertsSlot?: React.ReactNode;
}

const SESSION_LABEL = { 'pre-open': 'Pre-open', open: 'Open', closed: 'Closed', weekend: 'Weekend' } as const;

/** Fixed top bar, outside Dockview: the kill switch lives here so no layout can hide it. */
export const Chrome: React.FC<ChromeProps> = ({ workspaceSlot, paletteSlot, alertsSlot }) => {
  const { theme, toggleTheme } = useTheme();
  const { isLoggedIn, clientId, disconnect, tokenExpiryCountdown } = useDhanAuth();
  const [dhanOpen, setDhanOpen] = useState(false);
  const scanning = useApp((s) => s.scanner.is_scanning);
  const activeMode = useApp((s) => s.scanner.active_mode);
  const feedStatus = useApp((s) => s.scanner.feed_status);
  const ws = useApp((s) => Boolean(s.scanner.ws_connected));
  const stream = useApp((s) => s.stream);
  const openCount = useApp((s) => s.scanner.paper_portfolio?.active_positions?.length ?? 0);
  const density = useApp((s) => s.ui.density);
  const mode = useTradingMode();
  const scanBusy = useInFlight('scanNow');
  const now = useNow();
  const authenticated = isLoggedIn && activeMode !== 'demo';

  return (
    <>
      <header className="shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1" data-testid="chrome"
        style={{ background: 'var(--panel)', borderBottom: '1px solid var(--line-strong)', minHeight: 40 }}>
        <h1 className="font-semibold text-base tracking-tight m-0">BB Options</h1>
        {workspaceSlot}
        <span className="desk-pill nomark" data-testid="mode-pill" style={mode === 'paper' ? { background: 'var(--mode-paper)', color: 'var(--mode-paper-fg)' } : undefined}>
          {mode === 'paper' ? 'PAPER' : mode === 'live' ? 'LIVE' : 'DRY RUN'}
        </span>

        <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-xs desk-muted">
          <LossCapMeter />
          <span className="desk-num" data-testid="open-count">Open {openCount}</span>
          <KillSwitchButton />
          <ConnectionStatus activeMode={activeMode} feedStatus={feedStatus} wsConnected={ws} stream={stream} />
          <span className="desk-num" title="Market session in IST">{SESSION_LABEL[marketSession(new Date(now))]} · {formatIst(now)} IST</span>
          {alertsSlot}
          <button type="button" className="desk-btn" disabled={scanning || scanBusy} aria-label="Scan now" title="Scan now" onClick={() => void actions.scanNow()}>
            <RefreshCw className={`h-3.5 w-3.5 ${scanning ? 'animate-spin' : ''}`} aria-hidden />
          </button>
          {paletteSlot ?? (
            <span className="desk-btn" aria-hidden style={{ opacity: 0.6 }}><Search className="h-3.5 w-3.5" /></span>
          )}
          <button type="button" className="desk-btn" aria-pressed={density === 'comfortable'} aria-label="Toggle comfortable density" title="Density: compact or comfortable"
            onClick={() => setDensity(density === 'compact' ? 'comfortable' : 'compact')}>
            <Rows3 className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button type="button" className="desk-btn" aria-label="Toggle theme" title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} onClick={toggleTheme}>
            {theme === 'light' ? <Moon className="h-3.5 w-3.5" aria-hidden /> : <Sun className="h-3.5 w-3.5" aria-hidden />}
          </button>
          <button type="button" className="desk-btn" aria-label="Dashboard key" title="Enter dashboard key" onClick={openCapabilityDialog}>
            <KeyRound className="h-3.5 w-3.5" aria-hidden />
          </button>
          {authenticated ? (
            <div className="flex items-center gap-2 desk-pill up" style={{ padding: '4px 10px' }}>
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
              <span>Dhan Active: {clientId || 'Connected'}</span>
              <span className="desk-num" title="Remaining session hours">Token: {tokenExpiryCountdown || '24h 00m'}</span>
              <button type="button" onClick={disconnect} title="Disconnect Token" aria-label="Disconnect"><LogOut className="h-3.5 w-3.5" aria-hidden /></button>
            </div>
          ) : (
            <button type="button" className="desk-btn accent" onClick={() => setDhanOpen(true)}><Key className="h-3.5 w-3.5" aria-hidden /> Connect Dhan</button>
          )}
        </div>
      </header>
      {dhanOpen && <DhanConnectDialog onClose={() => setDhanOpen(false)} />}
    </>
  );
};
