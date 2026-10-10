import React, { useState, useEffect } from 'react';
import { PaperPortfolio, PaperPosition } from '../types';
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  CheckCircle2, 
  XCircle, 
  TrendingUp, 
  TrendingDown, 
  RefreshCcw, 
  Power, 
  Activity, 
  Receipt,
  X
} from 'lucide-react';

interface PaperPortfolioViewProps {
  portfolio?: PaperPortfolio;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onResetPortfolio: () => void;
}

const SETUP_FILTER_OPTIONS = [
  { id: 'ALL', label: 'All Setups' },
  { id: 'SETUP_1', label: 'Setup 1 (Squeeze)' },
  { id: 'SETUP_2', label: 'Setup 2 (Walking Bands)' },
  { id: 'SETUP_3', label: 'Setup 3 (W/M Reversal)' },
  { id: 'SETUP_4', label: 'Setup 4 (ORB 9:30 AM)' },
  { id: 'SETUP_5', label: 'Setup 5 (Option Chart)' },
  { id: 'SETUP_6', label: 'Setup 6 (Pin Bar)' },
  { id: 'SETUP_7', label: 'Setup 7 (Inside Bar)' },
  { id: 'SETUP_8', label: 'Setup 8 (Climax Divergence)' },
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

export const PaperPortfolioView: React.FC<PaperPortfolioViewProps> = ({
  portfolio,
  onClosePosition,
  onToggleAutoTrade,
  onChangeLots,
  onResetPortfolio,
}) => {
  const [selectedSetupFilter, setSelectedSetupFilter] = useState<string>('ALL');
  const [selectedTradeForReceipt, setSelectedTradeForReceipt] = useState<PaperPosition | null>(null);

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
    return <div className="p-8 text-center text-slate-500">Loading paper portfolio...</div>;
  }

  const grossRealized = portfolio.total_gross_pnl ?? portfolio.total_realized_pnl ?? 0;
  const slippageCost = portfolio.total_slippage_cost ?? 0;
  const avgSlippagePts = portfolio.avg_slippage_points ?? 0;
  const totalCharges = portfolio.total_charges ?? 0;
  const netRealized = portfolio.total_net_pnl ?? portfolio.total_realized_pnl ?? 0;

  const isGrossPositive = grossRealized >= 0;
  const isNetPositive = netRealized >= 0;

  const formatCurrency = (val: number, showPlus = false) => {
    const absVal = Math.abs(val);
    const formatted = absVal.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    if (val > 0) return `${showPlus ? '+' : ''}₹${formatted}`;
    if (val < 0) return `-₹${formatted}`;
    return `₹${formatted}`;
  };

  // Filtered trades and metrics
  const closedTrades = portfolio.closed_trades ?? [];
  const filteredTrades = closedTrades.filter((t) => matchSetup(t.setup_type, selectedSetupFilter));
  
  const winningFilteredTrades = filteredTrades.filter((t) => {
    const pnl = t.net_pnl !== undefined ? t.net_pnl : (t.gross_pnl !== undefined ? t.gross_pnl : t.pnl_rupees);
    return pnl > 0;
  }).length;

  const filteredWinRate = filteredTrades.length > 0 
    ? ((winningFilteredTrades / filteredTrades.length) * 100).toFixed(1) 
    : '0.0';

  const filteredGross = filteredTrades.reduce((acc, t) => acc + (t.gross_pnl ?? t.pnl_rupees ?? 0), 0);
  const filteredNet = filteredTrades.reduce((acc, t) => acc + (t.net_pnl ?? t.pnl_rupees ?? 0), 0);
  const filteredSlippage = filteredTrades.reduce((acc, t) => acc + (t.total_slippage_cost ?? 0), 0);

  return (
    <div className="space-y-6">
      {/* 1. 4-Metric Glassmorphism Hero Performance Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Gross Realized P&L */}
        <div className={`p-4 rounded-2xl border backdrop-blur-md shadow-sm transition-all duration-200 ${
          isGrossPositive 
            ? 'bg-gradient-to-br from-emerald-50/70 via-white/80 to-emerald-50/30 border-emerald-300/80 dark:from-dark-800/80 dark:via-dark-800/60 dark:to-emerald-950/20 dark:border-emerald-800/60' 
            : 'bg-gradient-to-br from-rose-50/70 via-white/80 to-rose-50/30 border-rose-300/80 dark:from-dark-800/80 dark:via-dark-800/60 dark:to-rose-950/20 dark:border-rose-800/60'
        }`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-1">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Gross Realized P&L</span>
            {isGrossPositive ? <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" /> : <TrendingDown className="h-4 w-4 text-rose-600 dark:text-rose-400" />}
          </div>
          <div className={`text-2xl font-black font-mono ${isGrossPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
            {formatCurrency(grossRealized, true)}
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-500 dark:text-slate-400 mt-2">
            <span>Pure Strategy Edge</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">{portfolio.winning_trades_count}W / {portfolio.losing_trades_count}L</span>
          </div>
        </div>

        {/* Execution Slippage Impact */}
        <div className="p-4 rounded-2xl border backdrop-blur-md shadow-sm transition-all duration-200 bg-gradient-to-br from-amber-50/70 via-white/80 to-orange-50/30 border-amber-300/80 dark:from-dark-800/80 dark:via-dark-800/60 dark:to-amber-950/20 dark:border-amber-800/60">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-1">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Execution Slippage Impact</span>
            <Activity className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="text-2xl font-black font-mono text-amber-600 dark:text-amber-400">
            {slippageCost > 0 ? `-₹${slippageCost.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '₹0.00'}
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-500 dark:text-slate-400 mt-2">
            <span>Avg Drag: <strong className="text-amber-600 dark:text-amber-400">{avgSlippagePts > 0 ? `-${avgSlippagePts.toFixed(1)}` : '0.0'} pts</strong></span>
            <span className="text-slate-500 dark:text-slate-400">Spread & Latency</span>
          </div>
        </div>

        {/* Brokerage & Regulatory Taxes */}
        <div className="p-4 rounded-2xl border backdrop-blur-md shadow-sm transition-all duration-200 bg-gradient-to-br from-indigo-50/70 via-white/80 to-purple-50/30 border-indigo-300/80 dark:from-dark-800/80 dark:via-dark-800/60 dark:to-indigo-950/20 dark:border-indigo-800/60">
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-1">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Brokerage & Regulatory Taxes</span>
            <Receipt className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div className="text-2xl font-black font-mono text-indigo-600 dark:text-indigo-400">
            {totalCharges > 0 ? `-₹${totalCharges.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '₹0.00'}
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-500 dark:text-slate-400 mt-2">
            <span>STT, GST, Exch & SEBI</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300">Dhan Rate Card</span>
          </div>
        </div>

        {/* Net Realized P&L */}
        <div className={`p-4 rounded-2xl border backdrop-blur-md shadow-sm transition-all duration-200 ${
          isNetPositive 
            ? 'bg-gradient-to-br from-emerald-50 via-white to-emerald-50/30 border-emerald-300 dark:from-dark-800 dark:to-emerald-950/30 dark:border-emerald-800/80' 
            : 'bg-gradient-to-br from-rose-50 via-white to-rose-50/30 border-rose-300 dark:from-dark-800 dark:to-rose-950/30 dark:border-rose-800/80'
        }`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-1">
            <span className="font-semibold uppercase tracking-wider text-[11px]">Net Realized P&L</span>
            {isNetPositive ? <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" /> : <TrendingDown className="h-4 w-4 text-rose-600 dark:text-rose-400" />}
          </div>
          <div className={`text-2xl font-black font-mono ${isNetPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
            {formatCurrency(netRealized, true)}
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-500 dark:text-slate-400 mt-2">
            <span>Win Rate: <strong className="text-cyan-600 dark:text-cyan-400">{portfolio.win_rate_pct.toFixed(1)}%</strong></span>
            <span>Floating: <strong className={portfolio.total_unrealized_pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>₹{portfolio.total_unrealized_pnl.toFixed(2)}</strong></span>
          </div>
        </div>
      </div>

      {/* 2. Controls & Configuration */}
      <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-4">
          {/* Auto Trade Toggle */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onToggleAutoTrade(!portfolio.auto_trade_enabled)}
              className={`flex items-center gap-2 text-xs font-bold px-3 py-1.5 rounded-xl transition ${
                portfolio.auto_trade_enabled
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30'
                  : 'bg-slate-100 dark:bg-dark-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-dark-700'
              }`}
            >
              <Power className="h-3.5 w-3.5" />
              {portfolio.auto_trade_enabled ? 'Auto-Enter on Signal: ON' : 'Auto-Enter on Signal: OFF'}
            </button>
          </div>

          {/* Lot Multiplier Selector */}
          <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
            <span className="font-semibold">Lot Multiplier:</span>
            <div className="flex bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700 rounded-lg p-1">
              {[2, 4, 6, 8, 10].map((l) => (
                <button
                  key={l}
                  onClick={() => onChangeLots(l)}
                  className={`px-2.5 py-0.5 rounded text-xs font-bold transition ${
                    portfolio.default_lots === l
                      ? 'bg-cyan-600 text-white shadow-sm'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  {l}x
                </button>
              ))}
            </div>
          </div>
        </div>

        <button
          onClick={onResetPortfolio}
          className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition"
          title="Reset paper testing stats"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Reset Portfolio
        </button>
      </div>

      {/* 3. Active Positions Table */}
      <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-5 py-3.5 border-b border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-900 flex items-center justify-between">
          <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">
            Active Open Paper Positions ({portfolio.active_positions.length})
          </h3>
          <span className="text-[11px] text-cyan-600 dark:text-cyan-400 font-mono">
            Auto-books 50% at Target 1 & trails remainder at Breakeven
          </span>
        </div>

        {portfolio.active_positions.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No open paper positions. New signals will automatically open trades or you can click "Paper Buy" on any signal card.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 dark:bg-dark-950/70 border-b border-slate-200 dark:border-dark-700 text-slate-600 dark:text-slate-400 uppercase font-semibold">
                <tr>
                  <th className="py-2.5 px-4">Instrument / Strike</th>
                  <th className="py-2.5 px-4">Direction</th>
                  <th className="py-2.5 px-4">Qty (Lots)</th>
                  <th className="py-2.5 px-4">Option Entry</th>
                  <th className="py-2.5 px-4">Current LTP</th>
                  <th className="py-2.5 px-4">Option SL / Target</th>
                  <th className="py-2.5 px-4">P&L (Pts)</th>
                  <th className="py-2.5 px-4">P&L (₹)</th>
                  <th className="py-2.5 px-4">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-dark-700/60">
                {portfolio.active_positions.map((pos) => {
                  const isPos = pos.pnl_rupees >= 0;
                  const isCE = pos.option_type === 'CE';
                  const isT1 = pos.status === 'TARGET_1';

                  return (
                    <tr key={pos.id} className="hover:bg-slate-50 dark:hover:bg-dark-700/30 transition">
                      <td className="py-3 px-4 font-mono">
                        <strong className="text-slate-900 dark:text-white block text-sm">{pos.strike_symbol}</strong>
                        <span className="text-[10px] text-slate-500 dark:text-slate-400">
                          {pos.symbol} • {pos.timeframe} @ {pos.entry_time}
                        </span>
                      </td>

                      <td className="py-3 px-4">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-black text-[10px] ${
                          isCE ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-800' : 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950 dark:text-rose-400 dark:border-rose-800'
                        }`}>
                          {isCE ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                          BUY {pos.option_type}
                        </span>
                      </td>

                      <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-300">
                        {pos.quantity} <span className="text-[10px] text-slate-500">({pos.lots}L × {pos.lot_size})</span>
                        {isT1 && (
                          <span className="block text-[10px] text-cyan-600 dark:text-cyan-400 font-bold mt-0.5">
                            ✓ 50% Booked (+₹{pos.booked_pnl_rupees?.toFixed(1) || '0'})
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-200">
                        ₹{pos.option_entry.toFixed(1)}
                      </td>

                      <td className="py-3 px-4 font-mono font-bold text-slate-900 dark:text-white">
                        ₹{pos.current_option_price.toFixed(1)}
                      </td>

                      <td className="py-3 px-4 font-mono text-[11px]">
                        {isT1 ? (
                          <>
                            <span className="text-cyan-600 dark:text-cyan-400 block font-semibold">Trailed SL (Cost): ₹{pos.option_sl.toFixed(1)}</span>
                            <span className="text-emerald-600 dark:text-emerald-400 block">T2 Target: ₹{pos.option_target_2.toFixed(1)}</span>
                          </>
                        ) : (
                          <>
                            <span className="text-rose-600 dark:text-rose-400 block">SL: ₹{pos.option_sl.toFixed(1)}</span>
                            <span className="text-emerald-600 dark:text-emerald-400 block">T1: ₹{pos.option_target_1.toFixed(1)}</span>
                          </>
                        )}
                      </td>

                      <td className={`py-3 px-4 font-mono font-bold ${isPos ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        {isPos ? '+' : ''}{pos.pnl_points.toFixed(1)} pts
                      </td>

                      <td className={`py-3 px-4 font-mono font-black text-sm ${isPos ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        {isPos ? '+' : ''}₹{pos.pnl_rupees.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                      </td>

                      <td className="py-3 px-4">
                        <button
                          onClick={() => onClosePosition(pos.id)}
                          className="px-2.5 py-1 bg-slate-100 hover:bg-rose-50 dark:bg-dark-900 dark:hover:bg-rose-900/60 border border-slate-200 hover:border-rose-300 dark:border-dark-600 dark:hover:border-rose-700 text-rose-600 dark:text-rose-300 rounded-lg text-xs font-semibold transition"
                        >
                          Close
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 4. Closed Trades History */}
      <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-5 py-3.5 border-b border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-900 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">
            Closed Trades Journal ({filteredTrades.length}{selectedSetupFilter !== 'ALL' ? ` of ${closedTrades.length}` : ''})
          </h3>
        </div>

        {/* Setup Filter Tabs & Dynamic Summary Strip */}
        <div className="p-4 border-b border-slate-200 dark:border-dark-700 space-y-3 bg-white dark:bg-dark-800">
          <div className="flex flex-wrap items-center gap-2">
            {SETUP_FILTER_OPTIONS.map((opt) => {
              const isActive = selectedSetupFilter === opt.id;
              return (
                <button
                  key={opt.id}
                  onClick={() => setSelectedSetupFilter(opt.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${
                    isActive
                      ? 'bg-cyan-600 text-white shadow-sm shadow-cyan-600/30'
                      : 'bg-slate-100 hover:bg-slate-200 dark:bg-dark-900 dark:hover:bg-dark-700 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-dark-700'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>

          {/* Dynamic Setup Summary Strip */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 dark:bg-dark-900/60 px-4 py-2.5 rounded-xl border border-slate-200/80 dark:border-dark-700/80 text-xs">
            <div className="flex items-center gap-5 flex-wrap">
              <div className="flex items-center gap-1.5 font-bold text-slate-800 dark:text-slate-200">
                <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
                <span>{filteredTrades.length} Trades</span>
              </div>
              <div className="text-slate-600 dark:text-slate-400">
                <span>Win Rate: </span>
                <strong className="text-cyan-600 dark:text-cyan-400 font-mono font-bold">
                  {filteredWinRate}% Win Rate
                </strong>
              </div>
              <div className="text-slate-600 dark:text-slate-400">
                <span>Gross P&L: </span>
                <strong className={`font-mono font-bold ${filteredGross >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                  {formatCurrency(filteredGross, true)}
                </strong>
              </div>
              <div className="text-slate-600 dark:text-slate-400">
                <span>Net P&L: </span>
                <strong className={`font-mono font-bold ${filteredNet >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                  {formatCurrency(filteredNet, true)}
                </strong>
              </div>
              <div className="text-slate-600 dark:text-slate-400">
                <span>Slippage Drag: </span>
                <strong className="text-amber-600 dark:text-amber-400 font-mono font-bold">
                  {filteredSlippage > 0 ? `-₹${filteredSlippage.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '₹0.00'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        {filteredTrades.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            {closedTrades.length === 0
              ? 'No closed trades yet. Trades will record here when targets or stop-losses are triggered.'
              : 'No closed trades matching the selected setup filter.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 dark:bg-dark-950/70 border-b border-slate-200 dark:border-dark-700 text-slate-600 dark:text-slate-400 uppercase font-semibold">
                <tr>
                  <th className="py-2.5 px-4">Strike Symbol</th>
                  <th className="py-2.5 px-4">Setup</th>
                  <th className="py-2.5 px-4">Exit Reason</th>
                  <th className="py-2.5 px-4">Entry ₹</th>
                  <th className="py-2.5 px-4">Exit ₹</th>
                  <th className="py-2.5 px-4">Gross vs Net P&L</th>
                  <th className="py-2.5 px-4">Outcome</th>
                  <th className="py-2.5 px-4 text-center">Receipt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-dark-700/60">
                {filteredTrades.slice().reverse().map((trade) => {
                  const grossVal = trade.gross_pnl ?? trade.pnl_rupees ?? 0;
                  const netVal = trade.net_pnl ?? trade.pnl_rupees ?? 0;
                  const isWin = netVal > 0;

                  return (
                    <tr key={trade.id} className="hover:bg-slate-50 dark:hover:bg-dark-700/30 transition">
                      <td className="py-2.5 px-4 font-mono font-bold text-slate-900 dark:text-white">
                        {trade.strike_symbol}
                        <span className="block text-[10px] text-slate-500 font-normal">
                          {trade.entry_time} → {trade.exit_time}
                        </span>
                      </td>

                      <td className="py-2.5 px-4 text-slate-700 dark:text-slate-300">
                        {trade.setup_type}
                      </td>

                      <td className="py-2.5 px-4 text-slate-700 dark:text-slate-300 font-medium">
                        {trade.exit_reason || trade.status}
                      </td>

                      <td className="py-2.5 px-4 font-mono text-slate-700 dark:text-slate-300">
                        <div>₹{trade.option_entry.toFixed(1)}</div>
                        {trade.entry_slippage !== undefined && trade.entry_slippage !== null && (
                          <div className="text-[10px] text-amber-600 dark:text-amber-400 font-normal">
                            (Slip: {trade.entry_slippage >= 0 ? `+${trade.entry_slippage.toFixed(1)}` : `${trade.entry_slippage.toFixed(1)}`} pts)
                          </div>
                        )}
                      </td>

                      <td className="py-2.5 px-4 font-mono text-slate-900 dark:text-white font-bold">
                        <div>₹{trade.current_option_price.toFixed(1)}</div>
                        {trade.exit_slippage !== undefined && trade.exit_slippage !== null && (
                          <div className="text-[10px] text-amber-600 dark:text-amber-400 font-normal">
                            {trade.exit_slippage && trade.exit_slippage > 0 ? `(Slip: -${trade.exit_slippage.toFixed(1)} pts)` : '(Slip: 0.0 pts)'}
                          </div>
                        )}
                      </td>

                      <td className="py-2.5 px-4 font-mono">
                        <div className={`font-semibold text-xs ${grossVal >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                          {formatCurrency(grossVal, true)} Gross
                        </div>
                        <div className={`font-black text-xs ${netVal >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                          {formatCurrency(netVal, true)} Net
                        </div>
                      </td>

                      <td className="py-2.5 px-4">
                        {isWin ? (
                          <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-bold">
                            <CheckCircle2 className="h-4 w-4" /> WIN
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-rose-600 dark:text-rose-400 font-bold">
                            <XCircle className="h-4 w-4" /> LOSS
                          </span>
                        )}
                      </td>

                      <td className="py-2.5 px-4 text-center">
                        {trade.charges_breakdown ? (
                          <button
                            onClick={() => setSelectedTradeForReceipt(trade)}
                            title="View Charges Breakdown"
                            className="inline-flex items-center justify-center p-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/50 dark:hover:bg-indigo-900/60 border border-indigo-200 dark:border-indigo-800 text-indigo-600 dark:text-indigo-400 transition shadow-sm"
                          >
                            <Receipt className="h-3.5 w-3.5" />
                          </button>
                        ) : (
                          <span className="text-slate-300 dark:text-slate-600 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 5. Itemized Tax Popover / Modal */}
      {selectedTradeForReceipt && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in"
          onClick={() => setSelectedTradeForReceipt(null)}
        >
          <div 
            className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl max-w-md w-full shadow-2xl p-5 overflow-hidden text-slate-800 dark:text-slate-100 relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-dark-700">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                  <Receipt className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                    Dhan & Statutory Taxes Receipt
                  </h4>
                  <p className="text-[11px] text-slate-500 font-mono">
                    {selectedTradeForReceipt.strike_symbol} • {selectedTradeForReceipt.setup_type}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedTradeForReceipt(null)}
                aria-label="Close"
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-dark-700 transition"
              >
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
                  <div className="grid grid-cols-2 gap-2 my-3 p-3 bg-slate-50 dark:bg-dark-900/60 rounded-xl border border-slate-100 dark:border-dark-700 text-xs font-mono">
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase block font-sans">Buy Turnover</span>
                      <span className="font-bold">₹{cb.buy_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase block font-sans">Sell Turnover</span>
                      <span className="font-bold">₹{cb.sell_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase block font-sans">Total Turnover</span>
                      <span className="font-bold">₹{cb.total_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase block font-sans">Orders Executed</span>
                      <span className="font-bold">{cb.orders_count} orders</span>
                    </div>
                  </div>

                  {/* Itemized Fees & Taxes */}
                  <div className="space-y-2 text-xs divide-y divide-slate-100 dark:divide-dark-700">
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">Brokerage (Dhan ₹20/order)</span>
                      <span className="font-mono font-bold">₹{cb.brokerage.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">STT (0.1% on Sell)</span>
                      <span className="font-mono font-bold">₹{cb.stt.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">NSE Exchange Fee (0.05%)</span>
                      <span className="font-mono font-bold">₹{cb.exchange_fee.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">GST (18%)</span>
                      <span className="font-mono font-bold">₹{cb.gst.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">Stamp Duty (0.003% on Buy)</span>
                      <span className="font-mono font-bold">₹{cb.stamp_duty.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="text-slate-600 dark:text-slate-400">SEBI Turnover Fee</span>
                      <span className="font-mono font-bold">₹{cb.sebi_fee.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Total Deductions */}
                  <div className="mt-4 pt-3 border-t border-slate-200 dark:border-dark-700 flex justify-between items-center">
                    <div>
                      <span className="font-bold text-xs uppercase tracking-wider text-slate-700 dark:text-slate-300 block">
                        Total Deductions
                      </span>
                      <span className="text-[10px] text-slate-500 font-sans">Dhan F&O Rate Card</span>
                    </div>
                    <span className="text-sm font-black font-mono text-rose-600 dark:text-rose-400">
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
