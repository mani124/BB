import React from 'react';
import { Signal } from '../types';
import { ArrowUpRight, ArrowDownRight, ShoppingCart } from 'lucide-react';

interface SignalTableProps {
  signals: Signal[];
  onPaperBuy?: (signal: Signal) => void;
}

export const SignalTable: React.FC<SignalTableProps> = ({ signals, onPaperBuy }) => {
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
    <div className="bg-dark-800 border border-dark-700 rounded-2xl overflow-hidden shadow-xl">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-dark-900 border-b border-dark-700 text-slate-400 uppercase tracking-wider font-semibold">
            <tr>
              <th className="py-3 px-4">Instrument</th>
              <th className="py-3 px-4">Setup</th>
              <th className="py-3 px-4">Direction</th>
              <th className="py-3 px-4">Strike / Lot</th>
              <th className="py-3 px-4">Spot Levels (Trigger / SL)</th>
              <th className="py-3 px-4">Option Est. Entry</th>
              <th className="py-3 px-4">Option SL (Pts)</th>
              <th className="py-3 px-4">Option T1 (Pts)</th>
              <th className="py-3 px-4">RSI / BW</th>
              <th className="py-3 px-4">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-700/60 text-slate-200">
            {signals.map((sig) => {
              const isCE = sig.option_type === 'CE';
              const rec = sig.strike_recommendation;
              const ind = sig.indicators_snapshot;

              return (
                <tr key={sig.id} className="hover:bg-dark-700/40 transition">
                  {/* Instrument */}
                  <td className="py-3 px-4 font-extrabold text-white">
                    {sig.symbol}
                    <span className="ml-2 text-[10px] text-cyan-400 font-mono font-normal">
                      [{sig.timeframe}]
                    </span>
                  </td>

                  {/* Setup */}
                  <td className="py-3 px-4 text-slate-300 font-medium">
                    {sig.setup_type}
                  </td>

                  {/* Direction */}
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-black ${
                        isCE
                          ? 'bg-emerald-950/80 border border-emerald-800 text-emerald-400'
                          : 'bg-rose-950/80 border border-rose-800 text-rose-400'
                      }`}
                    >
                      {isCE ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      BUY {sig.option_type}
                    </span>
                  </td>

                  {/* Strike & Lot */}
                  <td className="py-3 px-4 font-mono font-bold text-cyan-300">
                    {rec.strike_symbol}
                    <span className="block text-[10px] font-normal text-slate-400">
                      Lot Size: {rec.lot_size} Qty
                    </span>
                  </td>

                  {/* Spot Levels */}
                  <td className="py-3 px-4 font-mono">
                    <span className="text-white block font-bold">₹{sig.entry_price}</span>
                    <span className="text-rose-400 text-[10px] block">SL: ₹{sig.stop_loss}</span>
                  </td>

                  {/* Option Entry */}
                  <td className="py-3 px-4 font-mono font-black text-cyan-300">
                    ₹{rec.estimated_option_entry}
                  </td>

                  {/* Option SL */}
                  <td className="py-3 px-4 font-mono text-rose-400">
                    ₹{rec.option_sl_price}
                    <span className="block text-[10px] text-slate-500">(-{rec.option_sl_pts}p)</span>
                  </td>

                  {/* Option T1 */}
                  <td className="py-3 px-4 font-mono text-emerald-400">
                    ₹{rec.option_target_1_price}
                    <span className="block text-[10px] text-slate-500">(+{rec.option_target_1_pts}p)</span>
                  </td>

                  {/* RSI / BW */}
                  <td className="py-3 px-4 font-mono text-slate-300">
                    <div>RSI: {ind.rsi.toFixed(1)}</div>
                    <div className="text-[10px] text-slate-400">BW: {ind.bandwidth.toFixed(2)}%</div>
                  </td>

                  {/* Action */}
                  <td className="py-3 px-4">
                    {onPaperBuy && (
                      <button
                        onClick={() => onPaperBuy(sig)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-bold transition active:scale-95 whitespace-nowrap"
                      >
                        <ShoppingCart className="h-3.5 w-3.5" />
                        Paper Buy
                      </button>
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
