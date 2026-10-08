import React from 'react';
import { SetupType, OptionType } from '../types';
import { Filter, Flame, Compass, RefreshCw, Clock } from 'lucide-react';

interface SetupFilterTabsProps {
  selectedSetup: string;
  onSelectSetup: (setup: string) => void;
  selectedOptionType: string;
  onSelectOptionType: (opt: string) => void;
  selectedInstrumentType: string;
  onSelectInstrumentType: (inst: string) => void;
  selectedTimeframe: string;
  onSelectTimeframe: (tf: string) => void;
  totalSignals: number;
}

export const SetupFilterTabs: React.FC<SetupFilterTabsProps> = ({
  selectedSetup,
  onSelectSetup,
  selectedOptionType,
  onSelectOptionType,
  selectedInstrumentType,
  onSelectInstrumentType,
  selectedTimeframe,
  onSelectTimeframe,
  totalSignals,
}) => {
  const setups: { key: string; label: string; icon: any }[] = [
    { key: 'ALL', label: 'All Setups', icon: Filter },
    { key: 'Setup 1: BB Squeeze Breakout', label: 'Setup 1: Squeeze Breakout', icon: Flame },
    { key: 'Setup 3: W/M Reversal', label: 'Setup 3: W/M Reversal', icon: Compass },
    { key: 'Setup 2: Walking the Bands (9 EMA)', label: 'Setup 2: Walking Bands (9 EMA)', icon: RefreshCw },
    { key: 'Setup 4: 9:30 AM Opening Range Breakout', label: 'Setup 4: 9:30 AM ORB', icon: Clock },
  ];

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-2xl p-4 mb-6 space-y-4">
      {/* Top Row: Setups */}
      <div className="flex flex-wrap items-center gap-2">
        {setups.map(({ key, label, icon: Icon }) => {
          const active = selectedSetup === key;
          return (
            <button
              key={key}
              onClick={() => onSelectSetup(key)}
              className={`flex items-center gap-2 text-xs font-bold px-3.5 py-2 rounded-xl transition ${
                active
                  ? 'bg-cyan-600 text-white shadow-md shadow-cyan-600/30'
                  : 'bg-dark-900/90 text-slate-400 hover:text-slate-200 border border-dark-700 hover:border-dark-600'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          );
        })}
      </div>

      <div className="h-[1px] bg-dark-700/60" />

      {/* Bottom Row: Option Type (CE/PE), Instruments & Timeframes */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* CE vs PE */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-400">Direction:</span>
          <div className="flex bg-dark-900 border border-dark-700 rounded-xl p-1">
            {['ALL', 'CE', 'PE'].map((opt) => (
              <button
                key={opt}
                onClick={() => onSelectOptionType(opt)}
                className={`text-xs font-bold px-3 py-1 rounded-lg transition ${
                  selectedOptionType === opt
                    ? opt === 'CE'
                      ? 'bg-emerald-600 text-white'
                      : opt === 'PE'
                      ? 'bg-rose-600 text-white'
                      : 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt === 'ALL' ? 'Both (CE+PE)' : opt === 'CE' ? 'Calls (CE)' : 'Puts (PE)'}
              </button>
            ))}
          </div>
        </div>

        {/* Instruments: Indices vs Stocks */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-400">Universe:</span>
          <div className="flex bg-dark-900 border border-dark-700 rounded-xl p-1">
            {[
              { key: 'ALL', label: 'All' },
              { key: 'INDEX', label: 'Indices (4)' },
              { key: 'STOCK', label: 'Stocks (~30)' },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => onSelectInstrumentType(key)}
                className={`text-xs font-bold px-3 py-1 rounded-lg transition ${
                  selectedInstrumentType === key
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Timeframes */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-400">Timeframe:</span>
          <div className="flex bg-dark-900 border border-dark-700 rounded-xl p-1">
            {['ALL', '5m', '15m'].map((tf) => (
              <button
                key={tf}
                onClick={() => onSelectTimeframe(tf)}
                className={`text-xs font-bold px-3 py-1 rounded-lg transition ${
                  selectedTimeframe === tf
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Signal counter */}
        <div className="text-xs font-bold text-slate-300 bg-dark-900/80 px-3 py-1.5 rounded-xl border border-dark-700">
          Filtered Signals: <span className="text-cyan-400 font-mono text-sm">{totalSignals}</span>
        </div>
      </div>
    </div>
  );
};
