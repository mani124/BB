import React from 'react';
import { Signal } from '../types';
import { ArrowUpRight, ArrowDownRight, ShoppingCart, CheckCircle2 } from 'lucide-react';

interface SignalTableProps {
  signals: Signal[];
  onPaperBuy?: (signal: Signal) => void;
  activeSignalIds?: Set<string>;
}

export const SignalTable: React.FC<SignalTableProps> = ({ signals, onPaperBuy, activeSignalIds }) => {
  if (signals.length === 0) {
    return (
      <div className="bg-dark-800 border border-dark-700 rounded-2xl p-12 text-center text-slate-400">
        <p className="text-base font-semibold mb-1">No Active Signals Matching Current Filter</p>
        <p className="text-xs text-slate-500">
          The background scanner cycles every ~8 seconds. Signals will appear here as soon as a candle trigger fires.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-100 dark:bg-dark-900 border-b border-slate-200 dark:border-dark-700 text-slate-600 dark:text-slate-400 uppercase tracking-wider font-semibold">
            <tr>
              <th className="py-3 px-4">Instrument</th>
              <th className="py-3 px-4">Setup</th>
              <th className="py-3 px-4">Direction</th>
              <th className="py-3 px-4">Strike / Lot</th>
              <th className="py-3 px-4">Spot Levels (Trigger / SL / T1)</th>
              <th className="py-3 px-4">Option Est. Entry</th>
              <th className="py-3 px-4">Option SL (Pts)</th>
              <th className="py-3 px-4">Option T1 (Pts)</th>
              <th className="py-3 px-4">RSI / BW</th>
              <th className="py-3 px-4">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-dark-700/60 text-slate-800 dark:text-slate-200">
            {signals.map((sig) => {
              const isCE = sig.option_type === 'CE';
              const rec = sig.strike_recommendation;
              const ind = sig.indicators_snapshot;
              const isBought = activeSignalIds?.has(sig.id) || false;

              return (
                <tr key={sig.id} className="hover:bg-slate-50 dark:hover:bg-dark-700/40 transition">
                  {/* Instrument */}
                  <td className="py-3 px-4 font-extrabold text-slate-900 dark:text-white">
                    {sig.symbol}
                    <span className="ml-2 text-[10px] text-cyan-600 dark:text-cyan-400 font-mono font-normal">
                      [{sig.timeframe}]
                    </span>
                  </td>

                  {/* Setup */}
                  <td className="py-3 px-4 text-slate-700 dark:text-slate-300 font-medium">
                    {sig.setup_type}
                  </td>

                  {/* Direction */}
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-black ${
                        isCE
                          ? 'bg-emerald-50 dark:bg-emerald-950/80 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400'
                          : 'bg-rose-50 dark:bg-rose-950/80 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-400'
                      }`}
                    >
                      {isCE ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      BUY {sig.option_type}
                    </span>
                  </td>

                  {/* Strike & Lot */}
                  <td className="py-3 px-4 font-mono font-bold text-cyan-700 dark:text-cyan-300">
                    {rec.strike_symbol}
                    <span className="block text-[10px] font-normal text-slate-500 dark:text-slate-400">
                      Lot Size: {rec.lot_size} Qty
                    </span>
                  </td>

                  {/* Spot Levels */}
                  <td className="py-3 px-4 font-mono">
                    {sig.setup_type.includes('Setup 5') ? (
                      <div>
                        <span className="text-cyan-700 dark:text-cyan-300 block font-bold">Opt: ₹{sig.entry_price}</span>
                        <span className="text-[10px] text-slate-500 dark:text-slate-400">Spot Ref: ₹{rec.underlying_price}</span>
                      </div>
                    ) : (
                      <div>
                        <span className="text-slate-900 dark:text-white block font-bold">Trigger: ₹{sig.entry_price}</span>
                        <div className="flex items-center gap-2 text-[10px] mt-0.5">
                          <span className="text-rose-600 dark:text-rose-400">SL: ₹{sig.stop_loss}</span>
                          <span className="text-emerald-600 dark:text-emerald-400">T1: ₹{sig.target_1}</span>
                          <span className="text-emerald-600/80 dark:text-emerald-400/80">T2: ₹{sig.target_2}</span>
                        </div>
                      </div>
                    )}
                  </td>

                  {/* Option Entry */}
                  <td className="py-3 px-4 font-mono font-black text-cyan-700 dark:text-cyan-300">
                    ₹{rec.estimated_option_entry}
                  </td>

                  {/* Option SL */}
                  <td className="py-3 px-4 font-mono text-rose-600 dark:text-rose-400">
                    ₹{rec.option_sl_price}
                    <span className="block text-[10px] text-slate-500">(-{rec.option_sl_pts}p risk)</span>
                  </td>

                  {/* Option T1 */}
                  <td className="py-3 px-4 font-mono text-emerald-600 dark:text-emerald-400">
                    ₹{rec.option_target_1_price}
                    <span className="block text-[10px] text-slate-500">(+{rec.option_target_1_pts}p gain)</span>
                  </td>

                  {/* RSI / BW */}
                  <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-300">
                    <div>RSI: {ind?.rsi != null ? ind.rsi.toFixed(1) : '-'}</div>
                    <div className="text-[10px] text-slate-500 dark:text-slate-400">
                      BW: {ind?.bandwidth != null ? `${ind.bandwidth.toFixed(2)}%` : '-'}
                    </div>
                  </td>

                  {/* Action */}
                  <td className="py-3 px-4">
                    {onPaperBuy && (
                      isBought ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-100 dark:bg-emerald-950/80 border border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300 font-bold text-xs whitespace-nowrap">
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                          In Portfolio
                        </span>
                      ) : (
                        <button
                          onClick={() => onPaperBuy(sig)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white rounded-lg text-xs font-bold transition active:scale-95 whitespace-nowrap shadow-sm shadow-cyan-600/20"
                        >
                          <ShoppingCart className="h-3.5 w-3.5" />
                          Paper Buy
                        </button>
                      )
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
};
