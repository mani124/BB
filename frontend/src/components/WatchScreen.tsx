import React, { useState } from 'react';
import type { PaperPosition, ScannerState, Signal } from '../types';
import { CompactStrip } from './PortfolioStrips';
import { IndexHeroRadar } from './IndexHeroRadar';
import { OpenPositionsPanel } from './OpenPositionsPanel';
import { TodaySummary } from './TodaySummary';
import { SetupFilterTabs } from './SetupFilterTabs';
import { SignalTable } from './SignalTable';
import { SignalDetails } from './SignalDetails';
import { WatchStatus } from './WatchStatus';
import type { StreamStatus } from './Header';
import type { DashboardTrade, DashboardWatch, WatchBook } from '../types/dashboard';
import { WatchCandidateList } from './WatchCandidateList';
import { WatchCandidateDetail } from './WatchCandidateDetail';

const SIGNALS_SHOWN = 12;

export interface WatchFilters {
  setup: string;
  optionType: string;
  instrumentType: string;
  timeframe: string;
}

interface WatchScreenProps {
  dashboardWatch?: DashboardWatch | null;
  state: ScannerState;
  loaded: boolean;
  wsConnected: boolean;
  stream: StreamStatus;
  filters: WatchFilters;
  onFilters: (next: Partial<WatchFilters>) => void;
  filteredSignals: Signal[];
  closedTrades: PaperPosition[];
  activeSignalIds: Set<string>;
  onPaperBuy: (signal: Signal) => void;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  trades?: DashboardTrade[];
  onOpenTrade?: (id: string) => void;
}

/** Live screen: one header band, positions and today's tally on the left, signals on the right. */
export const WatchScreen: React.FC<WatchScreenProps> = ({
  dashboardWatch, state, loaded, wsConnected, stream, filters, onFilters, filteredSignals, closedTrades, activeSignalIds,
  onPaperBuy, onClosePosition, onToggleAutoTrade, onChangeLots, trades = [], onOpenTrade,
}) => {
  const [showAll, setShowAll] = useState(false);
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [sortBy, setSortBy] = useState<'newest' | 'symbol' | 'setup'>('newest');
  const [bookFilter, setBookFilter] = useState<'all' | WatchBook>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'actionable' | 'waiting'>('all');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [mainView, setMainView] = useState<'candidates' | 'signals'>('signals');
  // Confirmed signals first (stable), short list by default.
  const sorted = [...filteredSignals].sort((x, y) => {
    const confirmation = Number(y.is_confirmed !== false) - Number(x.is_confirmed !== false);
    if (confirmation) return confirmation;
    if (sortBy === 'symbol') return x.symbol.localeCompare(y.symbol);
    if (sortBy === 'setup') return x.setup_type.localeCompare(y.setup_type);
    return y.timestamp.localeCompare(x.timestamp);
  });
  const shown = showAll ? sorted : sorted.slice(0, SIGNALS_SHOWN);
  const pf = state.paper_portfolio;
  const currentSelection = selectedSignal && state.signals.find((sig) => sig.id === selectedSignal.id);
  const confirmedCount = state.signals.filter((sig) => sig.is_confirmed !== false).length;

  // Candidates come from the recorded watch feed; without it the screen is simply the signals view.
  const candidates = (dashboardWatch?.candidates ?? [])
    .filter((candidate) => bookFilter === 'all' || candidate.book === bookFilter)
    .filter((candidate) => {
      const actionable = ['READY', 'CONFIRMED', 'SIGNAL'].includes(candidate.stage);
      return statusFilter === 'all' || (statusFilter === 'actionable' ? actionable : !actionable);
    })
    .sort((a, b) => {
      const priority = (stage: string) => stage === 'READY' || stage === 'CONFIRMED' || stage === 'SIGNAL' ? 0 : 1;
      return priority(a.stage) - priority(b.stage) || (b.observed_at || '').localeCompare(a.observed_at || '');
    });
  const selected = candidates.find((candidate) => candidate.id === selectedCandidateId) ?? candidates[0] ?? null;
  const signalId = selected?.book === 'paper' && selected.id.startsWith('paper:') ? selected.id.slice('paper:'.length) : null;
  const matchedTrade = signalId ? trades.find((trade) => trade.book === 'paper' && trade.signal_id === signalId) : null;
  const view = dashboardWatch ? mainView : 'signals';

  const positionsRail = (
    <div className="flex flex-col gap-3 lg:min-h-0">
      <OpenPositionsPanel
        compact
        positions={pf?.active_positions ?? []}
        onClosePosition={onClosePosition}
        headerActions={pf && (
          <>
            <button
              type="button"
              className={`desk-btn sm ${pf.auto_trade_enabled ? 'solid' : ''}`}
              aria-pressed={pf.auto_trade_enabled}
              onClick={() => onToggleAutoTrade(!pf.auto_trade_enabled)}
            >
              Auto-enter: {pf.auto_trade_enabled ? 'ON' : 'OFF'}
            </button>
            <div className="desk-seg" role="group" aria-label="Lot multiplier">
              {[2, 4, 6, 8, 10].map((l) => (
                <button key={l} type="button" aria-pressed={pf.default_lots === l} onClick={() => onChangeLots(l)}>
                  {l}x
                </button>
              ))}
            </div>
          </>
        )}
      />
      <TodaySummary trades={closedTrades} />
    </div>
  );

  const candidatesView = (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.3fr)] gap-3 lg:min-h-0 lg:flex-1">
      <section className="desk-pane min-h-0" aria-label="Watched candidates">
        <div className="desk-ph justify-between">
          <h2>{candidates.length} candidates</h2>
          <label className="text-xs desk-muted">Book filter <select className="desk-input ml-2" style={{ width: 'auto' }} value={bookFilter} onChange={(event) => setBookFilter(event.target.value as typeof bookFilter)}>
            <option value="all">All books</option><option value="paper">Main scanner</option><option value="setup16">Setup 16</option>
            <option value="cx">Commodities & FX</option><option value="earnings">Earnings</option>
          </select></label>
          <label className="text-xs desk-muted">Status filter <select className="desk-input ml-2" style={{ width: 'auto' }} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
            <option value="all">All states</option><option value="actionable">Ready / signaled</option><option value="waiting">Waiting / blocked</option>
          </select></label>
        </div>
        <div className="desk-scroll">
          <WatchCandidateList candidates={candidates} selectedId={selected?.id ?? null} onSelect={setSelectedCandidateId} />
        </div>
      </section>
      <div className="lg:overflow-y-auto min-h-0">
        <WatchCandidateDetail candidate={selected} tradeId={matchedTrade?.id} onOpenTrade={onOpenTrade} />
      </div>
    </div>
  );

  const signalsView = (
    <div className="desk-pane min-h-0 lg:flex-1" aria-labelledby="signals-title">
      <div className="desk-ph">
        <h2 id="signals-title" className={dashboardWatch ? 'sr-only' : undefined}>Active Strategy Signals</h2>
        <span className="desk-pill desk-num">{filteredSignals.length} active</span>
        <span className="text-xs desk-muted ml-auto">
          {wsConnected ? 'Real-time ticks' : (state.last_scan_seconds ? `Scanned (last scan ${state.last_scan_seconds.toFixed(1)}s)` : 'Scanned')} · confirm on candle close
        </span>
      </div>
      <div className="px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm" style={{ borderBottom: '1px solid var(--line)' }}>
        <span className="desk-label">Bias</span>
        <span
          className={`desk-pill ${state.market_bias === 'BULLISH' ? 'up' : state.market_bias === 'BEARISH' ? 'down' : ''}`}
          title={
            state.market_bias === 'BULLISH' ? 'PE stock options blocked'
              : state.market_bias === 'BEARISH' ? 'CE stock options blocked' : undefined
          }
        >
          {state.active_mode === 'closed' ? 'MARKET CLOSED' : state.market_bias || 'NEUTRAL'}
        </span>
        {Boolean(state.top_bullish?.length) && <span className="desk-label ml-2">Top CE</span>}
        {state.top_bullish?.map((sym) => (
          <span key={sym} className="desk-pill up desk-num" title="Top bullish (CE)">▲ {sym}</span>
        ))}
        {Boolean(state.top_bearish?.length) && <span className="desk-label ml-2">Top PE</span>}
        {state.top_bearish?.map((sym) => (
          <span key={sym} className="desk-pill down desk-num" title="Top bearish (PE)">▼ {sym}</span>
        ))}
      </div>
      <SetupFilterTabs
        compact
        selectedSetup={filters.setup}
        onSelectSetup={(v) => onFilters({ setup: v })}
        selectedOptionType={filters.optionType}
        onSelectOptionType={(v) => onFilters({ optionType: v })}
        selectedInstrumentType={filters.instrumentType}
        onSelectInstrumentType={(v) => onFilters({ instrumentType: v })}
        selectedTimeframe={filters.timeframe}
        onSelectTimeframe={(v) => onFilters({ timeframe: v })}
        totalSignals={filteredSignals.length}
      />
      <div className="px-4 py-2 flex items-center justify-between gap-3 text-sm" style={{ borderBottom: '1px solid var(--line)' }}>
        <span className="desk-muted">Confirmed first · inspect a signal for reasoning and price basis</span>
        <label className="flex items-center gap-2 whitespace-nowrap">
          <span className="desk-muted">Sort</span>
          <select className="desk-input" style={{ width: 'auto' }} value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
            <option value="newest">Newest</option>
            <option value="symbol">Symbol</option>
            <option value="setup">Setup</option>
          </select>
        </label>
      </div>
      <div className="desk-scroll" tabIndex={0} aria-label="Signals list">
        <SignalTable signals={shown} onInspect={setSelectedSignal} activeSignalIds={activeSignalIds} loading={!loaded} />
        {sorted.length > SIGNALS_SHOWN && (
          <button
            type="button"
            className="w-full py-3 text-sm font-semibold"
            style={{ color: 'var(--accent)' }}
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll ? 'Show fewer signals' : `Show all ${sorted.length} signals`}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <>
      <h1 className="sr-only">Watch</h1>
      {!dashboardWatch && <WatchStatus state={state} stream={stream} confirmedCount={confirmedCount} />}
      <div className="desk-panel desk-band overflow-hidden">
        <CompactStrip portfolio={pf} />
        <IndexHeroRadar radar={state.radar} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(340px,0.8fr)_minmax(0,1.5fr)] gap-3 lg:flex-1 lg:min-h-0">
        {positionsRail}
        <section className="desk-panel desk-pane min-h-0" aria-label="Scanner results">
          {dashboardWatch && (
            <div className="desk-subtabs px-2" role="group" aria-label="Scanner view">
              <button type="button" className="desk-subtab" aria-pressed={view === 'signals'} onClick={() => setMainView('signals')}>
                Signals <span className="desk-pill desk-num ml-1">{filteredSignals.length}</span>
              </button>
              <button type="button" className="desk-subtab" aria-pressed={view === 'candidates'} onClick={() => setMainView('candidates')}>
                What the scanners are watching <span className="desk-pill desk-num ml-1">{dashboardWatch.candidates.length}</span>
              </button>
            </div>
          )}
          {view === 'candidates' ? candidatesView : signalsView}
        </section>
      </div>
      {currentSelection && (
        <SignalDetails
          signal={currentSelection}
          onClose={() => setSelectedSignal(null)}
          onPaperBuy={onPaperBuy}
          isBought={activeSignalIds.has(currentSelection.id)}
        />
      )}
    </>
  );
};
