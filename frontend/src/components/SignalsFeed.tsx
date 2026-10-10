import React from 'react';
import { Signal, SetupType } from '../types';
import { SignalCard } from './SignalCard';
import { SignalTable } from './SignalTable';

export interface SetupBadgeConfig {
  label: string;
  badgeStyle: string;
  dotColor: string;
}

/**
 * Returns distinct styling, label, and accent colors for all strategy setups (1 to 8).
 * Setups 6, 7, and 8 are Mean-Reversion Snapback setups:
 * - Setup 6: Pin Bar Exhaustion Snapback (Amber/Purple accent)
 * - Setup 7: 2.5σ Inside Bar Snapback (Indigo accent)
 * - Setup 8: Climax Divergence Fade (Cyan accent)
 */
export const getSetupBadgeConfig = (setupType: string | SetupType): SetupBadgeConfig => {
  const s = (setupType || '').toUpperCase();

  if (s.includes('SETUP_6') || s.includes('SETUP 6') || s.includes('PINBAR') || s.includes('PIN_BAR') || s.includes('PIN BAR')) {
    return {
      label: 'Setup 6: Pin Bar Snapback',
      badgeStyle: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-purple-950/50 dark:text-purple-300 dark:border-purple-800/60',
      dotColor: 'bg-amber-500 dark:bg-purple-400',
    };
  }

  if (s.includes('SETUP_7') || s.includes('SETUP 7') || s.includes('INSIDE_BAR') || s.includes('INSIDE BAR')) {
    return {
      label: 'Setup 7: Inside Bar Snapback',
      badgeStyle: 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800/60',
      dotColor: 'bg-indigo-500 dark:bg-indigo-400',
    };
  }

  if (s.includes('SETUP_8') || s.includes('SETUP 8') || s.includes('DIVERGENCE') || s.includes('CLIMAX')) {
    return {
      label: 'Setup 8: Climax Divergence',
      badgeStyle: 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/50 dark:text-cyan-300 dark:border-cyan-800/60',
      dotColor: 'bg-cyan-500 dark:bg-cyan-400',
    };
  }

  if (s.includes('SETUP_1') || s.includes('SETUP 1') || s.includes('SQUEEZE')) {
    return {
      label: 'Setup 1: Squeeze Breakout',
      badgeStyle: 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/50 dark:text-orange-300 dark:border-orange-800/60',
      dotColor: 'bg-orange-500',
    };
  }

  if (s.includes('SETUP_2') || s.includes('SETUP 2') || s.includes('WALKING')) {
    return {
      label: 'Setup 2: Walking Bands (9 EMA)',
      badgeStyle: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800/60',
      dotColor: 'bg-emerald-500',
    };
  }

  if (s.includes('SETUP_3') || s.includes('SETUP 3') || s.includes('REVERSAL') || s.includes('W/M')) {
    return {
      label: 'Setup 3: W/M Reversal',
      badgeStyle: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800/60',
      dotColor: 'bg-blue-500',
    };
  }

  if (s.includes('SETUP_4') || s.includes('SETUP 4') || s.includes('ORB')) {
    return {
      label: 'Setup 4: 9:30 AM ORB',
      badgeStyle: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/50 dark:text-sky-300 dark:border-sky-800/60',
      dotColor: 'bg-sky-500',
    };
  }

  if (s.includes('SETUP_5') || s.includes('SETUP 5') || s.includes('OPTION')) {
    return {
      label: 'Setup 5: Option Chart Scalp',
      badgeStyle: 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/50 dark:text-teal-300 dark:border-teal-800/60',
      dotColor: 'bg-teal-500',
    };
  }

  return {
    label: setupType || 'Standard Signal',
    badgeStyle: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-dark-900 dark:text-slate-300 dark:border-dark-700',
    dotColor: 'bg-slate-400',
  };
};

export interface SetupBadgeProps {
  setupType: string | SetupType;
  className?: string;
}

export const SetupBadge: React.FC<SetupBadgeProps> = ({ setupType, className = '' }) => {
  const { label, badgeStyle, dotColor } = getSetupBadgeConfig(setupType);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold border ${badgeStyle} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      {label}
    </span>
  );
};

export interface SignalsFeedProps {
  signals: Signal[];
  onPaperBuy?: (signal: Signal) => void;
  activeSignalIds?: Set<string>;
  viewMode?: 'grid' | 'table';
}

export const SignalsFeed: React.FC<SignalsFeedProps> = ({
  signals,
  onPaperBuy,
  activeSignalIds,
  viewMode = 'grid',
}) => {
  if (viewMode === 'table') {
    return (
      <SignalTable
        signals={signals}
        onPaperBuy={onPaperBuy}
        activeSignalIds={activeSignalIds}
      />
    );
  }

  if (signals.length === 0) {
    return (
      <div className="bg-white dark:bg-dark-800 border border-slate-200 dark:border-dark-700 rounded-2xl p-12 text-center text-slate-500 dark:text-slate-400 shadow-sm">
        <p className="text-base font-semibold mb-1 text-slate-800 dark:text-slate-200">
          No Active Signals Matching Current Filter
        </p>
        <p className="text-xs text-slate-500">
          The background scanner is actively monitoring. Signals will trigger as soon as a candle setup completes.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {signals.map((sig) => (
        <SignalCard
          key={sig.id}
          signal={sig}
          onPaperBuy={onPaperBuy}
          isBought={activeSignalIds?.has(sig.id)}
        />
      ))}
    </div>
  );
};
