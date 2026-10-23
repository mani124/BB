import React, { useState } from 'react';
import { ShieldCheck, Key, RefreshCw, LogOut, Sun, Moon, KeyRound, Radar, Layers, ArrowLeftRight, History, SlidersHorizontal } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { useTheme } from '../context/ThemeContext';
import { RiskControls } from './RiskControls';
import { Tabs } from './Tabs';
import { DhanConnectDialog } from './DhanConnectDialog';
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
    disconnect,
    tokenExpiryCountdown: contextCountdown,
  } = useDhanAuth();
  const { theme, toggleTheme } = useTheme();

  const [modalOpen, setModalOpen] = useState(false);


  const countdown = propCountdown || contextCountdown;
  const showAuthenticated = (isLoggedIn || Boolean(propCountdown)) && activeMode !== 'demo';
  const isWsLive = feedStatus === 'WS_LIVE' || wsConnected === true;

  return (
    <>
      <header
        className="shrink-0 z-40 px-4 sm:px-6 flex flex-wrap items-center gap-x-6 gap-y-1 min-h-[44px] py-1"
        style={{ background: 'var(--panel)', borderBottom: '1px solid var(--line-strong)' }}
      >
        <h1 className="font-semibold text-base tracking-tight m-0">BB Options</h1>

        {onTabChange && (
          <Tabs<AppTab>
            idPrefix="main"
            label="Sections"
            className="desk-topnav"
            tabClassName="desk-navtab"
            value={activeTab ?? 'watch'}
            onChange={onTabChange}
            items={[
              { id: 'watch', name: 'Watch', label: <><Radar className="h-[18px] w-[18px]" aria-hidden /><span>Watch</span></> },
              { id: 'books', name: 'Books', label: <><Layers className="h-[18px] w-[18px]" aria-hidden /><span>Books</span></> },
              { id: 'trades', name: 'Trades', label: <><ArrowLeftRight className="h-[18px] w-[18px]" aria-hidden /><span>Trades</span></> },
              { id: 'session', name: 'Session', label: <><History className="h-[18px] w-[18px]" aria-hidden /><span>Session</span></> },
              { id: 'control', name: 'Control', label: <><SlidersHorizontal className="h-[18px] w-[18px]" aria-hidden /><span>Control</span></> },
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
          <ConnectionStatus activeMode={activeMode} feedStatus={feedStatus} wsConnected={isWsLive} stream={stream} />
          <RiskControls risk={risk ?? undefined} onKillSwitch={onKillSwitch} compact />
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

      {modalOpen && <DhanConnectDialog onClose={() => setModalOpen(false)} />}
    </>
  );
};
