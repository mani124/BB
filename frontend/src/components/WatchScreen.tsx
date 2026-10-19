import React, { useState } from 'react';
import type { PaperPosition, ScannerState, Signal } from '../types';
import { CompactStrip } from './PortfolioStrips';
import { IndexHeroRadar } from './IndexHeroRadar';
import { OpenPositionsPanel } from './OpenPositionsPanel';
import { TodaySummary } from './TodaySummary';
import { SetupFilterTabs } from './SetupFilterTabs';
import { SignalTable } from './SignalTable';

const SIGNALS_SHOWN = 12;

export interface WatchFilters {
  setup: string;
  optionType: string;
  instrumentType: string;
  timeframe: string;
}

interface WatchScreenProps {
  state: ScannerState;
  loaded: boolean;
  wsConnected: boolean;
  filters: WatchFilters;
  onFilters: (next: Partial<WatchFilters>) => void;
  filteredSignals: Signal[];
  closedTrades: PaperPosition[];
  activeSignalIds: Set<string>;
  onPaperBuy: (signal: Signal) => void;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
}

/** Live screen: one header band, positions and today's tally on the left, signals on the right. */
export const WatchScreen: React.FC<WatchScreenProps> = ({
  state, loaded, wsConnected, filters, onFilters, filteredSignals, closedTrades, activeSignalIds,
  onPaperBuy, onClosePosition, onToggleAutoTrade, onChangeLots,
}) => {
  const [showAll, setShowAll] = useState(false);
  // Confirmed signals first (stable), short list by default.
  const sorted = [...filteredSignals].sort((x, y) => Number(y.is_confirmed !== false) - Number(x.is_confirmed !== false));
  const shown = showAll ? sorted : sorted.slice(0, SIGNALS_SHOWN);
  const pf = state.paper_portfolio;

  return (
    <>
      <div className="desk-panel desk-band overflow-hidden">
        <CompactStrip portfolio={pf} />
        <IndexHeroRadar radar={state.radar} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] lg:grid-rows-1 gap-3 lg:flex-1 lg:min-h-0">
        <div className="flex flex-col gap-3 min-h-0">
          <OpenPositionsPanel
            compact
            positions={pf?.active_positions ?? []}
            onClosePosition={onClosePosition}
            headerActions={pf && (
              <>
                <button
                  type="button"
                  className={`desk-btn sm ${pf.auto_trade_enabled ? 'accent' : ''}`}
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

        <section className="desk-panel desk-pane" aria-labelledby="signals-title">
          <div className="desk-ph">
            <h2 id="signals-title">Active Strategy Signals</h2>
            <span className="desk-pill desk-num">{filteredSignals.length} active</span>
            <span className="text-xs desk-muted ml-auto">
              {wsConnected ? 'Real-time ticks' : (state.last_scan_seconds ? `Scanned (last scan ${state.last_scan_seconds.toFixed(1)}s)` : 'Scanned')} · confirm on candle close
            </span>
          </div>
          <div className="px-3.5 py-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs" style={{ borderBottom: '1px solid var(--line)' }}>
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
          <div className="desk-scroll" tabIndex={0} aria-label="Signals list">
            <SignalTable signals={shown} onPaperBuy={onPaperBuy} activeSignalIds={activeSignalIds} loading={!loaded} />
            {sorted.length > SIGNALS_SHOWN && (
              <button
                type="button"
                className="w-full py-2 text-sm font-medium"
                style={{ color: 'var(--accent)' }}
                onClick={() => setShowAll((v) => !v)}
              >
                {showAll ? 'Show fewer signals' : `Show all ${sorted.length} signals`}
              </button>
            )}
          </div>
        </section>
      </div>
    </>
  );
};
