import React from 'react';
import { Signal } from '../types';
import { Target, ShieldAlert, ArrowUpRight, ArrowDownRight, Info, ShoppingCart, CheckCircle2 } from 'lucide-react';

interface SignalCardProps {
  signal: Signal;
  onPaperBuy?: (signal: Signal) => void;
  isBought?: boolean;
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal, onPaperBuy, isBought = false }) => {
  const isCE = signal.option_type === 'CE';
  const rec = signal.strike_recommendation;
  const ind = signal.indicators_snapshot;

  return (
    <div
      className={`border rounded-2xl p-5 transition-all duration-300 relative overflow-hidden flex flex-col justify-between ${
        isCE
          ? 'bg-gradient-to-b from-dark-800 to-emerald-950/10 border-emerald-800/60 hover:border-emerald-500/80 shadow-lg shadow-emerald-950/20'
          : 'bg-gradient-to-b from-dark-800 to-rose-950/10 border-rose-800/60 hover:border-rose-500/80 shadow-lg shadow-rose-950/20'
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
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-dark-900 border border-dark-700 text-slate-400 font-mono">
                Lot: {rec.lot_size}
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
            <span className="text-slate-400 font-medium">Recommended Strike (ITM)</span>
            <span className="text-[10px] font-mono text-cyan-400">ATM: ₹{rec.atm_strike}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-base font-black font-mono text-cyan-300">
              {rec.strike_symbol}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
              Official Lot: {rec.lot_size}
            </span>
          </div>
        </div>

        {/* 1. Underlying Spot Levels (Trigger, SL, T1, T2) */}
        <div className="mb-2">
          <div className="text-[10px] uppercase font-bold text-slate-500 mb-1 tracking-wider">
            Underlying Spot Levels
          </div>
          <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
            <div className="bg-dark-900/60 border border-dark-700 rounded-lg p-1.5">
              <span className="block text-[9px] text-slate-400 mb-0.5">Spot Trigger</span>
              <span className="font-bold font-mono text-white text-[11px]">₹{signal.entry_price}</span>
            </div>

            <div className="bg-rose-950/20 border border-rose-900/40 rounded-lg p-1.5">
              <span className="block text-[9px] text-rose-300 flex items-center justify-center gap-0.5 mb-0.5">
                <ShieldAlert className="h-2.5 w-2.5" /> Spot SL
              </span>
              <span className="font-bold font-mono text-rose-400 text-[11px]">₹{signal.stop_loss}</span>
            </div>

            <div className="bg-emerald-950/20 border border-emerald-900/40 rounded-lg p-1.5">
              <span className="block text-[9px] text-emerald-300 flex items-center justify-center gap-0.5 mb-0.5">
                <Target className="h-2.5 w-2.5" /> Spot T1
              </span>
              <span className="font-bold font-mono text-emerald-400 text-[11px]">₹{signal.target_1}</span>
            </div>

            <div className="bg-emerald-950/10 border border-emerald-900/30 rounded-lg p-1.5">
              <span className="block text-[9px] text-emerald-400/80 mb-0.5">Spot T2</span>
              <span className="font-bold font-mono text-emerald-400 text-[11px]">₹{signal.target_2}</span>
            </div>
          </div>
        </div>

        {/* 2. Option Premium Levels (Delta ~ 0.55) */}
        <div className="mb-3">
          <div className="text-[10px] uppercase font-bold text-cyan-500/80 mb-1 tracking-wider">
            Option Premium Levels (Δ ~0.55)
          </div>
          <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
            <div className="bg-cyan-950/20 border border-cyan-900/40 rounded-lg p-1.5">
              <span className="block text-[9px] text-cyan-300 mb-0.5">Est. Entry</span>
              <span className="font-black font-mono text-cyan-300 text-[11px]">₹{rec.estimated_option_entry}</span>
            </div>

            <div className="bg-rose-950/30 border border-rose-800/50 rounded-lg p-1.5">
              <span className="block text-[9px] text-rose-300 mb-0.5 truncate" title={`-${rec.option_sl_pts}p risk`}>
                SL (-{rec.option_sl_pts}p)
              </span>
              <span className="font-black font-mono text-rose-400 text-[11px]">₹{rec.option_sl_price}</span>
            </div>

            <div className="bg-emerald-950/30 border border-emerald-800/50 rounded-lg p-1.5">
              <span className="block text-[9px] text-emerald-300 mb-0.5 truncate" title={`+${rec.option_target_1_pts}p gain`}>
                T1 (+{rec.option_target_1_pts}p)
              </span>
              <span className="font-black font-mono text-emerald-400 text-[11px]">₹{rec.option_target_1_price}</span>
            </div>

            <div className="bg-emerald-950/20 border border-emerald-800/40 rounded-lg p-1.5">
              <span className="block text-[9px] text-emerald-400/80 mb-0.5 truncate" title={`+${rec.option_target_2_pts}p gain`}>
                T2 (+{rec.option_target_2_pts}p)
              </span>
              <span className="font-black font-mono text-emerald-400 text-[11px]">₹{rec.option_target_2_price}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer Snapshot & CTA */}
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

        <p className="text-[11px] text-slate-300 italic flex items-center gap-1.5 mb-3">
          <Info className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
          {signal.rationale}
        </p>

        {/* 1-Click Paper Buy Button */}
        {onPaperBuy && (
          <button
            onClick={() => !isBought && onPaperBuy(signal)}
            disabled={isBought}
            className={`w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-bold transition active:scale-95 ${
              isBought
                ? 'bg-emerald-950/80 border border-emerald-700 text-emerald-300 cursor-default'
                : 'bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-md shadow-cyan-600/20'
            }`}
          >
            {isBought ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                Active in Paper Portfolio ({rec.lot_size} Qty)
              </>
            ) : (
              <>
                <ShoppingCart className="h-3.5 w-3.5" />
                1-Click Paper Buy (1 Lot: {rec.lot_size} Qty)
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
