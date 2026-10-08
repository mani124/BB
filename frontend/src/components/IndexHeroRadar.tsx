import React from 'react';
import { IndexRadarItem } from '../types';
import { TrendingUp, TrendingDown, Layers, Zap } from 'lucide-react';

interface IndexHeroRadarProps {
  radar: Record<string, IndexRadarItem>;
}

export const IndexHeroRadar: React.FC<IndexHeroRadarProps> = ({ radar }) => {
  const indexKeys = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX'];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {indexKeys.map((key) => {
        const item = radar[key] || {
          symbol: key,
          close: 0,
          change_pct: 0,
          percent_b: 0.5,
          bandwidth: 0,
          is_squeeze: false,
          vwap_bias: 'ABOVE_VWAP',
          rsi: 50,
          trend_state: 'RANGE',
        };

        const isPositive = item.change_pct >= 0;
        const isAboveVwap = item.vwap_bias === 'ABOVE_VWAP';

        return (
          <div
            key={key}
            className={`p-4 rounded-2xl border transition-all duration-300 relative overflow-hidden shadow-sm ${
              item.is_squeeze
                ? 'bg-gradient-to-br from-indigo-50/80 via-white to-indigo-50/30 border-indigo-300 dark:from-dark-800 dark:via-indigo-950/20 dark:to-dark-800 dark:border-indigo-600/60 dark:shadow-indigo-500/10'
                : 'bg-white dark:bg-dark-800/90 border-slate-200 dark:border-dark-700 hover:border-slate-300 dark:hover:border-dark-600'
            }`}
          >
            {/* Squeeze Indicator Pip */}
            {item.is_squeeze && (
              <div className="absolute top-0 right-0 bg-indigo-600 text-white text-[9px] font-black uppercase tracking-wider px-2.5 py-0.5 rounded-bl-lg shadow flex items-center gap-1">
                <Zap className="h-2.5 w-2.5" />
                BB SQUEEZE ACTIVE
              </div>
            )}

            <div className="flex items-center justify-between mb-2">
              <span className="font-extrabold text-sm tracking-wide text-slate-900 dark:text-white">
                {item.symbol}
              </span>
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded-md flex items-center gap-1 ${
                  isPositive
                    ? 'bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400'
                    : 'bg-rose-50 dark:bg-rose-950/70 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-400'
                }`}
              >
                {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                {isPositive ? '+' : ''}{item.change_pct.toFixed(2)}%
              </span>
            </div>

            <div className="flex items-baseline gap-2 mb-3">
              <span className="text-xl font-black font-mono tracking-tight text-slate-900 dark:text-white">
                ₹{item.close > 0 ? item.close.toLocaleString('en-IN') : '---'}
              </span>
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold uppercase">
                5m Candle
              </span>
            </div>

            {/* Bollinger %B Visual Meter */}
            <div className="mb-2.5">
              <div className="flex justify-between text-[10px] text-slate-500 dark:text-slate-400 mb-1">
                <span>BB %B: <strong className="text-slate-700 dark:text-slate-200">{item.percent_b.toFixed(2)}</strong></span>
                <span>BW: <strong className="text-slate-700 dark:text-slate-200">{item.bandwidth.toFixed(2)}%</strong></span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-dark-950 h-1.5 rounded-full overflow-hidden border border-slate-200 dark:border-dark-700">
                <div
                  className={`h-full transition-all duration-500 ${
                    item.percent_b > 1.0
                      ? 'bg-emerald-500 dark:bg-emerald-400'
                      : item.percent_b < 0.0
                      ? 'bg-rose-500 dark:bg-rose-400'
                      : 'bg-cyan-600 dark:bg-cyan-500'
                  }`}
                  style={{ width: `${Math.max(0, Math.min(100, item.percent_b * 100))}%` }}
                />
              </div>
            </div>

            {/* Pill Tags */}
            <div className="flex items-center gap-2 pt-1 border-t border-slate-100 dark:border-dark-700/60 text-[10px]">
              <span
                className={`px-2 py-0.5 rounded font-semibold ${
                  isAboveVwap
                    ? 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60'
                    : 'bg-rose-50 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60'
                }`}
              >
                {isAboveVwap ? '▲ Above VWAP' : '▼ Below VWAP'}
              </span>

              <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-dark-900 border border-slate-200 dark:border-dark-700 text-slate-700 dark:text-slate-300 font-mono">
                RSI: {item.rsi.toFixed(1)}
              </span>

              <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-dark-900/60 text-slate-500 dark:text-slate-400 font-mono ml-auto">
                {item.trend_state}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
