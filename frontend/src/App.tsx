import React, { useState, useEffect } from 'react';
import { DhanAuthProvider, useDhanAuth } from './context/DhanAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { Header, type StreamStatus } from './components/Header';
import { liveTrades } from './components/format';
import { WatchScreen } from './components/WatchScreen';
import { CapabilityDialog } from './components/CapabilityDialog';
import { LiveAnnouncer } from './components/LiveAnnouncer';
import { ReviewScreen } from './components/ReviewScreen';
import { AppTab, PaperPortfolio, PaperPosition, ScannerState, SetupMode, Signal } from './types';
import { SettingsPanel } from './components/SettingsPanel';
import { EarningsPanel } from './components/EarningsPanel';
import { AlertCircle, X } from 'lucide-react';
import { isIndexSymbol } from './components/instruments';
import { apiFetch, bootstrapDashboardSession, getDashboardCapability, setDashboardCapability } from './api/client';

const DashboardContent: React.FC = () => {
  const [state, setState] = useState<ScannerState>({
    signals: [],
    radar: {},
    last_scan_time: '',
    scan_cycle_count: 0,
    is_scanning: false,
    scan_progress: 0,
    universe_count: 34,
    active_mode: 'demo',
  });

  const [activeTab, setActiveTab] = useState<AppTab>('scanner');
  const [selectedSetup, setSelectedSetup] = useState<string>('ALL');
  const [selectedOptionType, setSelectedOptionType] = useState<string>('ALL');
  const [selectedInstrumentType, setSelectedInstrumentType] = useState<string>('ALL');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('ALL');
  const [wsConnected, setWsConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [stream, setStream] = useState<StreamStatus>({ state: 'connecting', ageSec: 0 });
  const lastMessageAt = React.useRef(0);
  const streamErrored = React.useRef(false);
  const [announcement, setAnnouncement] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const { connect } = useDhanAuth();
  const reconnectingRef = React.useRef(false);

  const [capabilityModalOpen, setCapabilityModalOpen] = useState(false);
  const [capabilityInput, setCapabilityInput] = useState(getDashboardCapability());
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilitySuccess, setCapabilitySuccess] = useState(false);
  const [sessionNonce, setSessionNonce] = useState(0);
  // The live stream carries totals and open positions only; the closed-trade journal is
  // fetched separately whenever the server's closed-trade count changes.
  const [closedTrades, setClosedTrades] = useState<PaperPosition[]>([]);

  const applyPortfolio = (portData: PaperPortfolio) => {
    setState((prev) => ({ ...prev, paper_portfolio: portData }));
    setClosedTrades(portData.closed_trades ?? []);
  };

  const closedCount = state.paper_portfolio?.closed_trades_count;
  useEffect(() => {
    let cancelled = false;
    apiFetch('/api/paper/portfolio')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: PaperPortfolio | null) => {
        if (!cancelled && data) setClosedTrades(data.closed_trades ?? []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [closedCount, state.active_mode, sessionNonce]);

  // Stream health: "live" while messages keep arriving, "stale" once they stop, "reconnecting" after an error.
  useEffect(() => {
    const id = setInterval(() => {
      if (lastMessageAt.current === 0) return;
      const age = Math.round((Date.now() - lastMessageAt.current) / 1000);
      const next: StreamStatus = streamErrored.current
        ? { state: 'reconnecting', ageSec: age }
        : age > 15
        ? { state: 'stale', ageSec: age }
        : { state: 'live', ageSec: 0 };
      setStream((prev) => (prev.state === next.state && (next.state === 'live' || prev.ageSec === next.ageSec) ? prev : next));
    }, 2000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (actionError) {
      const timer = setTimeout(() => setActionError(null), 8000);
      return () => clearTimeout(timer);
    }
  }, [actionError]);

  const handleSaveCapability = async (e: React.FormEvent) => {
    e.preventDefault();
    setCapabilityError(null);
    setCapabilitySuccess(false);
    const ok = await bootstrapDashboardSession(capabilityInput);
    if (ok) {
      setCapabilitySuccess(true);
      setSessionNonce((n) => n + 1); // restart snapshot + live stream now that we are authorized
      setTimeout(() => {
        setCapabilityModalOpen(false);
        setCapabilitySuccess(false);
      }, 700);
      try {
        const res = await apiFetch('/api/signals');
        if (res.ok) {
          const data = await res.json();
          setState((prev) => ({ ...prev, ...data }));
          setWsConnected(Boolean(data.feed_status === 'WS_LIVE' || data.ws_connected));
        }
      } catch (err) {}
    } else {
      setCapabilityError('That key was not accepted. Check it and try again.');
    }
  };

  // Fetch initial snapshot and connect to SSE stream on mount
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimeout: any = null;
    let isCancelled = false;

    // Fast initial fetch so UI renders immediately
    const fetchSnapshot = async () => {
      try {
        const res = await apiFetch('/api/signals');
        if (res.status === 401) {
          setCapabilityModalOpen(true);
          return;
        }
        if (res.ok) {
          const data = await res.json();
          if (!isCancelled) {
            setState((prev) => ({ ...prev, ...data }));
            setLoaded(true);
            setWsConnected(Boolean(data.feed_status === 'WS_LIVE' || data.ws_connected));
            if (data.active_mode === 'demo' && !reconnectingRef.current) {
              const savedId = sessionStorage.getItem('dhan_client_id');
              const savedToken = sessionStorage.getItem('dhan_access_token');
              if (savedId && savedToken && !savedToken.includes('*')) {
                reconnectingRef.current = true;
                connect(savedId, savedToken).finally(() => {
                  setTimeout(() => { reconnectingRef.current = false; }, 15000);
                });
              }
            }
          }
        }
      } catch (e) {
        // SSE will hydrate state
      }
    };

    const connectSSE = () => {
      if (isCancelled) return;
      eventSource = new EventSource('/api/signals/stream');

      // Listen for sub-second real-time tick named events
      eventSource.addEventListener('tick', (event: MessageEvent) => {
        try {
          const tickData = JSON.parse(event.data);
          setWsConnected(true);
          // Only update radar spot prices for underlying spot ticks, never option contracts
          if (tickData.symbol && tickData.ltp && !tickData.is_option) {
            setState((prev) => {
              const sym = tickData.symbol;
              const prevRadar = prev.radar[sym];
              if (!prevRadar) return prev;
              return {
                ...prev,
                radar: {
                  ...prev.radar,
                  [sym]: {
                    ...prevRadar,
                    close: tickData.ltp,
                  },
                },
              };
            });
          }
        } catch (err) {
          console.error('Failed to parse SSE tick', err);
        }
      });

      // Throttled open-position and totals updates between full scans (about once a second)
      eventSource.addEventListener('portfolio', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          if (data?.paper_portfolio) {
            lastMessageAt.current = Date.now();
            setState((prev) => ({ ...prev, paper_portfolio: data.paper_portfolio }));
          }
        } catch (err) {
          console.error('Failed to parse SSE portfolio', err);
        }
      });

      // Default stream state snapshot updates
      eventSource.onmessage = (event) => {
        try {
          const data: ScannerState = JSON.parse(event.data);
          lastMessageAt.current = Date.now();
          streamErrored.current = false;
          setStream((prev) => (prev.state === 'live' ? prev : { state: 'live', ageSec: 0 }));
          setLoaded(true);
          setState(data);
          // Sync wsConnected with state snapshot to enable HTTP polling fallback
          setWsConnected(Boolean(data.feed_status === 'WS_LIVE' || data.ws_connected));
          if (data.active_mode === 'demo' && !reconnectingRef.current) {
            const savedId = sessionStorage.getItem('dhan_client_id');
            const savedToken = sessionStorage.getItem('dhan_access_token');
            if (savedId && savedToken && !savedToken.includes('*')) {
              reconnectingRef.current = true;
              connect(savedId, savedToken).finally(() => {
                setTimeout(() => { reconnectingRef.current = false; }, 15000);
              });
            }
          }
        } catch (err) {
          console.error('Failed to parse SSE payload', err);
        }
      };

      eventSource.onerror = () => {
        eventSource?.close();
        streamErrored.current = true;
        if (lastMessageAt.current === 0) lastMessageAt.current = Date.now();
        setStream((prev) => (prev.state === 'reconnecting' ? prev : { state: 'reconnecting', ageSec: 0 }));
        setWsConnected(false);
        if (!isCancelled) {
          reconnectTimeout = setTimeout(connectSSE, 3000);
        }
      };
    };

    const initialize = async () => {
      const ok = await bootstrapDashboardSession();
      if (!ok) {
        const checkRes = await apiFetch('/api/signals').catch(() => null);
        if (checkRes && checkRes.status === 401) {
          setCapabilityModalOpen(true);
          return;
        }
      }
      await fetchSnapshot();
      connectSSE();
    };

    initialize();

    return () => {
      isCancelled = true;
      eventSource?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [sessionNonce]);

  const handleScanNow = async () => {
    try {
      const res = await apiFetch('/api/signals/scan-now', { method: 'POST' });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
      }
    } catch (e) {
      console.error('Manual scan failed', e);
    }
  };

  // Paper trading actions
  const handlePaperBuy = async (signal: Signal) => {
    try {
      setActionError(null);
      const res = await apiFetch('/api/paper/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal, lots: state.paper_portfolio?.default_lots || 2 }),
      });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        // Refresh portfolio immediately
        const portRes = await apiFetch('/api/paper/portfolio');
        if (portRes.ok) {
          const portData = await portRes.json();
          applyPortfolio(portData);
        }
      } else {
        const errData = await res.json().catch(() => null);
        const msg = errData?.detail || `Trade rejected (HTTP ${res.status})`;
        setActionError(msg);
      }
    } catch (e: any) {
      console.error('Paper trade failed', e);
      setActionError(e?.message || 'Network error executing trade');
    }
  };

  const handleClosePosition = async (id: string) => {
    try {
      setActionError(null);
      const res = await apiFetch(`/api/paper/close/${encodeURIComponent(id)}`, { method: 'POST' });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        const portRes = await apiFetch('/api/paper/portfolio');
        if (portRes.ok) {
          const portData = await portRes.json();
          applyPortfolio(portData);
        }
      } else {
        const errData = await res.json().catch(() => null);
        const msg = errData?.detail || `Failed to close position (HTTP ${res.status})`;
        setActionError(msg);
      }
    } catch (e: any) {
      console.error('Failed to close position', e);
      setActionError(e?.message || 'Network error closing position');
    }
  };

  const handleToggleAutoTrade = async (enabled: boolean) => {
    try {
      const res = await apiFetch('/api/paper/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_trade_enabled: enabled }),
      });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        const portData = await res.json();
        applyPortfolio(portData);
      } else {
        setActionError(await settingsError(res, 'auto-trade'));
      }
    } catch (e) {
      console.error('Toggle auto trade failed', e);
      setActionError('Network error changing auto-trade.');
    }
  };

  const handleKillSwitch = async (engage: boolean) => {
    try {
      const res = await apiFetch(engage ? '/api/paper/kill-switch' : '/api/paper/kill-switch/release', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: true }),
      });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (!res.ok) {
        setActionError('Kill switch request failed. Please try again.');
        return;
      }
      if (engage) {
        const body = await res.json().catch(() => ({}));
        const failed: string[] = Array.isArray(body?.failed) ? body.failed : [];
        if (failed.length > 0) {
          setActionError(`Kill switch engaged, but ${failed.length} position(s) could not be closed: ${failed.join(', ')}. Close them by hand.`);
        }
      }
      const portRes = await apiFetch('/api/paper/portfolio');
      if (portRes.ok) applyPortfolio(await portRes.json());
    } catch (e) {
      console.error('Kill switch failed', e);
      setActionError('Network error changing the kill switch.');
    }
  };

  const handleChangeSetupMode = async (setup: string, mode: SetupMode) => {
    try {
      const res = await apiFetch('/api/paper/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setup_modes: { [setup]: mode } }),
      });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        const portData = await res.json();
        applyPortfolio(portData);
      } else {
        setActionError(await settingsError(res, 'the setup mode'));
      }
    } catch (e) {
      console.error('Change setup mode failed', e);
      setActionError('Network error changing the setup mode.');
    }
  };

  const handleChangeLots = async (lots: number) => {
    try {
      const res = await apiFetch('/api/paper/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_lots: lots }),
      });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        const portData = await res.json();
        applyPortfolio(portData);
      } else {
        setActionError(await settingsError(res, 'the lot size'));
      }
    } catch (e) {
      console.error('Change lots failed', e);
      setActionError('Network error changing the lot size.');
    }
  };

  const handleResetPortfolio = async () => {
    if (!window.confirm('Are you sure you want to reset all forward-testing paper trade logs?')) return;
    try {
      const res = await apiFetch('/api/paper/reset', { method: 'POST' });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (!res.ok) {
        setActionError('Failed to reset paper portfolio. Please try again.');
        return;
      }
      const portRes = await apiFetch('/api/paper/portfolio');
      if (portRes.ok) {
        const portData = await portRes.json();
        applyPortfolio(portData);
      }
    } catch (e) {
      console.error('Reset portfolio failed', e);
    }
  };

  const openCapabilityModal = () => {
    setCapabilityInput(getDashboardCapability());
    setCapabilityError(null);
    setCapabilitySuccess(false);
    setCapabilityModalOpen(true);
  };

  // Filter signals
  const filteredSignals = state.signals.filter((sig) => {
    if (selectedSetup !== 'ALL') {
      const match =
        sig.setup_type === selectedSetup ||
        sig.setup_type?.toLowerCase().includes(selectedSetup.toLowerCase()) ||
        selectedSetup.toLowerCase().includes(sig.setup_type?.toLowerCase());
      if (!match) return false;
    }
    if (selectedOptionType !== 'ALL' && sig.option_type !== selectedOptionType) return false;
    const isIndex = isIndexSymbol(sig.symbol);
    if (selectedInstrumentType === 'INDEX' && !isIndex) return false;
    if (selectedInstrumentType === 'STOCK' && isIndex) return false;
    if (selectedTimeframe !== 'ALL' && sig.timeframe !== selectedTimeframe) return false;
    return true;
  });

  const activePositionsCount = state.paper_portfolio?.active_positions?.length || 0;

  const activeSignalIds = React.useMemo(() => {
    return new Set(state.paper_portfolio?.active_positions?.map((p) => p.signal_id) || []);
  }, [state.paper_portfolio?.active_positions]);

  // Tell screen readers about new confirmed signals and risk-state changes.
  const seenSignals = React.useRef<Set<string> | null>(null);
  useEffect(() => {
    const confirmed = state.signals.filter((x) => x.is_confirmed !== false);
    if (seenSignals.current === null) {
      if (loaded) seenSignals.current = new Set(confirmed.map((x) => x.id));
      return;
    }
    const fresh = confirmed.filter((x) => !seenSignals.current!.has(x.id));
    fresh.forEach((x) => seenSignals.current!.add(x.id));
    if (fresh.length > 0) {
      const f = fresh[0];
      setAnnouncement(`New signal: ${f.symbol} ${f.option_type}${fresh.length > 1 ? ` and ${fresh.length - 1} more` : ''}`);
    }
  }, [state.signals, loaded]);

  const risk = state.paper_portfolio?.risk;
  useEffect(() => {
    if (risk?.kill_switch_active) setAnnouncement('Kill switch is on. New entries are paused.');
    else if (risk?.loss_cap_tripped) setAnnouncement('Daily loss cap hit. New entries are off for today.');
  }, [risk?.kill_switch_active, risk?.loss_cap_tripped]);

  return (
    <div className="min-h-screen flex flex-col lg:h-screen lg:overflow-hidden">
      <Header
        activeMode={state.active_mode}
        scanCycleCount={state.scan_cycle_count}
        lastScanTime={state.last_scan_time}
        isScanning={state.is_scanning}
        scanProgress={state.scan_progress}
        onScanNow={handleScanNow}
        feedStatus={state.feed_status}
        wsConnected={state.ws_connected || wsConnected}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        openPositionsCount={activePositionsCount}
        onOpenAccessKey={openCapabilityModal}
        risk={state.paper_portfolio?.risk}
        onKillSwitch={handleKillSwitch}
        stream={stream}
      />
      <LiveAnnouncer message={announcement} />

      <main className="flex-1 min-h-0 w-full px-4 sm:px-6 py-2 flex flex-col gap-2">
        <div id="main-panel" role="tabpanel" aria-labelledby={`main-tab-${activeTab}`} className="contents">
        {actionError && (
          <div className="desk-alert flex items-center justify-between gap-3" role="alert">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{actionError}</span>
            </div>
            <button type="button" onClick={() => setActionError(null)} title="Dismiss" aria-label="Dismiss">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {activeTab === 'scanner' ? (
          <WatchScreen
            state={state}
            loaded={loaded}
            wsConnected={wsConnected}
            filters={{ setup: selectedSetup, optionType: selectedOptionType, instrumentType: selectedInstrumentType, timeframe: selectedTimeframe }}
            onFilters={(f) => {
              if (f.setup !== undefined) setSelectedSetup(f.setup);
              if (f.optionType !== undefined) setSelectedOptionType(f.optionType);
              if (f.instrumentType !== undefined) setSelectedInstrumentType(f.instrumentType);
              if (f.timeframe !== undefined) setSelectedTimeframe(f.timeframe);
            }}
            filteredSignals={filteredSignals}
            closedTrades={liveTrades(closedTrades)}
            activeSignalIds={activeSignalIds}
            onPaperBuy={handlePaperBuy}
            onClosePosition={handleClosePosition}
            onToggleAutoTrade={handleToggleAutoTrade}
            onChangeLots={handleChangeLots}
          />
        ) : activeTab === 'earnings' ? (
          <div className="flex flex-col lg:flex-1 lg:min-h-0"><EarningsPanel /></div>
        ) : activeTab === 'settings' ? (
          <div className="flex flex-col lg:flex-1 lg:min-h-0"><SettingsPanel /></div>
        ) : (
          <ReviewScreen
            portfolio={state.paper_portfolio}
            closedTrades={liveTrades(closedTrades)}
            onClosePosition={handleClosePosition}
            onToggleAutoTrade={handleToggleAutoTrade}
            onChangeLots={handleChangeLots}
            onChangeSetupMode={handleChangeSetupMode}
            onResetPortfolio={handleResetPortfolio}
          />
        )}

        {capabilityModalOpen && (
          <CapabilityDialog
            value={capabilityInput}
            onChange={setCapabilityInput}
            error={capabilityError}
            success={capabilitySuccess}
            onSubmit={handleSaveCapability}
            onClose={() => setCapabilityModalOpen(false)}
          />
        )}
        </div>
      </main>

    </div>
  );
};

/** Message for a rejected settings change, so a toggle that snapped back is never unexplained. */
async function settingsError(res: Response, what: string): Promise<string> {
  const body = await res.json().catch(() => null);
  const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`;
  return `Could not change ${what}: ${detail}`;
}

export default function App() {
  return (
    <ThemeProvider>
      <DhanAuthProvider>
        <DashboardContent />
      </DhanAuthProvider>
    </ThemeProvider>
  );
}
