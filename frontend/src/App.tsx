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
import { LayoutGrid, Table, Radio, Briefcase } from 'lucide-react';

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
  const { connect } = useDhanAuth();
  const reconnectingRef = React.useRef(false);

  // Fetch initial snapshot and connect to SSE stream on mount
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimeout: any = null;

    // Fast initial fetch so UI renders immediately
    const fetchSnapshot = async () => {
      try {
        const res = await fetch('/api/signals');
        if (res.ok) {
          const data = await res.json();
          setState((prev) => ({ ...prev, ...data }));
          if (data.active_mode === 'demo' && !reconnectingRef.current) {
            const savedId = localStorage.getItem('dhan_client_id');
            const savedToken = localStorage.getItem('dhan_access_token');
            if (savedId && savedToken) {
              reconnectingRef.current = true;
              connect(savedId, savedToken).finally(() => {
                setTimeout(() => { reconnectingRef.current = false; }, 15000);
              });
            }
          }
        }
      } catch (e) {
        // SSE will hydrate state
      }
    };
    fetchSnapshot();

    const connectSSE = () => {
      eventSource = new EventSource('/api/signals/stream');

      eventSource.onmessage = (event) => {
        try {
          const data: ScannerState = JSON.parse(event.data);
          setState(data);
          if (data.active_mode === 'demo' && !reconnectingRef.current) {
            const savedId = localStorage.getItem('dhan_client_id');
            const savedToken = localStorage.getItem('dhan_access_token');
            if (savedId && savedToken) {
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
        reconnectTimeout = setTimeout(connectSSE, 3000);
      };
    };

    connectSSE();

    return () => {
      eventSource?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const handleScanNow = async () => {
    try {
      await fetch('/api/signals/scan-now', { method: 'POST' });
    } catch (e) {
      console.error('Manual scan failed', e);
    }
  };

  // Paper trading actions
  const handlePaperBuy = async (signal: Signal) => {
    try {
      const res = await fetch('/api/paper/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal, lots: state.paper_portfolio?.default_lots || 2 }),
      });
      if (res.ok) {
        // Refresh portfolio immediately
        const portRes = await fetch('/api/paper/portfolio');
        if (portRes.ok) {
          const portData = await portRes.json();
          setState((prev) => ({ ...prev, paper_portfolio: portData }));
        }
      }
    } catch (e) {
      console.error('Paper trade failed', e);
    }
  };

  const handleClosePosition = async (id: string) => {
    try {
      await fetch(`/api/paper/close/${id}`, { method: 'POST' });
      const portRes = await fetch('/api/paper/portfolio');
      if (portRes.ok) {
        const portData = await portRes.json();
        setState((prev) => ({ ...prev, paper_portfolio: portData }));
      }
    } catch (e) {
      console.error('Failed to close position', e);
    }
  };

  const handleToggleAutoTrade = async (enabled: boolean) => {
    try {
      const res = await fetch('/api/paper/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_trade_enabled: enabled }),
      });
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
      const res = await fetch('/api/paper/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_lots: lots }),
      });
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
      await fetch('/api/paper/reset', { method: 'POST' });
      const portRes = await fetch('/api/paper/portfolio');
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
    if (selectedSetup !== 'ALL' && sig.setup_type !== selectedSetup) return false;
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
      />

      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
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
          </div>

          <div className="text-xs text-slate-500 dark:text-slate-400">
            {activeTab === 'scanner' ? (
              <span>Signals update in real-time on every candle closure</span>
            ) : (
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                Auto-evaluates TP/SL every 8 seconds
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
                  Auto-refreshed every ~8s
                </span>
              </div>
              <IndexHeroRadar radar={state.radar} />
            </div>

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
