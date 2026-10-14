import React, { useState, useEffect } from 'react';
import { DhanAuthProvider, useDhanAuth } from './context/DhanAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { Header } from './components/Header';
import { IndexHeroRadar } from './components/IndexHeroRadar';
import { SetupFilterTabs } from './components/SetupFilterTabs';
import { SignalCard } from './components/SignalCard';
import { SignalTable } from './components/SignalTable';
import { PaperPortfolioView } from './components/PaperPortfolioView';
import { ScannerState, Signal } from './types';
import { LayoutGrid, Table, Radio, Briefcase, AlertCircle, X, KeyRound, Lock, CheckCircle2 } from 'lucide-react';
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

  const [activeTab, setActiveTab] = useState<'scanner' | 'paper'>('scanner');
  const [selectedSetup, setSelectedSetup] = useState<string>('ALL');
  const [selectedOptionType, setSelectedOptionType] = useState<string>('ALL');
  const [selectedInstrumentType, setSelectedInstrumentType] = useState<string>('ALL');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [wsConnected, setWsConnected] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const { connect } = useDhanAuth();
  const reconnectingRef = React.useRef(false);

  const [capabilityModalOpen, setCapabilityModalOpen] = useState(false);
  const [capabilityInput, setCapabilityInput] = useState(getDashboardCapability());
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilitySuccess, setCapabilitySuccess] = useState(false);
  const [sessionNonce, setSessionNonce] = useState(0);

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
      setCapabilityError('Invalid dashboard capability token. Please verify and try again.');
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
          setState((prev) => ({ ...prev, paper_portfolio: portData }));
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
      const res = await apiFetch(`/api/paper/close/${id}`, { method: 'POST' });
      if (res.status === 401) {
        setCapabilityModalOpen(true);
        setActionError('Unauthorized: Dashboard capability required.');
        return;
      }
      if (res.ok) {
        const portRes = await apiFetch('/api/paper/portfolio');
        if (portRes.ok) {
          const portData = await portRes.json();
          setState((prev) => ({ ...prev, paper_portfolio: portData }));
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
        setState((prev) => ({ ...prev, paper_portfolio: portData }));
      }
    } catch (e) {
      console.error('Toggle auto trade failed', e);
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
        setState((prev) => ({ ...prev, paper_portfolio: portData }));
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
        setState((prev) => ({ ...prev, paper_portfolio: portData }));
      }
    } catch (e) {
      console.error('Reset portfolio failed', e);
    }
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
    const isIndex = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX'].includes(sig.symbol);
    if (selectedInstrumentType === 'INDEX' && !isIndex) return false;
    if (selectedInstrumentType === 'STOCK' && isIndex) return false;
    if (selectedTimeframe !== 'ALL' && sig.timeframe !== selectedTimeframe) return false;
    return true;
  });

  const activePositionsCount = state.paper_portfolio?.active_positions?.length || 0;

  const activeSignalIds = React.useMemo(() => {
    return new Set(state.paper_portfolio?.active_positions?.map((p) => p.signal_id) || []);
  }, [state.paper_portfolio?.active_positions]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 dark:bg-[#0B0E14] text-slate-800 dark:text-slate-100 transition-colors duration-150">
      <Header
        activeMode={state.active_mode}
        scanCycleCount={state.scan_cycle_count}
        lastScanTime={state.last_scan_time}
        isScanning={state.is_scanning}
        scanProgress={state.scan_progress}
        onScanNow={handleScanNow}
        feedStatus={state.feed_status}
        wsConnected={state.ws_connected || wsConnected}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {/* Action Error Notification Banner */}
        {actionError && (
          <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl flex items-center justify-between text-rose-400 text-sm shadow-lg shadow-rose-950/20 backdrop-blur-md animate-in fade-in">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-rose-500/20 rounded-lg">
                <AlertCircle className="w-5 h-5 shrink-0 text-rose-500" />
              </div>
              <div>
                <span className="font-semibold block text-rose-300">Action Notice</span>
                <span className="text-xs text-rose-400/90">{actionError}</span>
              </div>
            </div>
            <button
              onClick={() => setActionError(null)}
              className="p-1.5 hover:bg-rose-500/20 rounded-lg transition text-rose-400 hover:text-rose-200"
              title="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Navigation Tabs: Scanner vs Forward-Testing Paper Portfolio */}

        <div className="flex items-center justify-between border-b border-slate-200 dark:border-dark-700/80 pb-4 mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setActiveTab('scanner')}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-black tracking-wide transition ${
                activeTab === 'scanner'
                  ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-600/30'
                  : 'bg-white dark:bg-dark-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-dark-700 shadow-sm'
              }`}
            >
              <Radio className="h-4 w-4" />
              Strategy Signals Scanner
            </button>

            <button
              onClick={() => setActiveTab('paper')}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-black tracking-wide transition relative ${
                activeTab === 'paper'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                  : 'bg-white dark:bg-dark-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-dark-700 shadow-sm'
              }`}
            >
              <Briefcase className="h-4 w-4" />
              Paper Portfolio & Forward-Testing
              {activePositionsCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-emerald-500 text-white font-mono font-black text-[10px]">
                  {activePositionsCount}
                </span>
              )}
            </button>

            <button
              onClick={() => {
                setCapabilityInput(getDashboardCapability());
                setCapabilityError(null);
                setCapabilitySuccess(false);
                setCapabilityModalOpen(true);
              }}
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-cyan-600 dark:hover:text-cyan-400 bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 shadow-sm transition"
              title="Manage Dashboard Capability Access Key"
            >
              <KeyRound className="h-4 w-4" />
              <span>Access Key</span>
            </button>
          </div>

          <div className="text-xs text-slate-500 dark:text-slate-400">
            {activeTab === 'scanner' ? (
              <span>Signals evaluate on candle closures with live tick verification</span>
            ) : (
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                {wsConnected
                  ? '⚡ Instant sub-second TP/SL execution on live ticks'
                  : 'Auto-evaluates TP/SL every cycle'}
              </span>
            )}
          </div>
        </div>

        {activeTab === 'scanner' ? (
          <>
            {/* Section 1: Benchmark Indices Radar */}
            <div className="mb-2">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-extrabold uppercase tracking-wider text-slate-400">
                  Benchmark Indices Bollinger Radar (5m)
                </h2>
                <span className="text-xs text-slate-500 font-mono">
                  {wsConnected ? '⚡ Real-Time Ticks (Sub-second)' : 'Auto-scanned every ~8s'}
                </span>
              </div>
              <IndexHeroRadar radar={state.radar} />
            </div>

            {/* Section 1.5: Market Bias & Momentum Filter Banner */}
            {(Boolean(state.top_bullish?.length) || Boolean(state.top_bearish?.length) || state.market_bias) && (
              <div className="mb-4 p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-slate-400 font-bold uppercase tracking-wider text-[11px]">Market Bias:</span>
                  <span className={`px-2 py-0.5 rounded font-black tracking-wide ${
                    state.market_bias === 'BULLISH'
                      ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
                      : state.market_bias === 'BEARISH'
                      ? 'bg-rose-950/80 text-rose-400 border border-rose-800'
                      : 'bg-slate-800 text-slate-300'
                  }`}>
                    {state.market_bias || 'NEUTRAL'}
                  </span>
                  <span className="text-[11px] text-slate-500">
                    {state.market_bias === 'BULLISH'
                      ? '(PE stock options blocked)'
                      : state.market_bias === 'BEARISH'
                      ? '(CE stock options blocked)'
                      : ''}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-4">
                  {state.top_bullish && state.top_bullish.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-emerald-400 font-bold">Top Bullish (CE):</span>
                      <div className="flex items-center gap-1">
                        {state.top_bullish.map((sym) => (
                          <span key={sym} className="px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/80 text-emerald-300 font-mono text-[10px] font-bold">
                            {sym}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {state.top_bearish && state.top_bearish.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-rose-400 font-bold">Top Bearish (PE):</span>
                      <div className="flex items-center gap-1">
                        {state.top_bearish.map((sym) => (
                          <span key={sym} className="px-1.5 py-0.5 rounded bg-rose-950/60 border border-rose-800/80 text-rose-300 font-mono text-[10px] font-bold">
                            {sym}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Section 2: Filters & Controls */}
            <SetupFilterTabs
              selectedSetup={selectedSetup}
              onSelectSetup={setSelectedSetup}
              selectedOptionType={selectedOptionType}
              onSelectOptionType={setSelectedOptionType}
              selectedInstrumentType={selectedInstrumentType}
              onSelectInstrumentType={setSelectedInstrumentType}
              selectedTimeframe={selectedTimeframe}
              onSelectTimeframe={setSelectedTimeframe}
              totalSignals={filteredSignals.length}
              viewMode={viewMode}
              onSelectViewMode={setViewMode}
            />

            {/* Section 3: Signals Header & View Switcher */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-extrabold text-white tracking-tight">
                  Active Strategy Signals
                </h3>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-400 font-mono font-bold">
                  {filteredSignals.length} Active
                </span>
              </div>

              <div className="flex items-center gap-1 bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-xl p-1 shadow-sm">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-1.5 rounded-lg transition ${
                    viewMode === 'grid' ? 'bg-cyan-600 text-white' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                  title="Card Grid View"
                >
                  <LayoutGrid className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setViewMode('table')}
                  className={`p-1.5 rounded-lg transition ${
                    viewMode === 'table' ? 'bg-cyan-600 text-white' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                  title="Table View"
                >
                  <Table className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Section 4: Signals Display */}
            {viewMode === 'grid' ? (
              filteredSignals.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {filteredSignals.map((sig) => (
                    <SignalCard
                      key={sig.id}
                      signal={sig}
                      onPaperBuy={handlePaperBuy}
                      isBought={activeSignalIds.has(sig.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl p-12 text-center text-slate-500 dark:text-slate-400 shadow-sm">
                  <p className="text-base font-semibold mb-1 text-slate-800 dark:text-slate-200">No Active Signals Matching Current Filter</p>
                  <p className="text-xs text-slate-500">
                    The background scanner is actively monitoring. Signals will trigger as soon as a candle setup completes.
                  </p>
                </div>
              )
            ) : (
              <SignalTable
                signals={filteredSignals}
                onPaperBuy={handlePaperBuy}
                activeSignalIds={activeSignalIds}
              />
            )}
          </>
        ) : (
          <PaperPortfolioView
            portfolio={state.paper_portfolio}
            onClosePosition={handleClosePosition}
            onToggleAutoTrade={handleToggleAutoTrade}
            onChangeLots={handleChangeLots}
            onResetPortfolio={handleResetPortfolio}
          />
        )}

        {/* Dashboard Capability Access Key Modal */}
        {capabilityModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in">
            <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-3xl max-w-md w-full p-6 shadow-2xl relative">
              <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-dark-700/60 mb-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-cyan-500/10 dark:bg-cyan-500/20 text-cyan-500 rounded-xl">
                    <KeyRound className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                      Dashboard Capability Key
                    </h3>
                    <p className="text-xs text-slate-500">Authorization required for mutations & streaming</p>
                  </div>
                </div>
                <button
                  onClick={() => setCapabilityModalOpen(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg"
                  title="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {capabilityError && (
                <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-500 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{capabilityError}</span>
                </div>
              )}

              {capabilitySuccess && (
                <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-500 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>Capability verified and session established!</span>
                </div>
              )}

              <form onSubmit={handleSaveCapability} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Access Token / Secret
                  </label>
                  <input
                    type="password"
                    value={capabilityInput}
                    onChange={(e) => setCapabilityInput(e.target.value)}
                    placeholder="Enter DASHBOARD_CAPABILITY token"
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-900 text-slate-800 dark:text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 font-mono"
                    required
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    Default: <code className="text-cyan-500 font-mono">bb-options-local-capability</code>
                  </p>
                </div>

                <div className="flex items-center justify-end gap-3 pt-3">
                  <button
                    type="button"
                    onClick={() => setCapabilityModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-dark-700 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 rounded-xl text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/30 transition flex items-center gap-1.5"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    Authorize Session
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200 dark:border-dark-800 py-4 text-center text-xs text-slate-500 bg-white dark:bg-dark-900/50">
        Bollinger Bands Options PRO • High-Probability Options Buying Engine • Forward-Testing Mode
      </footer>
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
