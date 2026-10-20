import React from 'react';
import type { PaperPosition, Signal } from '../types';
import type { DashboardCandidate, DashboardTrade } from '../types/dashboard';
import { SignalDetails } from './SignalDetails';
import { PositionChartModal } from './PositionChartModal';
import { WatchCandidateDetail } from './WatchCandidateDetail';
import { formatCurrency, pnlClass } from './format';
import { setupCode } from './setupCode';

export type Selection =
  | { kind: 'signal'; id: string }
  | { kind: 'position'; id: string }
  | { kind: 'candidate'; id: string }
  | null;

interface Props {
  signal: Signal | null;
  position: PaperPosition | null;
  candidate: DashboardCandidate | null;
  trades: DashboardTrade[];
  isBought: boolean;
  onPaperBuy: (signal: Signal) => void;
  onClosePosition: (id: string) => void;
  onOpenTrade: (id: string) => void;
  onClear: () => void;
}

const Stat: React.FC<{ label: string; tone?: string; children: React.ReactNode }> = ({ label, tone = '', children }) => (
  <div><div className="desk-label">{label}</div><div className={`desk-num font-semibold ${tone}`}>{children}</div></div>
);

/** Centre workspace: whatever is selected on the left, in the right, or in a table, with its levels and evidence. */
export const FocusPane: React.FC<Props> = ({ signal, position, candidate, trades, isBought, onPaperBuy, onClosePosition, onOpenTrade, onClear }) => {
  if (signal) {
    return <div className="h-full"><SignalDetails inline signal={signal} onClose={onClear} onPaperBuy={onPaperBuy} isBought={isBought} /></div>;
  }
  if (position) {
    const t1 = position.status === 'TARGET_1';
    const booked = position.booked_pnl_rupees ?? 0;
    return (
      <div className="flex flex-col h-full min-h-0" aria-label="Selected position">
        <div className="px-4 py-3 flex flex-wrap items-start justify-between gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold truncate">{position.strike_symbol} <span className={`desk-side ${position.option_type === 'CE' ? 'ce' : 'pe'}`}>BUY {position.option_type}</span></h2>
            <p className="text-xs desk-muted">{setupCode(position.setup_type)} · {position.symbol} · {position.timeframe} · in {position.entry_time} · {position.quantity} qty ({position.lots}L × {position.lot_size})</p>
          </div>
          <div className="text-right">
            <div className={`desk-hero md ${pnlClass(position.pnl_rupees)}`}>{formatCurrency(position.pnl_rupees, true)}</div>
            <div className="text-xs desk-muted desk-num">{position.pnl_points >= 0 ? '+' : ''}{position.pnl_points.toFixed(1)} pts on open lots</div>
          </div>
        </div>
        <div className="px-4 py-2 flex flex-wrap items-end gap-x-6 gap-y-2" style={{ borderBottom: '1px solid var(--line)' }}>
          <Stat label={t1 ? 'Trailed SL' : 'SL'} tone="desk-down">{position.option_sl.toFixed(1)}</Stat>
          <Stat label="Entry">{position.option_entry.toFixed(1)}</Stat>
          <Stat label="LTP">{position.current_option_price.toFixed(1)}</Stat>
          <Stat label={t1 ? 'T2' : 'T1'} tone="desk-up">{(t1 ? position.option_target_2 : position.option_target_1).toFixed(1)}</Stat>
          <Stat label="Booked" tone={pnlClass(booked)}>{formatCurrency(booked, true)}</Stat>
          {position.est_net_pnl !== undefined && <Stat label="Net if closed now" tone={pnlClass(position.est_net_pnl)}>{formatCurrency(position.est_net_pnl, true)}</Stat>}
          <button type="button" className="desk-btn danger fill ml-auto" onClick={() => onClosePosition(position.id)} aria-label={`Close ${position.strike_symbol} position now`}>Close position</button>
        </div>
        <div className="flex-1 min-h-0"><PositionChartModal inline position={position} onClose={onClear} /></div>
      </div>
    );
  }
  if (candidate) {
    const signalId = candidate.book === 'paper' && candidate.id.startsWith('paper:') ? candidate.id.slice('paper:'.length) : null;
    const trade = signalId ? trades.find((x) => x.book === 'paper' && x.signal_id === signalId) : null;
    return <div className="h-full overflow-y-auto p-2"><WatchCandidateDetail candidate={candidate} tradeId={trade?.id} onOpenTrade={onOpenTrade} /></div>;
  }
  return (
    <div className="h-full flex items-center justify-center p-8 text-center">
      <div>
        <p className="font-semibold mb-1">Nothing selected</p>
        <p className="text-sm desk-muted max-w-xs">Pick a signal on the left or an open position on the right to see its levels, reasoning and chart here.</p>
      </div>
    </div>
  );
};
