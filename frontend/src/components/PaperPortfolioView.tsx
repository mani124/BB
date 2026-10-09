import React from 'react';
import { PaperPortfolio } from '../types';
import { ArrowUpRight, ArrowDownRight, CheckCircle2, XCircle, TrendingUp, TrendingDown, RefreshCcw, Power, Activity, Receipt } from 'lucide-react';

interface PaperPortfolioViewProps {
  portfolio?: PaperPortfolio;
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onResetPortfolio: () => void;
}

export const PaperPortfolioView: React.FC<PaperPortfolioViewProps> = ({
  portfolio,
  onClosePosition,
  onToggleAutoTrade,
  onChangeLots,
  onResetPortfolio,
}) => {
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
        <div className="px-5 py-3.5 border-b border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-900">
          <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">
            Closed Trades Journal ({portfolio.closed_trades.length})
          </h3>
        </div>

        {portfolio.closed_trades.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            No closed trades yet. Trades will record here when targets or stop-losses are triggered.
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
                  <th className="py-2.5 px-4">Net P&L (₹)</th>
                  <th className="py-2.5 px-4">Outcome</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-dark-700/60">
                {portfolio.closed_trades.slice().reverse().map((trade) => {
                  const isWin = trade.pnl_rupees > 0;

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
                        ₹{trade.option_entry.toFixed(1)}
                      </td>

                      <td className="py-2.5 px-4 font-mono text-slate-900 dark:text-white font-bold">
                        ₹{trade.current_option_price.toFixed(1)}
                      </td>

                      <td className={`py-2.5 px-4 font-mono font-black text-sm ${isWin ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                        {isWin ? '+' : ''}₹{trade.pnl_rupees.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
