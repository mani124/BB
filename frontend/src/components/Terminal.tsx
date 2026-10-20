import React, { useState } from 'react';
import { Briefcase, Crosshair, ListFilter, Table2 } from 'lucide-react';
import type { PaperPosition, ScannerState, Signal } from '../types';
import type { DashboardCandidate } from '../types/dashboard';
import { SignalsPane } from './SignalsPane';
import { FocusPane, type Selection } from './FocusPane';
import { PositionsPane } from './PositionsPane';
import { Blotter, FULL_HEIGHT_TABS, type BlotterProps, type BlotterTab } from './Blotter';
import type { WatchFilters } from './SignalsPane';
import type { DashboardWatch } from '../types/dashboard';

type Pane = 'signals' | 'focus' | 'positions' | 'blotter';

export interface TerminalProps extends Omit<BlotterProps,
  'tab' | 'onTab' | 'expanded' | 'onToggleExpanded' | 'selectedSignalId' | 'selectedPositionId' | 'onSelectSignal' | 'onSelectPosition' | 'tradeId' | 'onOpenTrade' | 'signals' | 'signalsLoaded'> {
  state: ScannerState;
  loaded: boolean;
  wsConnected: boolean;
  dashboardWatch: DashboardWatch | null;
  filters: WatchFilters;
  onFilters: (next: Partial<WatchFilters>) => void;
  filteredSignals: Signal[];
  onPaperBuy: (signal: Signal) => void;
}

const panel = 'desk-panel flex-col min-h-0 overflow-hidden';

/** The whole product on one screen: signals, the selected thing, positions, and a blotter of every table below. */
export const Terminal: React.FC<TerminalProps> = (props) => {
  const { state, loaded, wsConnected, dashboardWatch, filters, onFilters, filteredSignals, activeSignalIds, onPaperBuy, onClosePosition, ...blotterRest } = props;
  const [chosen, setChosen] = useState<Selection>(null);
  const [dismissed, setDismissed] = useState(false);
  const [tab, setTabState] = useState<BlotterTab>('positions');
  const [expanded, setExpanded] = useState(false);
  const [pane, setPane] = useState<Pane>('signals');
  const [tradeId, setTradeId] = useState<string | null>(null);

  const portfolio = state.paper_portfolio;
  // With nothing chosen the centre shows the first open position, else the newest signal, so it is never an empty box.
  const firstPosition = portfolio?.active_positions?.[0];
  const firstSignal = filteredSignals[0];
  const selection: Selection = chosen ?? (dismissed ? null : firstPosition ? { kind: 'position', id: firstPosition.id } : firstSignal ? { kind: 'signal', id: firstSignal.id } : null);
  // Selections are looked up by id, so a refreshed snapshot never leaves a stale copy on screen.
  const signal = selection?.kind === 'signal' ? state.signals.find((s) => s.id === selection.id) ?? null : null;
  const position = selection?.kind === 'position' ? portfolio?.active_positions?.find((x) => x.id === selection.id) ?? null : null;
  const candidate: DashboardCandidate | null = selection?.kind === 'candidate' ? dashboardWatch?.candidates.find((c) => c.id === selection.id) ?? null : null;

  const setTab = (next: BlotterTab) => { setTabState(next); setExpanded(FULL_HEIGHT_TABS.includes(next)); setPane('blotter'); };
  const select = (next: Selection) => { setChosen(next); setDismissed(false); setPane('focus'); if (expanded) setExpanded(false); };
  const openTrade = (id: string) => { setTradeId(id); setTabState('trades'); setExpanded(true); setPane('blotter'); };
  const selectSignal = (s: Signal) => select({ kind: 'signal', id: s.id });
  const selectPosition = (x: PaperPosition) => select({ kind: 'position', id: x.id });

  const show = (name: Pane) => (pane === name ? 'flex' : 'hidden lg:flex');
  const bar: { id: Pane; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'signals', label: 'Signals', Icon: ListFilter },
    { id: 'focus', label: 'Detail', Icon: Crosshair },
    { id: 'positions', label: 'Positions', Icon: Briefcase },
    { id: 'blotter', label: 'Tables', Icon: Table2 },
  ];

  return (
    <div className="flex flex-col gap-2 flex-1 min-h-0">
      <div className={`grid gap-2 lg:flex-1 lg:min-h-0 lg:grid-cols-[19rem_minmax(0,1fr)_20rem] ${expanded ? 'lg:hidden' : ''} ${pane === 'blotter' ? 'hidden lg:grid' : ''}`}>
        <section className={`${panel} ${show('signals')} min-h-[24rem] lg:min-h-0`} aria-labelledby="signals-title">
          <SignalsPane state={state} signals={filteredSignals} loaded={loaded} activeSignalIds={activeSignalIds} wsConnected={wsConnected}
            selectedSignalId={signal?.id ?? null} onSelectSignal={selectSignal}
            filters={filters} onFilters={onFilters} dashboardWatch={dashboardWatch}
            selectedCandidateId={candidate?.id ?? null} onSelectCandidate={(id) => select({ kind: 'candidate', id })} />
        </section>
        <section className={`${panel} ${show('focus')} min-h-[24rem] lg:min-h-0`} aria-label="Selected instrument">
          <FocusPane signal={signal} position={position} candidate={candidate} trades={props.trades}
            isBought={signal ? activeSignalIds.has(signal.id) : false} onPaperBuy={onPaperBuy} onClosePosition={onClosePosition}
            onOpenTrade={openTrade} onClear={() => { setChosen(null); setDismissed(true); }} />
        </section>
        <section className={`${panel} ${show('positions')} min-h-[24rem] lg:min-h-0`}>
          <PositionsPane portfolio={portfolio} closedTrades={props.closedTrades} selectedId={position?.id ?? null} onSelect={selectPosition}
            onClosePosition={onClosePosition} onToggleAutoTrade={props.onToggleAutoTrade} onChangeLots={props.onChangeLots} />
        </section>
      </div>
      <section className={`${panel} ${pane === 'blotter' ? 'flex' : 'hidden lg:flex'} ${expanded ? 'lg:flex-1' : 'lg:h-[32vh] lg:shrink-0'} min-h-[24rem] lg:min-h-0`} aria-label="Tables">
        <Blotter {...blotterRest} onClosePosition={onClosePosition} activeSignalIds={activeSignalIds} signals={filteredSignals} signalsLoaded={loaded}
          tab={tab} onTab={setTab} expanded={expanded} onToggleExpanded={() => setExpanded((v) => !v)}
          selectedSignalId={signal?.id ?? null} selectedPositionId={position?.id ?? null}
          onSelectSignal={selectSignal} onSelectPosition={selectPosition} tradeId={tradeId} onOpenTrade={openTrade} />
      </section>
      <nav className="desk-panebar lg:hidden" aria-label="Screen sections">
        {bar.map(({ id, label, Icon }) => (
          <button key={id} type="button" className="desk-navtab" aria-current={pane === id ? 'page' : undefined} onClick={() => setPane(id)}>
            <Icon className="h-[18px] w-[18px]" aria-hidden /><span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
};
