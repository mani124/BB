import React from 'react';
import { Signal } from '../types';
import { Target, ShieldAlert, ArrowUpRight, ArrowDownRight, Info } from 'lucide-react';

interface SignalCardProps {
  signal: Signal;
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal }) => {
  const isCE = signal.option_type === 'CE';
  const rec = signal.strike_recommendation;
  const ind = signal.indicators_snapshot;

  return (
    <div
      className={`border rounded-2xl p-5 transition-all duration-300 relative overflow-hidden flex flex-col justify-between ${
        isCE
          ? 'bg-gradient-to-b from-dark-800 to-emerald-950/10 border-emerald-800/60 hover:border-emerald-500/80'
          : 'bg-gradient-to-b from-dark-800 to-rose-950/10 border-rose-800/60 hover:border-rose-500/80'
      }`}
    >
      {/* Top Header */}
      <div>
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base text-white tracking-wide">
                {signal.symbol}
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-dark-900 border border-dark-700 text-cyan-300 font-mono">
                {signal.timeframe}
              </span>
            </div>
            <span className="text-[11px] text-slate-400 font-medium">
              {signal.setup_type}
            </span>
          </div>

          {/* Direction Pill */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-black shadow-md ${
              isCE
                ? 'bg-emerald-600 text-white shadow-emerald-600/30'
                : 'bg-rose-600 text-white shadow-rose-600/30'
            }`}
          >
            {isCE ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
            BUY {signal.option_type}
          </div>
        </div>

        {/* Recommended Option Strike Hero Box */}
        <div className="bg-dark-900/90 border border-dark-700/80 rounded-xl p-3.5 mb-3">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-400 font-medium">Option Recommendation</span>
            <span className="text-[10px] font-mono text-cyan-400">ATM: ₹{rec.atm_strike}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-base font-black font-mono text-cyan-300">
              {rec.strike_symbol}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
              1-Strike ITM
            </span>
          </div>
        </div>

        {/* Levels Grid */}
        <div className="grid grid-cols-3 gap-2 text-center mb-3 text-xs">
          <div className="bg-dark-900/60 border border-dark-700 rounded-lg p-2">
            <span className="block text-[10px] text-slate-400 mb-0.5">Entry Trigger</span>
            <span className="font-black font-mono text-white">₹{signal.entry_price}</span>
          </div>

          <div className="bg-rose-950/20 border border-rose-900/40 rounded-lg p-2">
            <span className="block text-[10px] text-rose-300 flex items-center justify-center gap-0.5 mb-0.5">
              <ShieldAlert className="h-3 w-3" /> Stop-Loss
            </span>
            <span className="font-black font-mono text-rose-400">₹{signal.stop_loss}</span>
          </div>

          <div className="bg-emerald-950/20 border border-emerald-900/40 rounded-lg p-2">
            <span className="block text-[10px] text-emerald-300 flex items-center justify-center gap-0.5 mb-0.5">
              <Target className="h-3 w-3" /> Target 1 (1:1.5)
            </span>
            <span className="font-black font-mono text-emerald-400">₹{signal.target_1}</span>
          </div>
        </div>

        {/* Target 2 & Risk points */}
        <div className="flex items-center justify-between text-[11px] px-2 py-1 bg-dark-900/40 rounded-lg text-slate-400 mb-3">
          <span>
            Target 2 (1:2.5): <strong className="text-emerald-400 font-mono">₹{signal.target_2}</strong>
          </span>
          <span>
            Underlying Risk: <strong className="text-rose-400 font-mono">{rec.risk} pts</strong>
          </span>
        </div>
      </div>

      {/* Footer Snapshot & Rationale */}
      <div className="pt-2.5 border-t border-dark-700/60">
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400 mb-2 font-mono">
          <span className="px-1.5 py-0.5 rounded bg-dark-900 border border-dark-700">
            RSI: {ind.rsi.toFixed(1)}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-dark-900 border border-dark-700">
            BW: {ind.bandwidth.toFixed(2)}%
          </span>
          <span className="px-1.5 py-0.5 rounded bg-dark-900 border border-dark-700">
            %B: {ind.percent_b.toFixed(2)}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-dark-900 border border-dark-700">
            VWAP: ₹{ind.vwap.toFixed(1)}
          </span>
        </div>

        <p className="text-[11px] text-slate-300 italic flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
          {signal.rationale}
        </p>
      </div>
    </div>
  );
};
