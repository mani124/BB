import React, { useState, useEffect } from 'react';
import { DhanAuthProvider, useDhanAuth } from './context/DhanAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { Header } from './components/Header';
import { IndexHeroRadar } from './components/IndexHeroRadar';
import { SetupFilterTabs } from './components/SetupFilterTabs';
import { SignalTable } from './components/SignalTable';
import { CompactStrip, OpenPositionsPanel, liveTrades } from './components/PaperPortfolioView';
import { ReviewScreen } from './components/ReviewScreen';
import { AppTab, PaperPortfolio, PaperPosition, ScannerState, SetupMode, Signal } from './types';
import { SettingsPanel } from './components/SettingsPanel';
import { EarningsPanel } from './components/EarningsPanel';
import { AlertCircle, X, KeyRound, Lock, CheckCircle2 } from 'lucide-react';
import { isIndexSymbol } from './components/instruments';
import { apiFetch, bootstrapDashboardSession, getDashboardCapability, setDashboardCapability } from './api/client';

const SIGNALS_SHOWN = 12;

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

      // Default stream state snapshot updates
      eventSource.onmessage = (event) => {
        try {
          const data: ScannerState = JSON.parse(event.data);
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
      }
    } catch (e) {
      console.error('Toggle auto trade failed', e);
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
      }
    } catch (e) {
      console.error('Change setup mode failed', e);
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
      }
    } catch (e) {
      console.error('Change lots failed', e);
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

  // Confirmed signals first (stable), short list by default.
  const sortedSignals = [...filteredSignals].sort((x, y) => Number(y.is_confirmed !== false) - Number(x.is_confirmed !== false));
  const [showAllSignals, setShowAllSignals] = useState(false);
  const shownSignals = showAllSignals ? sortedSignals : sortedSignals.slice(0, SIGNALS_SHOWN);

  const activePositionsCount = state.paper_portfolio?.active_positions?.length || 0;

  const activeSignalIds = React.useMemo(() => {
    return new Set(state.paper_portfolio?.active_positions?.map((p) => p.signal_id) || []);
  }, [state.paper_portfolio?.active_positions]);

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
      />

      <main className="flex-1 min-h-0 max-w-[1600px] w-full mx-auto px-4 sm:px-6 py-2 flex flex-col gap-2">
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

        <CompactStrip portfolio={state.paper_portfolio} />

        {activeTab === 'scanner' ? (
          <>
            <IndexHeroRadar radar={state.radar} />

            <div className="desk-panel px-3.5 py-1.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="desk-label">Bias</span>
                <span
                  className={`desk-pill ${
                    state.market_bias === 'BULLISH' ? 'up' : state.market_bias === 'BEARISH' ? 'down' : ''
                  }`}
                  title={
                    state.market_bias === 'BULLISH'
                      ? 'PE stock options blocked'
                      : state.market_bias === 'BEARISH'
                      ? 'CE stock options blocked'
                      : undefined
                  }
                >
                  {state.active_mode === 'closed' ? 'MARKET CLOSED' : state.market_bias || 'NEUTRAL'}
                </span>
                {state.top_bullish?.map((sym) => (
                  <span key={sym} className="desk-pill up desk-num" title="Top bullish (CE)">{sym}</span>
                ))}
                {state.top_bearish?.map((sym) => (
                  <span key={sym} className="desk-pill down desk-num" title="Top bearish (PE)">{sym}</span>
                ))}
              </div>
              {state.paper_portfolio && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <button
                    type="button"
                    className={`desk-btn ${state.paper_portfolio.auto_trade_enabled ? 'solid' : ''}`}
                    onClick={() => handleToggleAutoTrade(!state.paper_portfolio!.auto_trade_enabled)}
                  >
                    Auto-enter: {state.paper_portfolio.auto_trade_enabled ? 'ON' : 'OFF'}
                  </button>
                  <div className="desk-seg" role="group" aria-label="Lot multiplier">
                    {[2, 4, 6, 8, 10].map((l) => (
                      <button key={l} type="button" aria-pressed={state.paper_portfolio!.default_lots === l} onClick={() => handleChangeLots(l)}>
                        {l}x
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] lg:grid-rows-1 gap-3 lg:flex-1 lg:min-h-0">
              <OpenPositionsPanel
                compact
                positions={state.paper_portfolio?.active_positions ?? []}
                onClosePosition={handleClosePosition}
              />

              <section className="desk-panel desk-pane" aria-labelledby="signals-title">
                <div className="desk-ph">
                  <h2 id="signals-title">Active Strategy Signals</h2>
                  <span className="desk-pill desk-num">{filteredSignals.length} active</span>
                  <span className="text-xs desk-muted ml-auto">
                    {wsConnected ? 'Real-time ticks' : 'Scanned every ~8s'} · confirm on candle close
                  </span>
                </div>
                <SetupFilterTabs
                  compact
                  selectedSetup={selectedSetup}
                  onSelectSetup={setSelectedSetup}
                  selectedOptionType={selectedOptionType}
                  onSelectOptionType={setSelectedOptionType}
                  selectedInstrumentType={selectedInstrumentType}
                  onSelectInstrumentType={setSelectedInstrumentType}
                  selectedTimeframe={selectedTimeframe}
                  onSelectTimeframe={setSelectedTimeframe}
                  totalSignals={filteredSignals.length}
                />
                <div className="desk-scroll">
                  <SignalTable
                    signals={shownSignals}
                    onPaperBuy={handlePaperBuy}
                    activeSignalIds={activeSignalIds}
                  />
                  {sortedSignals.length > SIGNALS_SHOWN && (
                    <button
                      type="button"
                      className="w-full py-2 text-sm font-medium"
                      style={{ color: 'var(--accent)' }}
                      onClick={() => setShowAllSignals((v) => !v)}
                    >
                      {showAllSignals ? 'Show fewer signals' : `Show all ${sortedSignals.length} signals`}
                    </button>
                  )}
                </div>
              </section>
            </div>
          </>
        ) : activeTab === 'earnings' ? (
          <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3"><EarningsPanel /></div>
        ) : activeTab === 'settings' ? (
          <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3"><SettingsPanel /></div>
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
          <div className="desk-overlay">
            <div className="desk-modal p-5">
              <div className="flex items-center justify-between pb-3 mb-4" style={{ borderBottom: '1px solid var(--line)' }}>
                <div className="flex items-center gap-3">
                  <KeyRound className="w-5 h-5" style={{ color: 'var(--accent)' }} />
                  <div>
                    <h3 className="text-base font-semibold">Dashboard key</h3>
                    <p className="text-xs desk-muted">Needed to trade, reset and stream live data</p>
                  </div>
                </div>
                <button type="button" onClick={() => setCapabilityModalOpen(false)} title="Close" aria-label="Close" className="desk-btn">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {capabilityError && (
                <div className="desk-alert mb-4 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{capabilityError}</span>
                </div>
              )}
              {capabilitySuccess && (
                <div className="desk-pill up mb-4 flex items-center gap-2" style={{ borderRadius: 8, padding: '8px 12px' }}>
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>Key accepted. Session started.</span>
                </div>
              )}

              <form onSubmit={handleSaveCapability} className="space-y-4">
                <div>
                  <label htmlFor="capability-input" className="block text-xs font-semibold mb-1.5 desk-muted">
                    Access key
                  </label>
                  <input
                    id="capability-input"
                    type="password"
                    value={capabilityInput}
                    onChange={(e) => setCapabilityInput(e.target.value)}
                    placeholder="Enter your dashboard key"
                    className="desk-input font-mono"
                    required
                  />
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button type="button" onClick={() => setCapabilityModalOpen(false)} className="desk-btn">Cancel</button>
                  <button type="submit" className="desk-btn solid">
                    <Lock className="w-3.5 h-3.5" />
                    Authorize session
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>

    </div>
  );
};

export default function App() {
  return (
    <ThemeProvider>
      <DhanAuthProvider>
        <DashboardContent />
      </DhanAuthProvider>
    </ThemeProvider>
  );
}
