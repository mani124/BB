import React from 'react';
import { Signal } from '../types';
import { Target, ShieldAlert, ArrowUpRight, ArrowDownRight, Info, ShoppingCart, CheckCircle2 } from 'lucide-react';
import { SetupBadge } from './SignalsFeed';

interface SignalCardProps {
  signal: Signal;
  onPaperBuy?: (signal: Signal) => void;
  isBought?: boolean;
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal, onPaperBuy, isBought = false }) => {
  const isCE = signal.option_type === 'CE';
  const rec = signal.strike_recommendation;
  const ind = signal.indicators_snapshot;
  const isSetup5 = signal.setup_type.includes('Setup 5');

  return (
    <div
      className={`border rounded-2xl p-5 transition-all duration-300 relative overflow-hidden flex flex-col justify-between shadow-sm ${
        isCE
          ? 'bg-gradient-to-b from-white to-emerald-50/50 border-emerald-300 hover:border-emerald-500 hover:shadow-emerald-500/10 dark:from-dark-800 dark:to-emerald-950/10 dark:border-emerald-800/60 dark:hover:border-emerald-500/80'
          : 'bg-gradient-to-b from-white to-rose-50/50 border-rose-300 hover:border-rose-500 hover:shadow-rose-500/10 dark:from-dark-800 dark:to-rose-950/10 dark:border-rose-800/60 dark:hover:border-rose-500/80'
      }`}
    >
      {/* Top Header */}
      <div>
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base text-slate-900 dark:text-white tracking-wide">
                {signal.symbol}
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700 text-cyan-700 dark:text-cyan-300 font-mono">
                {signal.timeframe}
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700 text-slate-600 dark:text-slate-400 font-mono">
                Lot: {rec.lot_size}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 flex-wrap">
              <SetupBadge setupType={signal.setup_type} />
              {signal.is_confirmed === false && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 border border-amber-300 dark:border-amber-700/60 text-amber-800 dark:text-amber-300">
                  ⏳ Provisional (Forms Intrabar)
                </span>
              )}
            </div>
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
        <div className="bg-slate-50 dark:bg-dark-900/90 border border-slate-200 dark:border-dark-700/80 rounded-xl p-3.5 mb-3 shadow-inner">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-600 dark:text-slate-400 font-medium">Recommended Strike (ITM)</span>
            <span className="text-[10px] font-mono text-cyan-600 dark:text-cyan-400">ATM: ₹{rec.atm_strike}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-base font-black font-mono text-cyan-700 dark:text-cyan-300">
              {rec.strike_symbol}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-100 dark:bg-cyan-950 border border-cyan-300 dark:border-cyan-800 text-cyan-800 dark:text-cyan-300 font-bold">
              Official Lot: {rec.lot_size}
            </span>
          </div>
        </div>

        {/* If Setup 5: Direct Option Chart Levels with Underlying Spot Reference */}
        {isSetup5 ? (
          <div className="mb-3">
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-cyan-700 dark:text-cyan-400 mb-1 tracking-wider">
              <span>Option Chart Scalp Levels</span>
              <span className="font-mono text-[9px] text-slate-500 dark:text-slate-400">
                Spot Ref: ₹{rec.underlying_price}
              </span>
            </div>
            <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
              <div className="bg-cyan-50 dark:bg-cyan-950/20 border border-cyan-200 dark:border-cyan-900/40 rounded-lg p-1.5">
                <span className="block text-[9px] text-cyan-700 dark:text-cyan-300 mb-0.5">Opt Trigger</span>
                <span className="font-black font-mono text-cyan-700 dark:text-cyan-300 text-[11px]">₹{signal.entry_price}</span>
              </div>
              <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/50 rounded-lg p-1.5">
                <span className="block text-[9px] text-rose-700 dark:text-rose-300 mb-0.5 truncate" title={`-${rec.option_sl_pts}p risk`}>
                  Opt SL (-{rec.option_sl_pts}p)
                </span>
                <span className="font-black font-mono text-rose-600 dark:text-rose-400 text-[11px]">₹{signal.stop_loss}</span>
              </div>
              <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 rounded-lg p-1.5">
                <span className="block text-[9px] text-emerald-700 dark:text-emerald-300 mb-0.5 truncate" title={`+${rec.option_target_1_pts}p gain`}>
                  Opt T1 (+{rec.option_target_1_pts}p)
                </span>
                <span className="font-black font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{signal.target_1}</span>
              </div>
              <div className="bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/40 rounded-lg p-1.5">
                <span className="block text-[9px] text-emerald-700/80 dark:text-emerald-400/80 mb-0.5 truncate" title={`+${rec.option_target_2_pts}p gain`}>
                  Opt T2 (+{rec.option_target_2_pts}p)
                </span>
                <span className="font-black font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{signal.target_2}</span>
              </div>
            </div>
            <div className="mt-1 text-[9px] text-right text-emerald-600 dark:text-emerald-400 font-medium">
              ⚡ Option Chart Scalp (Exits tracked strictly on option premium)
            </div>
          </div>
        ) : (
          <>
            {/* 1. Underlying Spot Levels (Trigger, SL, T1, T2) */}
            <div className="mb-2">
              <div className="text-[10px] uppercase font-bold text-slate-500 mb-1 tracking-wider">
                Underlying Spot Levels
              </div>
              <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
                <div className="bg-slate-50 dark:bg-dark-900/60 border border-slate-200 dark:border-dark-700 rounded-lg p-1.5">
                  <span className="block text-[9px] text-slate-500 dark:text-slate-400 mb-0.5">Spot Trigger</span>
                  <span className="font-bold font-mono text-slate-900 dark:text-white text-[11px]">₹{signal.entry_price}</span>
                </div>

                <div className="bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/40 rounded-lg p-1.5">
                  <span className="block text-[9px] text-rose-700 dark:text-rose-300 flex items-center justify-center gap-0.5 mb-0.5">
                    <ShieldAlert className="h-2.5 w-2.5" /> Spot SL
                  </span>
                  <span className="font-bold font-mono text-rose-600 dark:text-rose-400 text-[11px]">₹{signal.stop_loss}</span>
                </div>

                <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/40 rounded-lg p-1.5">
                  <span className="block text-[9px] text-emerald-700 dark:text-emerald-300 flex items-center justify-center gap-0.5 mb-0.5">
                    <Target className="h-2.5 w-2.5" /> Spot T1
                  </span>
                  <span className="font-bold font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{signal.target_1}</span>
                </div>

                <div className="bg-emerald-50/60 dark:bg-emerald-950/10 border border-emerald-200 dark:border-emerald-900/30 rounded-lg p-1.5">
                  <span className="block text-[9px] text-emerald-700/80 dark:text-emerald-400/80 mb-0.5">Spot T2</span>
                  <span className="font-bold font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{signal.target_2}</span>
                </div>
              </div>
            </div>

            {/* 2. Option Premium Levels (Delta ~ 0.55 or Live Greeks) */}
            <div className="mb-3">
              <div className="flex items-center justify-between text-[10px] uppercase font-bold text-cyan-700 dark:text-cyan-500/80 mb-1 tracking-wider">
                <span>Option Premium {rec.is_live_quote ? (rec.real_delta ? `(Δ ${rec.real_delta})` : '(Live Quote)') : '(Δ ~0.55)'}</span>
                {rec.is_live_quote ? (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-black text-[9px] border border-emerald-500/30">
                    LIVE NSE_FNO
                  </span>
                ) : null}
              </div>
              <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
                <div className="bg-cyan-50 dark:bg-cyan-950/20 border border-cyan-200 dark:border-cyan-900/40 rounded-lg p-1.5">
                  <span className="block text-[9px] text-cyan-700 dark:text-cyan-300 mb-0.5">
                    {rec.is_live_quote ? 'Live Ask' : 'Est. Entry'}
                  </span>
                  <span className="font-black font-mono text-cyan-700 dark:text-cyan-300 text-[11px]">₹{rec.estimated_option_entry}</span>
                </div>

                <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/50 rounded-lg p-1.5">
                  <span className="block text-[9px] text-rose-700 dark:text-rose-300 mb-0.5 truncate" title={`-${rec.option_sl_pts}p risk`}>
                    SL (-{rec.option_sl_pts}p)
                  </span>
                  <span className="font-black font-mono text-rose-600 dark:text-rose-400 text-[11px]">₹{rec.option_sl_price}</span>
                </div>

                <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 rounded-lg p-1.5">
                  <span className="block text-[9px] text-emerald-700 dark:text-emerald-300 mb-0.5 truncate" title={`+${rec.option_target_1_pts}p gain`}>
                    T1 (+{rec.option_target_1_pts}p)
                  </span>
                  <span className="font-black font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{rec.option_target_1_price}</span>
                </div>

                <div className="bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/40 rounded-lg p-1.5">
                  <span className="block text-[9px] text-emerald-700/80 dark:text-emerald-400/80 mb-0.5 truncate" title={`+${rec.option_target_2_pts}p gain`}>
                    T2 (+{rec.option_target_2_pts}p)
                  </span>
                  <span className="font-black font-mono text-emerald-600 dark:text-emerald-400 text-[11px]">₹{rec.option_target_2_price}</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Footer Snapshot & CTA */}
      <div className="pt-2.5 border-t border-slate-200 dark:border-dark-700/60">
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-600 dark:text-slate-400 mb-2 font-mono">
          <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700">
            RSI: {ind?.rsi != null ? ind.rsi.toFixed(1) : '-'}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700">
            BW: {ind?.bandwidth != null ? `${ind.bandwidth.toFixed(2)}%` : '-'}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700">
            %B: {ind?.percent_b != null ? ind.percent_b.toFixed(2) : '-'}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700">
            VWAP: ₹{ind?.vwap != null ? ind.vwap.toFixed(1) : '-'}
          </span>
        </div>

        <p className="text-[11px] text-slate-600 dark:text-slate-300 italic flex items-center gap-1.5 mb-3">
          <Info className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400 shrink-0" />
          {signal.rationale}
        </p>

        {/* 1-Click Paper Buy Button */}
        {onPaperBuy && (
          <button
            onClick={() => !isBought && signal.is_confirmed !== false && onPaperBuy(signal)}
            disabled={isBought || signal.is_confirmed === false}
            className={`w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-bold transition active:scale-95 shadow-sm ${
              isBought
                ? 'bg-emerald-100 dark:bg-emerald-950/80 border border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300 cursor-default'
                : signal.is_confirmed === false
                ? 'bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-700/60 text-amber-700 dark:text-amber-300 cursor-not-allowed'
                : 'bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-md shadow-cyan-600/20'
            }`}
          >
            {isBought ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                Active in Paper Portfolio
              </>
            ) : signal.is_confirmed === false ? (
              <>
                <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
                Awaiting Bar Close (Provisional)
              </>
            ) : (
              <>
                <ShoppingCart className="h-3.5 w-3.5" />
                1-Click Paper Buy
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
