import React from 'react';
import { Signal } from '../types';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface SignalTableProps {
  signals: Signal[];
}

export const SignalTable: React.FC<SignalTableProps> = ({ signals }) => {
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
              <th className="py-3 px-4">Recommended Strike</th>
              <th className="py-3 px-4">Trigger Price</th>
              <th className="py-3 px-4">Stop-Loss</th>
              <th className="py-3 px-4">Target 1 (1:1.5)</th>
              <th className="py-3 px-4">Target 2 (1:2.5)</th>
              <th className="py-3 px-4">RSI</th>
              <th className="py-3 px-4">BandWidth</th>
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

                  {/* Strike */}
                  <td className="py-3 px-4 font-mono font-bold text-cyan-300">
                    {rec.strike_symbol}
                    <span className="block text-[10px] font-normal text-slate-400">
                      ATM: ₹{rec.atm_strike}
                    </span>
                  </td>

                  {/* Trigger */}
                  <td className="py-3 px-4 font-mono font-bold text-white">
                    ₹{sig.entry_price}
                  </td>

                  {/* SL */}
                  <td className="py-3 px-4 font-mono font-bold text-rose-400">
                    ₹{sig.stop_loss}
                  </td>

                  {/* Target 1 */}
                  <td className="py-3 px-4 font-mono font-bold text-emerald-400">
                    ₹{sig.target_1}
                  </td>

                  {/* Target 2 */}
                  <td className="py-3 px-4 font-mono font-bold text-emerald-300">
                    ₹{sig.target_2}
                  </td>

                  {/* RSI */}
                  <td className="py-3 px-4 font-mono text-slate-300">
                    {ind.rsi.toFixed(1)}
                  </td>

                  {/* BandWidth */}
                  <td className="py-3 px-4 font-mono text-slate-300">
                    {ind.bandwidth.toFixed(2)}%
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
