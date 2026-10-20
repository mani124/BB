import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { PaperPortfolio, PaperPosition, SetupMode, Signal } from '../types';
import type { DashboardChart, DashboardSession, DashboardSource, DashboardTrade, DashboardTradeDetail } from '../types/dashboard';
import { Tabs } from './Tabs';
import { SignalTable } from './SignalTable';
import { TradesScreen } from './TradesScreen';
import { SessionScreen } from './SessionScreen';
import { ReviewScreen } from './ReviewScreen';
import { Setup16Screen } from './Setup16Screen';
import { CxScreen } from './CxScreen';
import { EarningsPanel } from './EarningsPanel';
import { SettingsPanel } from './SettingsPanel';
import { ControlScreen, type ControlView } from './ControlScreen';
import { formatCurrency, pnlClass } from './format';
import { setupCode } from './setupCode';

export type BlotterTab = 'positions' | 'signals' | 'trades' | 'session' | 'review' | 'setup16' | 'cx' | 'earnings' | 'settings' | 'control';

/** Tabs that need the whole workspace; the terminal collapses to give them room. */
export const FULL_HEIGHT_TABS: BlotterTab[] = ['trades', 'session', 'review', 'setup16', 'cx', 'earnings', 'settings', 'control'];

const BOOK_OF: Partial<Record<BlotterTab, DashboardSource['book']>> = { setup16: 'setup16', cx: 'cx', earnings: 'earnings' };

export interface BlotterProps {
  tab: BlotterTab;
  onTab: (tab: BlotterTab) => void;
  expanded: boolean;
  onToggleExpanded: () => void;
  portfolio?: PaperPortfolio;
  closedTrades: PaperPosition[];
  signals: Signal[];
  signalsLoaded: boolean;
  activeSignalIds: Set<string>;
  selectedSignalId: string | null;
  selectedPositionId: string | null;
  onSelectSignal: (signal: Signal) => void;
  onSelectPosition: (position: PaperPosition) => void;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onChangeSetupMode: (setup: string, mode: SetupMode) => void;
  onResetPortfolio: () => void;
  onKillSwitch: (engage: boolean) => void;
  onScanNow: () => void;
  onOpenAccessKey: () => void;
  sources: DashboardSource[];
  trades: DashboardTrade[];
  tradesError: string | null;
  loadTradeDetail: (trade: DashboardTrade) => Promise<DashboardTradeDetail>;
  loadTradeChart: (trade: DashboardTrade) => Promise<DashboardChart>;
  onClosePaperTrade: (sourceId: string) => Promise<void>;
  onRefreshTrades: () => void | Promise<void>;
  tradeId: string | null;
  onOpenTrade: (id: string) => void;
  loadSession: (day: string) => Promise<DashboardSession>;
  sessionDay: string;
}

const PositionsTable: React.FC<Pick<BlotterProps, 'portfolio' | 'selectedPositionId' | 'onSelectPosition' | 'onClosePosition'>> = ({ portfolio, selectedPositionId, onSelectPosition, onClosePosition }) => {
  const positions = portfolio?.active_positions ?? [];
  if (!portfolio) return <div className="p-4 text-sm desk-muted" role="status">Loading portfolio…</div>;
  if (positions.length === 0) return <div className="p-6 text-center text-sm desk-muted">No open paper positions.</div>;
  return (
    <div className="overflow-x-auto"><table className="desk-table" aria-label="Open positions">
      <thead><tr>
        <th scope="col">Instrument</th><th scope="col">Setup</th><th scope="col">In</th><th scope="col" className="r">Qty</th><th scope="col" className="r">Entry</th><th scope="col" className="r">LTP</th>
        <th scope="col" className="r">SL</th><th scope="col" className="r">Target</th><th scope="col" className="r">Booked</th><th scope="col" className="r">P&L</th><th scope="col" className="r">Net if closed</th><th scope="col"><span className="sr-only">Actions</span></th>
      </tr></thead>
      <tbody>{positions.map((p) => {
        const t1 = p.status === 'TARGET_1';
        return (
          <tr key={p.id} className={selectedPositionId === p.id ? 'desk-selected cursor-pointer' : 'cursor-pointer'} onClick={() => onSelectPosition(p)}>
            <td><span className="desk-sym">{p.strike_symbol}</span>{' '}<span className={`desk-side ${p.option_type === 'CE' ? 'ce' : 'pe'}`}>{p.option_type}</span>{t1 && <span className="desk-pill up ml-1">T1 hit</span>}</td>
            <td><span className="desk-code">{setupCode(p.setup_type)}</span></td>
            <td className="desk-num">{p.entry_time}</td>
            <td className="r desk-num">{p.quantity}</td>
            <td className="r desk-num">{p.option_entry.toFixed(1)}</td>
            <td className="r desk-num">{p.current_option_price.toFixed(1)}</td>
            <td className="r desk-num desk-down">{p.option_sl.toFixed(1)}</td>
            <td className="r desk-num desk-up">{(t1 ? p.option_target_2 : p.option_target_1).toFixed(1)}</td>
            <td className={`r desk-num ${pnlClass(p.booked_pnl_rupees ?? 0)}`}>{formatCurrency(p.booked_pnl_rupees ?? 0, true)}</td>
            <td className={`r desk-num font-semibold ${pnlClass(p.pnl_rupees)}`}>{formatCurrency(p.pnl_rupees, true)}</td>
            <td className={`r desk-num ${p.est_net_pnl === undefined ? 'desk-muted' : pnlClass(p.est_net_pnl)}`}>{p.est_net_pnl === undefined ? 'n/a' : formatCurrency(p.est_net_pnl, true)}</td>
            <td className="r"><button type="button" className="desk-btn sm danger" aria-label={`Close ${p.strike_symbol} from table`} onClick={(e) => { e.stopPropagation(); onClosePosition(p.id); }}>Close</button></td>
          </tr>
        );
      })}</tbody></table></div>
  );
};

/** The blotter: every table and workspace the terminal has, behind one row of tabs. */
export const Blotter: React.FC<BlotterProps> = (p) => {
  const openCount = p.portfolio?.active_positions?.length;
  const health = (tab: BlotterTab) => {
    const book = BOOK_OF[tab];
    return book ? p.sources.find((s) => s.book === book) : undefined;
  };
  const items: { id: BlotterTab; label: string; count?: number }[] = [
    { id: 'positions', label: 'Positions', count: openCount },
    { id: 'signals', label: 'Signals', count: p.signals.length },
    { id: 'trades', label: 'Trades' },
    { id: 'session', label: 'Session' },
    { id: 'review', label: 'Review' },
    { id: 'setup16', label: 'Setup 16' },
    { id: 'cx', label: 'Commodities & FX' },
    { id: 'earnings', label: 'Earnings' },
    { id: 'settings', label: 'Settings' },
    { id: 'control', label: 'Control' },
  ];
  const openView = (view: ControlView) => p.onTab(view === 'legacy-review' ? 'review' : view);

  let body: React.ReactNode;
  switch (p.tab) {
    case 'positions': body = <PositionsTable {...p} />; break;
    case 'signals':
      body = <div><SignalTable signals={p.signals} onInspect={p.onSelectSignal} activeSignalIds={p.activeSignalIds} loading={!p.signalsLoaded} selectedId={p.selectedSignalId} /></div>;
      break;
    case 'trades':
      body = (<>
        {p.tradesError && <p role="alert" className="desk-alert m-2">{p.tradesError}</p>}
        <TradesScreen key={p.tradeId ?? 'none'} trades={p.trades} loadDetail={p.loadTradeDetail} loadChart={p.loadTradeChart}
          onClosePaper={p.onClosePaperTrade} onRefresh={p.onRefreshTrades} initialTradeId={p.tradeId} />
      </>);
      break;
    case 'session':
      body = <SessionScreen initialDay={p.sessionDay} loadSession={p.loadSession} onOpenTrade={p.onOpenTrade} onOpenReview={() => p.onTab('review')} />;
      break;
    case 'review':
      body = <ReviewScreen portfolio={p.portfolio} closedTrades={p.closedTrades} onClosePosition={p.onClosePosition} onToggleAutoTrade={p.onToggleAutoTrade}
        onChangeLots={p.onChangeLots} onChangeSetupMode={p.onChangeSetupMode} onResetPortfolio={p.onResetPortfolio} />;
      break;
    case 'setup16': body = <Setup16Screen />; break;
    case 'cx': body = <CxScreen />; break;
    case 'earnings': body = <EarningsPanel />; break;
    case 'settings': body = <SettingsPanel />; break;
    case 'control':
      body = <ControlScreen portfolio={p.portfolio} risk={p.portfolio?.risk} onPause={p.onToggleAutoTrade} onKillSwitch={p.onKillSwitch}
        onOpenView={openView} onScanNow={p.onScanNow} onOpenAccessKey={p.onOpenAccessKey} />;
      break;
  }

  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="flex items-stretch" style={{ borderBottom: '1px solid var(--line-strong)', background: 'var(--alt)' }}>
        <Tabs<BlotterTab>
          idPrefix="blotter" label="Blotter" className="flex flex-1 min-w-0 overflow-x-auto" tabClassName="desk-subtab whitespace-nowrap"
          value={p.tab} onChange={p.onTab}
          items={items.map((t) => {
            const h = health(t.id);
            const attention = h && (h.state === 'error' || h.state === 'stale');
            return { id: t.id, name: t.label, label: <>{t.label}{t.count != null && <span className="desk-pill desk-num ml-1">{t.count}</span>}{attention && <span className={`desk-pill ${h.state === 'error' ? 'down' : 'warn'} ml-1`} title={h.message || undefined}>{h.state}</span>}</> };
          })}
        />
        <button type="button" className="desk-btn sm m-1 hidden lg:inline-flex" aria-pressed={p.expanded} onClick={p.onToggleExpanded}
          aria-label={p.expanded ? 'Show the terminal again' : 'Give the table the whole workspace'} title={p.expanded ? 'Show signals, chart and positions again' : 'Use the whole workspace for this table'}>
          {p.expanded ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronUp className="h-4 w-4" aria-hidden />}
          {p.expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      <div id="blotter-panel" role="tabpanel" aria-labelledby={`blotter-tab-${p.tab}`} className="flex-1 min-h-0 overflow-y-auto flex flex-col">
        {body}
      </div>
    </div>
  );
};
