import React, { useState, useEffect } from 'react';
import { DhanAuthProvider } from './context/DhanAuthContext';
import { Header } from './components/Header';
import { IndexHeroRadar } from './components/IndexHeroRadar';
import { SetupFilterTabs } from './components/SetupFilterTabs';
import { SignalCard } from './components/SignalCard';
import { SignalTable } from './components/SignalTable';
import { ScannerState, Signal } from './types';
import { LayoutGrid, Table } from 'lucide-react';

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

  const [selectedSetup, setSelectedSetup] = useState<string>('ALL');
  const [selectedOptionType, setSelectedOptionType] = useState<string>('ALL');
  const [selectedInstrumentType, setSelectedInstrumentType] = useState<string>('ALL');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');

  // Connect to SSE stream on mount
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimeout: any = null;

    const connectSSE = () => {
      eventSource = new EventSource('/api/signals/stream');

      eventSource.onmessage = (event) => {
        try {
          const data: ScannerState = JSON.parse(event.data);
          setState(data);
        } catch (err) {
          console.error('Failed to parse SSE payload', err);
        }
      };

      eventSource.onerror = () => {
        eventSource?.close();
        // Reconnect after 3 seconds
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

  // Filter signals
  const filteredSignals = state.signals.filter((sig) => {
    // Setup filter
    if (selectedSetup !== 'ALL' && sig.setup_type !== selectedSetup) {
      return false;
    }
    // Option type (CE/PE)
    if (selectedOptionType !== 'ALL' && sig.option_type !== selectedOptionType) {
      return false;
    }
    // Instrument type
    const isIndex = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX'].includes(sig.symbol);
    if (selectedInstrumentType === 'INDEX' && !isIndex) return false;
    if (selectedInstrumentType === 'STOCK' && isIndex) return false;
    // Timeframe
    if (selectedTimeframe !== 'ALL' && sig.timeframe !== selectedTimeframe) {
      return false;
    }
    return true;
  });

  return (
    <div className="min-h-screen flex flex-col bg-[#0B0E14] text-slate-100">
      <Header
        activeMode={state.active_mode}
        scanCycleCount={state.scan_cycle_count}
        lastScanTime={state.last_scan_time}
        isScanning={state.is_scanning}
        scanProgress={state.scan_progress}
        onScanNow={handleScanNow}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
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

          <div className="flex items-center gap-1 bg-dark-800 border border-dark-700 rounded-xl p-1">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1.5 rounded-lg transition ${
                viewMode === 'grid' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Card Grid View"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded-lg transition ${
                viewMode === 'table' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-slate-200'
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
                <SignalCard key={sig.id} signal={sig} />
              ))}
            </div>
          ) : (
            <div className="bg-dark-800 border border-dark-700 rounded-2xl p-12 text-center text-slate-400">
              <p className="text-base font-semibold mb-1">No Active Signals Matching Current Filter</p>
              <p className="text-xs text-slate-500">
                The background scanner is actively monitoring. Signals will trigger as soon as a candle setup completes.
              </p>
            </div>
          )
        ) : (
          <SignalTable signals={filteredSignals} />
        )}
      </main>

      <footer className="border-t border-dark-800 py-4 text-center text-xs text-slate-500">
        Bollinger Bands Options PRO • High-Probability Options Buying Engine • Forward-Testing Mode
      </footer>
    </div>
  );
};

export default function App() {
  return (
    <DhanAuthProvider>
      <DashboardContent />
    </DhanAuthProvider>
  );
}
