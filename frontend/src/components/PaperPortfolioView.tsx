import React, { useState, useEffect } from 'react';
import { PaperPortfolio, PaperPosition, SetupMode } from '../types';
import { RefreshCcw, Power, Receipt, LineChart } from 'lucide-react';
import { PositionChartModal } from './PositionChartModal';
import { setupCode } from './setupCode';
import { CostPanel } from './CostPanel';
import { isIndexSymbol } from './instruments';
import { SetupStatsPanel } from './SetupStatsPanel';
import { INR, formatCurrency, pnlClass, liveTrades, shortTime } from './format';
import { formatTradeSpan, summarizeTrades } from './tradeUtils';
import { OpenPositionsPanel } from './OpenPositionsPanel';
import { PortfolioStrip } from './PortfolioStrips';
import { ExitReason, TradeDrawer } from './TradeParts';
import { ReceiptModal } from './ReceiptModal';

// Re-exported so existing imports (App, tests) keep working after the split into smaller files.
export { formatTradeSpan, summarizeTrades } from './tradeUtils';
export { formatCurrency, liveTrades } from './format';
export { PortfolioStrip, CompactStrip } from './PortfolioStrips';
export { OpenPositionsPanel } from './OpenPositionsPanel';
export { exitReasonLabel } from './TradeParts';

interface PaperPortfolioViewProps {
  portfolio?: PaperPortfolio;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onChangeSetupMode?: (setup: string, mode: SetupMode) => void;
  onResetPortfolio: () => void;
  hideStrip?: boolean;
  /** Which part of the review to show; 'all' (default) is the original long page. */
  view?: 'all' | 'today' | 'trades' | 'setups' | 'costs';
}

const KIND_FILTER_OPTIONS = [
  { id: 'ALL', label: 'All' },
  { id: 'INDEX', label: 'Index' },
  { id: 'STOCK', label: 'Stock' },
];
const matchKind = (t: PaperPosition, kind: string): boolean =>
  kind === 'ALL' || (kind === 'INDEX') === isIndexSymbol(t.symbol);

const SETUP_FILTER_OPTIONS = [
  { id: 'ALL', label: 'All setups' },
  { id: 'SETUP_1', label: 'S1 Squeeze' },
  { id: 'SETUP_2', label: 'S2 Walking Bands' },
  { id: 'SETUP_3', label: 'S3 W/M Reversal' },
  { id: 'SETUP_4', label: 'S4 9:30 ORB' },
  { id: 'SETUP_5', label: 'S5 Option Chart' },
  { id: 'SETUP_6', label: 'S6 Pin Bar' },
  { id: 'SETUP_7', label: 'S7 Inside Bar' },
  { id: 'SETUP_8', label: 'S8 Climax Divergence' },
  { id: 'SETUP_9', label: 'S9 Rel. Strength' },
  { id: 'SETUP_10', label: 'S10 Straddle Squeeze' },
  { id: 'SETUP_11', label: 'S11 Filtered Scalp' },
  { id: 'SETUP_12', label: 'S12 ADX EMA Cross' },
  { id: 'SETUP_13', label: 'S13 Option VWAP' },
  { id: 'SETUP_14', label: 'S14 OI Wall Bounce' },
  { id: 'SETUP_20', label: 'S20 T315 EMA Cross' },
  { id: 'SETUP_21', label: 'S21 T315-F 3m' },
  { id: 'SETUP_22', label: 'S22 T315-F 5m' },
  { id: 'SETUP_23', label: 'S23 T315-F 5m wide' },
];

const matchSetup = (tradeSetup: string | undefined, filterId: string) => {
  if (filterId === 'ALL') return true;
  if (!tradeSetup) return false;
  const s = tradeSetup.toUpperCase();
  // A numbered label ('SETUP 1', 'SETUP_10_...') decides on its number so S1 never matches S10.
  const num = s.match(/SETUP[_ ](\d+)/)?.[1];
  if (num) return `SETUP_${num}` === filterId;
  if (filterId === 'SETUP_1') {
    return s.includes('SETUP_1') || s.includes('SETUP 1') || s.includes('SQUEEZE');
  }
  if (filterId === 'SETUP_2') {
    return s.includes('SETUP_2') || s.includes('SETUP 2') || s.includes('WALKING');
  }
  if (filterId === 'SETUP_3') {
    return s.includes('SETUP_3') || s.includes('SETUP 3') || s.includes('REVERSAL') || s.includes('W/M');
  }
  if (filterId === 'SETUP_4') {
    return s.includes('SETUP_4') || s.includes('SETUP 4') || s.includes('ORB') || s.includes('OPENING RANGE');
  }
  if (filterId === 'SETUP_5') {
    return s.includes('SETUP_5') || s.includes('SETUP 5') || s.includes('OPTION');
  }
  if (filterId === 'SETUP_6') {
    return s.includes('SETUP_6') || s.includes('SETUP 6') || s.includes('PINBAR') || s.includes('PIN BAR') || s.includes('PIN_BAR');
  }
  if (filterId === 'SETUP_7') {
    return s.includes('SETUP_7') || s.includes('SETUP 7') || s.includes('INSIDE_BAR') || s.includes('INSIDE BAR');
  }
  if (filterId === 'SETUP_8') {
    return s.includes('SETUP_8') || s.includes('SETUP 8') || s.includes('DIVERGENCE') || s.includes('CLIMAX');
  }
  if (filterId === 'SETUP_9') {
    return s.includes('SETUP_9') || s.includes('SETUP 9') || s.includes('RELATIVE');
  }
  return false;
};

/* ---------- Journal helpers ---------- */
const tradeDay = (t: PaperPosition): string =>
  (t.exit_datetime ?? t.entry_datetime ?? '').slice(0, 10) || 'Undated';

const dayLabel = (iso: string): string => {
  if (iso === 'Undated') return iso;
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });
};

const DAYS_SHOWN = 5;
const PAGE_SIZE = 25;

const SETUP_SWITCH_ROWS: { key: string; label: string; perIndex?: boolean }[] = [
  { key: '1', label: 'Setup 1 · BB Squeeze' },
  { key: '2', label: 'Setup 2 · Walking the Bands' },
  { key: '3', label: 'Setup 3 · W/M Reversal' },
  { key: '4', label: 'Setup 4 · 9:30 ORB' },
  { key: '5', label: 'Setup 5 · Option Chart Scalp' },
  { key: '6', label: 'Setup 6 · Pin Bar Snapback' },
  { key: '7', label: 'Setup 7 · Inside Bar Snapback' },
  { key: '8', label: 'Setup 8 · Divergence Fade' },
  { key: '9', label: 'Setup 9 · Relative Strength' },
  { key: '10', label: 'Setup 10 · Straddle Squeeze' },
  { key: '11', label: 'Setup 11 · Filtered Option Scalp' },
  { key: '12', label: 'Setup 12 · ADX EMA Cross' },
  { key: '13', label: 'Setup 13 · Option VWAP Reclaim' },
  { key: '14', label: 'Setup 14 · OI Wall Bounce' },
  { key: '20', label: 'Setup 20 · T315 EMA 3/15 Cross' },
  { key: '21', label: 'Setup 21 · T315-F 3m', perIndex: true },
  { key: '22', label: 'Setup 22 · T315-F 5m', perIndex: true },
  { key: '23', label: 'Setup 23 · T315-F 5m wide', perIndex: true },
];

// The T315-F setups also run on one index only, so each can be switched on for Nifty or Bank Nifty independently.
const INDEX_MODE_OPTIONS: { mode: SetupMode; label: string; title: string }[] = [
  { mode: 'off', label: 'Off', title: 'Never auto-enter this setup' },
  { mode: 'nifty', label: 'Nifty', title: 'Auto-enter on Nifty 50 only' },
  { mode: 'banknifty', label: 'Bank Nifty', title: 'Auto-enter on Nifty Bank only' },
  { mode: 'index', label: 'Both', title: 'Auto-enter on Nifty 50 and Nifty Bank' },
];

const SETUP_MODE_OPTIONS: { mode: SetupMode; label: string; title: string }[] = [
  { mode: 'off', label: 'Off', title: 'Never auto-enter this setup' },
  { mode: 'index', label: 'Index', title: 'Auto-enter on indices only' },
  { mode: 'stocks', label: 'Stocks', title: 'Auto-enter on stocks only' },
  { mode: 'all', label: 'All', title: 'Auto-enter on indices and stocks' },
];

export const PaperPortfolioView: React.FC<PaperPortfolioViewProps> = ({
  portfolio,
  onClosePosition,
  onToggleAutoTrade,
  onChangeLots,
  onChangeSetupMode,
  onResetPortfolio,
  hideStrip = false,
  view = 'all',
}) => {
  const show = (...v: string[]) => view === 'all' || v.includes(view);
  const [page, setPage] = useState(0);
  const [drawerTrade, setDrawerTrade] = useState<PaperPosition | null>(null);
  const [selectedSetupFilter, setSelectedSetupFilter] = useState<string>('ALL');
  const [selectedKindFilter, setSelectedKindFilter] = useState<string>('ALL');
  useEffect(() => { setPage(0); }, [selectedSetupFilter, selectedKindFilter]);
  const [selectedTradeForReceipt, setSelectedTradeForReceipt] = useState<PaperPosition | null>(null);
  const [showAllDays, setShowAllDays] = useState(false);
  const [chartTrade, setChartTrade] = useState<PaperPosition | null>(null);


  if (!portfolio) {
    return <div className="p-8 text-center desk-muted">Loading paper portfolio...</div>;
  }

  const closedTrades = liveTrades(portfolio.closed_trades);
  const filteredTrades = closedTrades.filter(
    (t) => matchSetup(t.setup_type, selectedSetupFilter) && matchKind(t, selectedKindFilter),
  );
  const isFiltered = selectedSetupFilter !== 'ALL' || selectedKindFilter !== 'ALL';
  const summary = summarizeTrades(filteredTrades);

  // Group newest first by calendar day.
  const ordered = filteredTrades.slice().reverse();
  const dayMap = new Map<string, PaperPosition[]>();
  ordered.forEach((t) => {
    const k = tradeDay(t);
    dayMap.set(k, [...(dayMap.get(k) ?? []), t]);
  });
  const days = Array.from(dayMap.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  let visibleDays = showAllDays ? days : days.slice(0, DAYS_SHOWN);
  const pageCount = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  if (view === 'today') {
    visibleDays = days.slice(0, 1);
  } else if (view === 'trades') {
    const pageMap = new Map<string, PaperPosition[]>();
    ordered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE).forEach((t) => {
      const k = tradeDay(t);
      pageMap.set(k, [...(pageMap.get(k) ?? []), t]);
    });
    visibleDays = Array.from(pageMap.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }
  const paged = view === 'trades';
  // Today tab: the summary and title describe the session shown, not the whole journal.
  const todayIso = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  const shownDay = view === 'today' ? visibleDays[0]?.[0] : undefined;
  const headSummary = view === 'today' ? summarizeTrades(visibleDays[0]?.[1] ?? []) : summary;
  const journalTitle =
    view === 'today'
      ? shownDay === undefined || shownDay === todayIso
        ? "Today's closed trades"
        : `Last session · ${dayLabel(shownDay)}`
      : `Closed Trades Journal (${filteredTrades.length}${isFiltered ? ` of ${closedTrades.length}` : ''})`;

  // Per-setup table over all live trades.
  const bySetup = new Map<string, { trades: number; wins: number; net: number }>();
  closedTrades.forEach((t) => {
    const code = setupCode(t.setup_type);
    const net = t.net_pnl ?? t.pnl_rupees ?? 0;
    const row = bySetup.get(code) ?? { trades: 0, wins: 0, net: 0 };
    row.trades += 1;
    row.wins += net > 0 ? 1 : 0;
    row.net += net;
    bySetup.set(code, row);
  });
  const setupRows = Array.from(bySetup.entries()).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="flex flex-col gap-3">
      {!hideStrip && <PortfolioStrip portfolio={portfolio} />}

      {/* Controls */}
      {show('setups') && (
      <div className="desk-panel px-3.5 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          className={`desk-btn ${portfolio.auto_trade_enabled ? 'solid' : ''}`}
          onClick={() => onToggleAutoTrade(!portfolio.auto_trade_enabled)}
        >
          <Power className="h-3.5 w-3.5" />
          {portfolio.auto_trade_enabled ? 'Auto-Enter on Signal: ON' : 'Auto-Enter on Signal: OFF'}
        </button>
        <div className="flex items-center gap-2 text-xs desk-muted">
          <span className="desk-label">Lot Multiplier</span>
          <div className="desk-seg" role="group" aria-label="Lot multiplier">
            {[2, 4, 6, 8, 10].map((l) => (
              <button key={l} type="button" aria-pressed={portfolio.default_lots === l} onClick={() => onChangeLots(l)}>
                {l}x
              </button>
            ))}
          </div>
        </div>
        <button type="button" className="desk-btn ml-auto" onClick={onResetPortfolio} title="Reset paper testing stats">
          <RefreshCcw className="h-3.5 w-3.5" />
          Reset Portfolio
        </button>
      </div>
      )}

      {show('setups') && <SetupStatsPanel refreshKey={portfolio.closed_trades.length} collapsible={view === 'setups'} />}

      {show('setups') && onChangeSetupMode && (
        <section className="desk-panel" aria-labelledby="setup-switches-title">
          <div className="desk-ph">
            <h2 id="setup-switches-title">Setup switches</h2>
            <span className="text-xs desk-muted">Auto-entry only. Manual trades are never blocked.</span>
          </div>
          <div className="px-3.5 py-2.5 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-2">
            {SETUP_SWITCH_ROWS.map((row) => {
              const current = portfolio.setup_modes?.[row.key] ?? 'all';
              return (
                <div key={row.key} className="flex items-center justify-between gap-3 text-xs">
                  <span>{row.label}</span>
                  <div className="desk-seg" role="group" aria-label={`${row.label} mode`}>
                    {(row.perIndex ? INDEX_MODE_OPTIONS : SETUP_MODE_OPTIONS).map((opt) => (
                      <button
                        key={opt.mode}
                        type="button"
                        title={opt.title}
                        aria-pressed={current === opt.mode}
                        onClick={() => onChangeSetupMode(row.key, opt.mode)}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {view === 'all' && (
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-3 items-start">
        <OpenPositionsPanel positions={portfolio.active_positions} onClosePosition={onClosePosition} />

        <section className="desk-panel" aria-labelledby="by-setup-title">
          <div className="desk-ph"><h2 id="by-setup-title">By setup</h2></div>
          {setupRows.length === 0 ? (
            <div className="p-6 text-center text-xs desk-muted">Setup results appear after the first closed trade.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="desk-table">
                <thead>
                  <tr><th scope="col">Setup</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Win</th><th scope="col" className="r">Net</th></tr>
                </thead>
                <tbody>
                  {setupRows.map(([code, r]) => (
                    <tr key={code}>
                      <td><span className="desk-code">{code}</span></td>
                      <td className="r desk-num">{r.trades}</td>
                      <td className="r desk-num">{Math.round((r.wins / r.trades) * 100)}%</td>
                      <td className={`r desk-num ${pnlClass(r.net)}`}>{formatCurrency(r.net, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
      )}

      {show('costs') && <CostPanel refreshKey={portfolio.closed_trades_count ?? closedTrades.length} />}

      {/* Closed trades journal, grouped by day */}
      {show('trades', 'today') && (
      <section className="desk-panel" aria-labelledby="journal-title">
        <div className={`desk-ph ${view !== 'all' ? 'sticky top-0 z-[2]' : ''}`} style={view !== 'all' ? { background: 'var(--panel)' } : undefined}>
          <h2 id="journal-title">{journalTitle}</h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 ml-auto">
            <div className="flex gap-1.5" role="group" aria-label="Journal instrument filter">
              {KIND_FILTER_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="desk-chip"
                  aria-pressed={selectedKindFilter === opt.id}
                  onClick={() => setSelectedKindFilter(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {view !== 'all' ? (
              <select
                className="desk-input"
                style={{ width: 'auto', padding: '3px 8px' }}
                value={selectedSetupFilter}
                onChange={(e) => setSelectedSetupFilter(e.target.value)}
                aria-label="Journal setup filter"
              >
                {SETUP_FILTER_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>{opt.label}</option>
                ))}
              </select>
            ) : (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Journal setup filter">
              {SETUP_FILTER_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="desk-chip"
                  aria-pressed={selectedSetupFilter === opt.id}
                  onClick={() => setSelectedSetupFilter(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            )}
          </div>
        </div>

        <div className="desk-day text-sm">
          <span>{headSummary.count} trades</span>
          <span className="desk-muted">{headSummary.winRate}% Win Rate</span>
          <span>Gross <b className={`desk-num ${pnlClass(headSummary.gross)}`}>{formatCurrency(headSummary.gross, true)}</b></span>
          <span>Net <b className={`desk-num ${pnlClass(headSummary.net)}`}>{formatCurrency(headSummary.net, true)}</b></span>
          <span>Slippage drag <b className="desk-num" style={{ color: 'var(--warn)' }}>
            {headSummary.slippage > 0 ? `-₹${headSummary.slippage.toLocaleString('en-IN', INR)}` : '₹0.00'}
          </b></span>
        </div>

        {filteredTrades.length === 0 ? (
          <div className="p-6 text-center text-xs desk-muted">
            {closedTrades.length === 0
              ? 'No closed trades yet. Trades will record here when targets or stop-losses are triggered.'
              : 'No closed trades matching the selected filters.'}
          </div>
        ) : (
          <>
            {visibleDays.map(([day, trades]) => {
              const s = summarizeTrades(trades);
              return (
                <div key={day}>
                  <div className="desk-day">
                    <span>{dayLabel(day)}</span>
                    <span className={`desk-num ${pnlClass(s.net)}`}>{formatCurrency(s.net, true)}</span>
                    <span className="desk-muted desk-num font-normal">
                      {s.count} {s.count === 1 ? 'trade' : 'trades'} · {Math.round(Number(s.winRate))}% win
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="desk-table">
                      <thead>
                        <tr>
                          <th scope="col">In → Out</th><th scope="col">Instrument</th><th scope="col">Setup</th><th scope="col" className="r">Entry → Exit</th>
                          <th scope="col" className="r">Gross</th><th scope="col" className="r">Net</th><th scope="col">Why it closed</th><th scope="col" className="r">{view !== 'all' ? 'Details' : 'Receipt'}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map((trade) => {
                          const grossVal = trade.gross_pnl ?? trade.pnl_rupees ?? 0;
                          const netVal = trade.net_pnl ?? trade.pnl_rupees ?? 0;
                          const slipTitle = [
                            trade.entry_slippage != null ? `Entry slippage ${trade.entry_slippage.toFixed(1)} pts` : '',
                            trade.exit_slippage != null ? `Exit slippage ${trade.exit_slippage.toFixed(1)} pts` : '',
                          ].filter(Boolean).join(' · ');
                          return (
                            <tr
                              key={trade.id}
                              className={view !== 'all' ? 'cursor-pointer' : undefined}
                              onClick={view !== 'all' ? () => setDrawerTrade(trade) : undefined}
                            >
                              <td className="desk-num" title={formatTradeSpan(trade)}>{formatTradeSpan(trade, { short: true })}</td>
                              <td>
                                <span className="desk-sym">{trade.strike_symbol}</span>{' '}
                                <span className={`desk-side ${trade.option_type === 'CE' ? 'ce' : 'pe'}`}>{trade.option_type}</span>
                              </td>
                              <td><span className="desk-code" title={trade.setup_type}>{setupCode(trade.setup_type)}</span></td>
                              <td className="r desk-num" title={slipTitle || undefined}>
                                {trade.option_entry.toFixed(1)}
                                {trade.entry_estimated && (
                                  <span className="desk-muted" title="Entry price was modelled, not a real quote"> est.</span>
                                )}
                                {' → '}
                                {trade.current_option_price.toFixed(1)}
                              </td>
                              <td className={`r desk-num ${pnlClass(grossVal)}`}>{formatCurrency(grossVal, true)}</td>
                              <td className={`r desk-num font-semibold ${pnlClass(netVal)}`}>{formatCurrency(netVal, true)}</td>
                              <td><ExitReason reason={trade.exit_reason || trade.status} /></td>
                              <td className="r whitespace-nowrap">
                                {view !== 'all' ? (
                                  <button
                                    type="button"
                                    className="desk-btn sm"
                                    onClick={(e) => { e.stopPropagation(); setDrawerTrade(trade); }}
                                    aria-label={`Details for ${trade.strike_symbol}`}
                                  >
                                    Details
                                  </button>
                                ) : (
                                  <>
                                    <button
                                      type="button"
                                      className="desk-btn mr-1"
                                      onClick={(e) => { e.stopPropagation(); setChartTrade(trade); }}
                                      title="Open chart"
                                      aria-label="Open trade chart"
                                    >
                                      <LineChart className="h-3.5 w-3.5" />
                                    </button>
                                    {trade.charges_breakdown ? (
                                      <button
                                        type="button"
                                        className="desk-btn"
                                        onClick={(e) => { e.stopPropagation(); setSelectedTradeForReceipt(trade); }}
                                        title="View Charges Breakdown"
                                        aria-label="View charges breakdown"
                                      >
                                        <Receipt className="h-3.5 w-3.5" />
                                      </button>
                                    ) : (
                                      <span className="desk-muted">—</span>
                                    )}
                                  </>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
            {paged && (
              <div className="flex items-center justify-between gap-3 px-3.5 py-2 text-xs desk-muted" style={{ borderTop: '1px solid var(--line)' }}>
                <span className="desk-num">
                  {safePage * PAGE_SIZE + 1}–{Math.min(ordered.length, (safePage + 1) * PAGE_SIZE)} of {ordered.length} trades
                </span>
                <span className="flex items-center gap-2">
                  <button type="button" className="desk-btn" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>Prev</button>
                  <span className="desk-num">Page {safePage + 1} / {pageCount}</span>
                  <button type="button" className="desk-btn" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>Next</button>
                </span>
              </div>
            )}
            {view === 'all' && days.length > DAYS_SHOWN && (
              <button
                type="button"
                className="w-full py-2.5 text-sm font-medium"
                style={{ color: 'var(--accent)' }}
                onClick={() => setShowAllDays((v) => !v)}
              >
                {showAllDays ? 'Show fewer days' : `Show ${days.length - DAYS_SHOWN} more days`}
              </button>
            )}
          </>
        )}
      </section>
      )}

      {drawerTrade && (
        <TradeDrawer
          trade={drawerTrade}
          onClose={() => setDrawerTrade(null)}
          onChart={() => setChartTrade(drawerTrade)}
          onReceipt={() => setSelectedTradeForReceipt(drawerTrade)}
        />
      )}

      {/* Itemized tax receipt */}
      {chartTrade && <PositionChartModal position={chartTrade} onClose={() => setChartTrade(null)} />}
      {selectedTradeForReceipt && <ReceiptModal trade={selectedTradeForReceipt} onClose={() => setSelectedTradeForReceipt(null)} />}
    </div>
  );
};
