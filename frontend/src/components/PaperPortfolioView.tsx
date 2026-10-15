import React, { useState, useEffect } from 'react';
import { PaperPortfolio, PaperPosition } from '../types';
import { RefreshCcw, Power, Receipt, X, LineChart } from 'lucide-react';
import { PositionChartModal } from './PositionChartModal';
import { setupCode } from './setupCode';

// Show the date whenever a trade crosses midnight/sessions so an overnight exit never
// looks like it happened before its entry (times alone are HH:MM:SS).
export function formatTradeSpan(trade: {
  entry_time: string;
  exit_time?: string;
  entry_datetime?: string | null;
  exit_datetime?: string | null;
}): string {
  const entryDate = trade.entry_datetime?.slice(0, 10);
  const exitDate = trade.exit_datetime?.slice(0, 10);
  const fmt = (iso: string, time: string) => {
    const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
    const label = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    return `${label} ${time}`;
  };
  if (entryDate && exitDate && entryDate !== exitDate) {
    return `${fmt(entryDate, trade.entry_time)} → ${fmt(exitDate, trade.exit_time ?? '')}`;
  }
  return `${trade.entry_time} → ${trade.exit_time ?? ''}`;
}


type SummaryTrade = {
  quarantine_reason?: string | null;
  net_pnl?: number;
  gross_pnl?: number;
  pnl_rupees?: number;
  total_slippage_cost?: number;
};

export function summarizeTrades(trades: SummaryTrade[]) {
  const counted = trades.filter((t) => !t.quarantine_reason);
  const wins = counted.filter((t) => (t.net_pnl ?? t.gross_pnl ?? t.pnl_rupees ?? 0) > 0).length;
  return {
    count: counted.length,
    winRate: counted.length > 0 ? ((wins / counted.length) * 100).toFixed(1) : '0.0',
    gross: counted.reduce((a, t) => a + (t.gross_pnl ?? t.pnl_rupees ?? 0), 0),
    net: counted.reduce((a, t) => a + (t.net_pnl ?? t.pnl_rupees ?? 0), 0),
    slippage: counted.reduce((a, t) => a + (t.total_slippage_cost ?? 0), 0),
  };
}


interface PaperPortfolioViewProps {
  portfolio?: PaperPortfolio;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onResetPortfolio: () => void;
  hideStrip?: boolean;
}

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
];

const matchSetup = (tradeSetup: string | undefined, filterId: string) => {
  if (filterId === 'ALL') return true;
  if (!tradeSetup) return false;
  const s = tradeSetup.toUpperCase();
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
  return false;
};

const INR = { minimumFractionDigits: 2, maximumFractionDigits: 2 } as const;

export const formatCurrency = (val: number, showPlus = false) => {
  const formatted = Math.abs(val).toLocaleString('en-IN', INR);
  if (val > 0) return `${showPlus ? '+' : ''}₹${formatted}`;
  if (val < 0) return `-₹${formatted}`;
  return `₹${formatted}`;
};

const pnlClass = (v: number) => (v > 0 ? 'desk-up' : v < 0 ? 'desk-down' : '');

// Quarantined rows come from before the live journal began; they are never shown or counted.
export const liveTrades = (trades: PaperPosition[] | undefined): PaperPosition[] =>
  (trades ?? []).filter((t) => !t.quarantine_reason);

/* ---------- P&L strip ---------- */
export const PortfolioStrip: React.FC<{ portfolio?: PaperPortfolio }> = ({ portfolio }) => {
  const grossRealized = portfolio?.total_gross_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const slippageCost = portfolio?.total_slippage_cost ?? 0;
  const avgSlippagePts = portfolio?.avg_slippage_points ?? 0;
  const totalCharges = portfolio?.total_charges ?? 0;
  const netRealized = portfolio?.total_net_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const floating = portfolio?.total_unrealized_pnl ?? 0;

  return (
    <section
      className="desk-strip grid-cols-2 md:grid-cols-3 lg:grid-cols-[1.4fr_repeat(4,1fr)]"
      aria-label="Portfolio performance"
    >
      <div className="col-span-2 md:col-span-3 lg:col-span-1">
        <div className="desk-label">Net Realized P&L</div>
        <div className={`desk-num text-[26px] font-semibold ${pnlClass(netRealized)}`}>
          {formatCurrency(netRealized, true)}
        </div>
      </div>
      <div>
        <div className="desk-label">Gross Realized P&L</div>
        <div className={`desk-num text-lg font-semibold ${pnlClass(grossRealized)}`}>
          {formatCurrency(grossRealized, true)}
        </div>
        <div className="text-xs desk-muted">
          {portfolio?.winning_trades_count ?? 0}W / {portfolio?.losing_trades_count ?? 0}L
        </div>
      </div>
      <div>
        <div className="desk-label">Execution Slippage Impact</div>
        <div className="desk-num text-lg font-semibold" style={{ color: 'var(--warn)' }}>
          {slippageCost > 0 ? `-₹${slippageCost.toLocaleString('en-IN', INR)}` : '₹0.00'}
        </div>
        <div className="text-xs desk-muted">
          Avg drag {avgSlippagePts > 0 ? `-${avgSlippagePts.toFixed(1)}` : '0.0'} pts
        </div>
      </div>
      <div>
        <div className="desk-label">Brokerage & Regulatory Taxes</div>
        <div className="desk-num text-lg font-semibold">
          {totalCharges > 0 ? `-₹${totalCharges.toLocaleString('en-IN', INR)}` : '₹0.00'}
        </div>
        <div className="text-xs desk-muted">STT, GST, exchange, SEBI</div>
      </div>
      <div>
        <div className="desk-label">Win rate</div>
        <div className="desk-num text-lg font-semibold">{(portfolio?.win_rate_pct ?? 0).toFixed(1)}%</div>
        <div className="text-xs desk-muted">
          Floating <span className={`desk-num ${pnlClass(floating)}`}>₹{floating.toFixed(2)}</span>
        </div>
      </div>
    </section>
  );
};

/* ---------- Open positions ---------- */
export const OpenPositionsPanel: React.FC<{
  positions: PaperPosition[];
  onClosePosition: (id: string) => void;
}> = ({ positions, onClosePosition }) => {
  // Keep the position itself, so the popup stays open (and shows the exit) if the trade closes meanwhile.
  const [chartPosition, setChartPosition] = useState<PaperPosition | null>(null);
  return (
  <section className="desk-panel" aria-labelledby="open-positions-title">
    <div className="desk-ph">
      <h2 id="open-positions-title">Active Open Paper Positions ({positions.length})</h2>
      <span className="text-xs desk-muted ml-auto">Books 50% at T1, then trails the rest at breakeven</span>
    </div>
    {positions.length === 0 ? (
      <div className="p-6 text-center text-xs desk-muted">
        No open paper positions. New signals open trades automatically, or click "Paper buy" on a signal.
      </div>
    ) : (
      positions.map((pos) => {
        const isT1 = pos.status === 'TARGET_1';
        const target = isT1 ? pos.option_target_2 : pos.option_target_1;
        const span = target - pos.option_sl;
        const frac = span > 0 ? Math.max(0, Math.min(1, (pos.current_option_price - pos.option_sl) / span)) : 0.5;
        return (
          <div
            key={pos.id}
            className="px-3.5 py-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 cursor-pointer"
            style={{ borderBottom: '1px solid var(--line)' }}
            onClick={() => setChartPosition(pos)}
            title="Click to open chart"
          >
            <div>
              <span className="desk-sym">{pos.strike_symbol}</span>{' '}
              <span className={`desk-side ${pos.option_type === 'CE' ? 'ce' : 'pe'}`}>BUY {pos.option_type}</span>
              <span className="desk-sub">
                {setupCode(pos.setup_type)} · {pos.symbol} {pos.timeframe} @ {pos.entry_time} · {pos.quantity} qty ({pos.lots}L × {pos.lot_size})
              </span>
            </div>
            <div className={`desk-num text-xl font-semibold text-right ${pnlClass(pos.pnl_rupees)}`}>
              {pos.pnl_rupees >= 0 ? '+' : ''}₹{pos.pnl_rupees.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
              <span className="desk-sub text-right">{pos.pnl_points >= 0 ? '+' : ''}{pos.pnl_points.toFixed(1)} pts</span>
            </div>
            <div
              className="col-span-2 relative h-1.5 rounded-sm my-2"
              style={{ background: 'linear-gradient(90deg, var(--down-soft) 0 33%, var(--line) 33% 66%, var(--up-soft) 66%)' }}
            >
              <i className="absolute block rounded-sm" style={{ top: -3, width: 3, height: 12, background: 'var(--fg)', left: `calc(${frac * 100}% - 1px)` }} />
            </div>
            <div className="col-span-2 flex flex-wrap justify-between gap-x-3 text-xs desk-num desk-muted">
              <span className={isT1 ? '' : 'desk-down'}>{isT1 ? 'Trailed SL' : 'SL'} {pos.option_sl.toFixed(1)}</span>
              <span>Entry {pos.option_entry.toFixed(1)}</span>
              <span style={{ color: 'var(--fg)', fontWeight: 600 }}>LTP {pos.current_option_price.toFixed(1)}</span>
              <span className="desk-up">{isT1 ? 'T2' : 'T1'} {target.toFixed(1)}</span>
            </div>
            {isT1 && (
              <div className="col-span-2 text-xs" style={{ color: 'var(--accent)' }}>
                ✓ 50% booked (+₹{pos.booked_pnl_rupees?.toFixed(1) || '0'})
              </div>
            )}
            <div className="col-span-2 text-right mt-1">
              <button type="button" className="desk-btn accent mr-2" onClick={(e) => { e.stopPropagation(); setChartPosition(pos); }}>
                Chart
              </button>
              <button type="button" className="desk-btn danger" onClick={(e) => { e.stopPropagation(); onClosePosition(pos.id); }}>
                Close
              </button>
            </div>
          </div>
        );
      })
    )}
    {chartPosition && <PositionChartModal position={chartPosition} onClose={() => setChartPosition(null)} />}
  </section>
  );
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

export const PaperPortfolioView: React.FC<PaperPortfolioViewProps> = ({
  portfolio,
  onClosePosition,
  onToggleAutoTrade,
  onChangeLots,
  onResetPortfolio,
  hideStrip = false,
}) => {
  const [selectedSetupFilter, setSelectedSetupFilter] = useState<string>('ALL');
  const [selectedTradeForReceipt, setSelectedTradeForReceipt] = useState<PaperPosition | null>(null);
  const [showAllDays, setShowAllDays] = useState(false);
  const [chartTrade, setChartTrade] = useState<PaperPosition | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedTradeForReceipt(null);
      }
    };
    if (selectedTradeForReceipt) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [selectedTradeForReceipt]);

  if (!portfolio) {
    return <div className="p-8 text-center desk-muted">Loading paper portfolio...</div>;
  }

  const closedTrades = liveTrades(portfolio.closed_trades);
  const filteredTrades = closedTrades.filter((t) => matchSetup(t.setup_type, selectedSetupFilter));
  const summary = summarizeTrades(filteredTrades);

  // Group newest first by calendar day.
  const ordered = filteredTrades.slice().reverse();
  const dayMap = new Map<string, PaperPosition[]>();
  ordered.forEach((t) => {
    const k = tradeDay(t);
    dayMap.set(k, [...(dayMap.get(k) ?? []), t]);
  });
  const days = Array.from(dayMap.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  const visibleDays = showAllDays ? days : days.slice(0, DAYS_SHOWN);

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
                  <tr><th>Setup</th><th className="r">Trades</th><th className="r">Win</th><th className="r">Net</th></tr>
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

      {/* Closed trades journal, grouped by day */}
      <section className="desk-panel" aria-labelledby="journal-title">
        <div className="desk-ph">
          <h2 id="journal-title">
            Closed Trades Journal ({filteredTrades.length}{selectedSetupFilter !== 'ALL' ? ` of ${closedTrades.length}` : ''})
          </h2>
          <div className="flex flex-wrap gap-1.5 ml-auto" role="group" aria-label="Journal setup filter">
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
        </div>

        <div className="desk-day text-sm">
          <span>{summary.count} trades</span>
          <span className="desk-muted">{summary.winRate}% Win Rate</span>
          <span>Gross <b className={`desk-num ${pnlClass(summary.gross)}`}>{formatCurrency(summary.gross, true)}</b></span>
          <span>Net <b className={`desk-num ${pnlClass(summary.net)}`}>{formatCurrency(summary.net, true)}</b></span>
          <span>Slippage drag <b className="desk-num" style={{ color: 'var(--warn)' }}>
            {summary.slippage > 0 ? `-₹${summary.slippage.toLocaleString('en-IN', INR)}` : '₹0.00'}
          </b></span>
        </div>

        {filteredTrades.length === 0 ? (
          <div className="p-6 text-center text-xs desk-muted">
            {closedTrades.length === 0
              ? 'No closed trades yet. Trades will record here when targets or stop-losses are triggered.'
              : 'No closed trades matching the selected setup filter.'}
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
                          <th>In → Out</th><th>Instrument</th><th>Setup</th><th className="r">Entry → Exit</th>
                          <th className="r">Gross</th><th className="r">Net</th><th>Why it closed</th><th className="r">Receipt</th>
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
                            <tr key={trade.id}>
                              <td className="desk-num">{formatTradeSpan(trade)}</td>
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
                              <td>{trade.exit_reason || trade.status}</td>
                              <td className="r whitespace-nowrap">
                                <button
                                  type="button"
                                  className="desk-btn mr-1"
                                  onClick={() => setChartTrade(trade)}
                                  title="Open chart"
                                  aria-label="Open trade chart"
                                >
                                  <LineChart className="h-3.5 w-3.5" />
                                </button>
                                {trade.charges_breakdown ? (
                                  <button
                                    type="button"
                                    className="desk-btn"
                                    onClick={() => setSelectedTradeForReceipt(trade)}
                                    title="View Charges Breakdown"
                                    aria-label="View charges breakdown"
                                  >
                                    <Receipt className="h-3.5 w-3.5" />
                                  </button>
                                ) : (
                                  <span className="desk-muted">—</span>
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
            {days.length > DAYS_SHOWN && (
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

      {/* Itemized tax receipt */}
      {chartTrade && <PositionChartModal position={chartTrade} onClose={() => setChartTrade(null)} />}
      {selectedTradeForReceipt && (
        <div className="desk-overlay" onClick={() => setSelectedTradeForReceipt(null)}>
          <div className="desk-modal p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3" style={{ borderBottom: '1px solid var(--line)' }}>
              <div>
                <h4 className="text-sm font-semibold">Dhan & Statutory Taxes Receipt</h4>
                <p className="text-[11px] desk-muted font-mono">
                  {selectedTradeForReceipt.strike_symbol} • {selectedTradeForReceipt.setup_type}
                </p>
              </div>
              <button type="button" onClick={() => setSelectedTradeForReceipt(null)} aria-label="Close" className="desk-btn">
                <X className="h-4 w-4" />
              </button>
            </div>

            {(() => {
              const cb = selectedTradeForReceipt.charges_breakdown ?? {
                buy_turnover: selectedTradeForReceipt.option_entry * selectedTradeForReceipt.quantity,
                sell_turnover: selectedTradeForReceipt.current_option_price * selectedTradeForReceipt.quantity,
                total_turnover: (selectedTradeForReceipt.option_entry + selectedTradeForReceipt.current_option_price) * selectedTradeForReceipt.quantity,
                orders_count: 2,
                brokerage: 40.0,
                stt: 0,
                exchange_fee: 0,
                sebi_fee: 0,
                stamp_duty: 0,
                gst: 0,
                total_charges: selectedTradeForReceipt.total_charges ?? 0,
              };

              return (
                <>
                  {/* Turnover Summary */}
                  <div className="grid grid-cols-2 gap-2 my-3 p-3 rounded-md text-xs font-mono" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
                    <div>
                      <span className="text-[10px] desk-muted uppercase block font-sans">Buy Turnover</span>
                      <span className="font-bold">₹{cb.buy_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] desk-muted uppercase block font-sans">Sell Turnover</span>
                      <span className="font-bold">₹{cb.sell_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] desk-muted uppercase block font-sans">Total Turnover</span>
                      <span className="font-bold">₹{cb.total_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] desk-muted uppercase block font-sans">Orders Executed</span>
                      <span className="font-bold">{cb.orders_count} orders</span>
                    </div>
                  </div>

                  {/* Itemized Fees & Taxes */}
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">Brokerage (Dhan ₹20/order)</span>
                      <span className="font-mono font-bold">₹{cb.brokerage.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">STT (0.1% on Sell)</span>
                      <span className="font-mono font-bold">₹{cb.stt.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">NSE Exchange Fee (0.05%)</span>
                      <span className="font-mono font-bold">₹{cb.exchange_fee.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">GST (18%)</span>
                      <span className="font-mono font-bold">₹{cb.gst.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">Stamp Duty (0.003% on Buy)</span>
                      <span className="font-mono font-bold">₹{cb.stamp_duty.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">SEBI Turnover Fee</span>
                      <span className="font-mono font-bold">₹{cb.sebi_fee.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Total Deductions */}
                  <div className="mt-4 pt-3 flex justify-between items-center" style={{ borderTop: '1px solid var(--line)' }}>
                    <div>
                      <span className="font-bold text-xs uppercase tracking-wider block">
                        Total Deductions
                      </span>
                      <span className="text-[10px] desk-muted font-sans">Dhan F&O Rate Card</span>
                    </div>
                    <span className="text-sm font-semibold font-mono desk-down">
                      -₹{cb.total_charges.toFixed(2)}
                    </span>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
};
