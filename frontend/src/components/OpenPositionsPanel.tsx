import React, { useState } from 'react';
import type { PaperPosition } from '../types';
import { PositionChartModal } from './PositionChartModal';
import { setupCode } from './setupCode';
import { INR, formatCurrency, pnlClass } from './format';

/* ---------- Open positions ---------- */
export const OpenPositionsPanel: React.FC<{
  positions: PaperPosition[];
  onClosePosition: (id: string) => void;
  /** One-line expandable rows that fill their parent's height (Watch screen). */
  compact?: boolean;
  /** Controls shown in the panel header (Watch screen: auto-enter and lot size). */
  headerActions?: React.ReactNode;
}> = ({ positions, onClosePosition, compact = false, headerActions }) => {
  // Keep the position itself, so the popup stays open (and shows the exit) if the trade closes meanwhile.
  const [chartPosition, setChartPosition] = useState<PaperPosition | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  return (
  <section className={`desk-panel ${compact ? 'desk-pane min-h-[6rem]' : ''}`} aria-labelledby="open-positions-title">
    <div className="desk-ph">
      <h2 id="open-positions-title">{compact ? 'Open positions' : 'Active Open Paper Positions'} ({positions.length})</h2>
      {headerActions ? (
        <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1.5">{headerActions}</div>
      ) : (
        <span className="text-xs desk-muted ml-auto">Books 50% at T1, then trails the rest at breakeven</span>
      )}
    </div>
    <div className={compact ? 'desk-scroll' : ''} tabIndex={compact ? 0 : undefined} aria-label={compact ? 'Open positions list' : undefined}>
    {positions.length === 0 ? (
      <div className="p-6 text-center text-sm desk-muted">
        No open paper positions. New signals open trades automatically, or click "Paper buy" on a signal.
      </div>
    ) : (
      positions.map((pos) => {
        const isT1 = pos.status === 'TARGET_1';
        if (compact) {
          const open = expandedId === pos.id;
          const cTarget = isT1 ? pos.option_target_2 : pos.option_target_1;
          const cSpan = cTarget - pos.option_sl;
          const cFrac = cSpan > 0 ? Math.max(0, Math.min(1, (pos.current_option_price - pos.option_sl) / cSpan)) : 0.5;
          const cBooked = pos.booked_pnl_rupees ?? 0;
          return (
            <div key={pos.id} style={{ borderBottom: '1px solid var(--line)' }}>
              <div className="px-4 py-3 grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-2">
                <div className="min-w-0">
                  <span className="desk-sym">{pos.strike_symbol}</span>{' '}
                  <span className={`desk-side ${pos.option_type === 'CE' ? 'ce' : 'pe'}`}>{pos.option_type}</span>{' '}
                  <span className="desk-code">{setupCode(pos.setup_type)}</span>
                  <span className="desk-sub">
                    {pos.quantity} qty · in {pos.entry_time} · LTP {pos.current_option_price.toFixed(1)}
                    {isT1 ? ' · T1 hit' : ''}
                  </span>
                </div>
                <div className={`desk-hero md text-right ${pnlClass(pos.pnl_rupees)}`}>
                  {formatCurrency(pos.pnl_rupees, true)}
                </div>
                <div className="flex items-center gap-2 min-w-0 col-span-2 sm:col-span-1" aria-hidden>
                  <span className="desk-num text-xs desk-down shrink-0">{pos.option_sl.toFixed(1)}</span>
                  <div className="relative h-2 flex-1 rounded-sm" style={{ background: 'linear-gradient(90deg, var(--down-soft) 0 33%, var(--line) 33% 66%, var(--up-soft) 66%)' }}>
                    <i className="absolute block rounded-sm" style={{ top: -3, width: 4, height: 14, background: 'var(--fg)', left: `calc(${cFrac * 100}% - 2px)` }} />
                  </div>
                  <span className="desk-num text-xs desk-up shrink-0">{cTarget.toFixed(1)}</span>
                </div>
                <div className="flex items-center gap-2 justify-end col-span-2 sm:col-span-1">
                  <button type="button" className="desk-btn sm" aria-expanded={open} aria-label={`Details for ${pos.strike_symbol}`} onClick={() => setExpandedId(open ? null : pos.id)}>{open ? 'Less' : 'Details'}</button>
                  <button type="button" className="desk-btn sm accent" aria-label={`Chart ${pos.strike_symbol}`} onClick={() => setChartPosition(pos)}>Chart</button>
                  <button type="button" className="desk-btn sm danger" aria-label={`Close ${pos.strike_symbol}`} onClick={() => onClosePosition(pos.id)}>Close</button>
                </div>
              </div>
              {open && (
                <div className="px-4 pb-3 flex flex-col gap-1 text-sm desk-num">
                  <div className="flex flex-wrap justify-between gap-x-3 desk-muted">
                    <span className={isT1 ? '' : 'desk-down'}>{isT1 ? 'Trailed SL' : 'SL'} {pos.option_sl.toFixed(1)}</span>
                    <span>Entry {pos.option_entry.toFixed(1)}</span>
                    <span className="desk-up">{isT1 ? 'T2' : 'T1'} {cTarget.toFixed(1)}</span>
                  </div>
                  <div className="flex flex-wrap justify-between gap-x-3">
                    <span className={pnlClass(cBooked)}>Booked {formatCurrency(cBooked, true)}</span>
                    {pos.est_net_pnl !== undefined && (
                      <span className={pnlClass(pos.est_net_pnl)}>Net if closed now {formatCurrency(pos.est_net_pnl, true)}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        }
        const target = isT1 ? pos.option_target_2 : pos.option_target_1;
        const span = target - pos.option_sl;
        const booked = pos.booked_pnl_rupees ?? 0;
        const openGain = pos.unrealized_pnl_rupees ?? Math.round((pos.pnl_rupees - booked) * 100) / 100;
        const frac = span > 0 ? Math.max(0, Math.min(1, (pos.current_option_price - pos.option_sl) / span)) : 0.5;
        return (
          <div
            key={pos.id}
            className="px-3.5 py-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 cursor-pointer"
            style={{ borderBottom: '1px solid var(--line)' }}
            onClick={() => setChartPosition(pos)}
            title="Click to open chart"
          >
            <div>
              <span className="desk-sym">{pos.strike_symbol}</span>{' '}
              <span className={`desk-side ${pos.option_type === 'CE' ? 'ce' : 'pe'}`}>BUY {pos.option_type}</span>
              <span className="desk-sub">
                {setupCode(pos.setup_type)} · {pos.symbol} {pos.timeframe} @ {pos.entry_time} · {pos.quantity} qty ({pos.lots}L × {pos.lot_size})
              </span>
            </div>
            <div className={`desk-num text-xl font-semibold text-right ${pnlClass(pos.pnl_rupees)}`}>
              {formatCurrency(pos.pnl_rupees, true)}
              <span className="desk-sub text-right">Total · {pos.pnl_points >= 0 ? '+' : ''}{pos.pnl_points.toFixed(1)} pts on open lots</span>
            </div>
            <div
              className="col-span-2 relative h-1.5 rounded-sm my-2"
              style={{ background: 'linear-gradient(90deg, var(--down-soft) 0 33%, var(--line) 33% 66%, var(--up-soft) 66%)' }}
            >
              <i className="absolute block rounded-sm" style={{ top: -3, width: 3, height: 12, background: 'var(--fg)', left: `calc(${frac * 100}% - 1px)` }} />
            </div>
            <div className="col-span-2 flex flex-wrap justify-between gap-x-3 text-xs desk-num desk-muted">
              <span className={isT1 ? '' : 'desk-down'}>{isT1 ? 'Trailed SL' : 'SL'} {pos.option_sl.toFixed(1)}</span>
              <span>Entry {pos.option_entry.toFixed(1)}</span>
              <span style={{ color: 'var(--fg)', fontWeight: 600 }}>LTP {pos.current_option_price.toFixed(1)}</span>
              <span className="desk-up">{isT1 ? 'T2' : 'T1'} {target.toFixed(1)}</span>
            </div>
            <div className="col-span-2 flex flex-wrap justify-between gap-x-3 text-xs desk-num">
              <span className={pnlClass(booked)}>
                Booked {formatCurrency(booked, true)}
              </span>
              <span className={pnlClass(openGain)}>
                Unrealized {formatCurrency(openGain, true)}
              </span>
              {pos.est_net_pnl !== undefined && (
                <span className={pnlClass(pos.est_net_pnl)} title="Booked + unrealized, minus estimated brokerage and taxes for the whole trade">
                  Net if closed now {formatCurrency(pos.est_net_pnl, true)}
                  {(pos.est_exit_charges ?? 0) > 0 && <span className="desk-muted"> (charges ₹{pos.est_exit_charges!.toLocaleString('en-IN', INR)})</span>}
                </span>
              )}
            </div>
            {isT1 && (
              <div className="col-span-2 text-xs" style={{ color: 'var(--accent)' }}>
                {(pos.booked_lots ?? 0) > 0
                  ? `✓ ${pos.booked_lots} of ${pos.initial_lots ?? (pos.lots + (pos.booked_lots ?? 0))} lots booked at T1: ${formatCurrency(booked, true)} locked in`
                  : 'T1 hit: a single lot cannot be split, so nothing is booked. Stop moved to breakeven.'}
              </div>
            )}
            <div className="col-span-2 text-right mt-1">
              <button type="button" className="desk-btn accent mr-2" onClick={(e) => { e.stopPropagation(); setChartPosition(pos); }}>
                Chart
              </button>
              <button type="button" className="desk-btn danger" onClick={(e) => { e.stopPropagation(); onClosePosition(pos.id); }}>
                Close
              </button>
            </div>
          </div>
        );
      })
    )}
    </div>
    {chartPosition && <PositionChartModal position={chartPosition} onClose={() => setChartPosition(null)} />}
  </section>
  );
};
