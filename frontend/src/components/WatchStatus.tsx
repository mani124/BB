import React from 'react';
import type { ScannerState } from '../types';
import type { StreamStatus } from './Header';

/** A single glance at whether the desk is receiving data and permitted to enter. */
export const WatchStatus: React.FC<{ state: ScannerState; stream: StreamStatus; confirmedCount: number }> = ({ state, stream, confirmedCount }) => {
  const risk = state.paper_portfolio?.risk;
  const blocked = risk?.entries_blocked || risk?.kill_switch_active || risk?.loss_cap_tripped;
  const entryLabel = state.active_mode === 'closed' ? 'Market closed · no entries' : !risk ? 'Entry status unavailable' : blocked ? 'Entries paused' : 'Risk permits entries';
  const entryReason = blocked ? (risk?.block_reason || risk?.loss_cap_reason || (risk?.kill_switch_active ? 'Kill switch is on' : 'Risk limit reached')) : null;
  const feedLabel = state.active_mode === 'demo' ? 'Demo data' : state.active_mode === 'closed' ? 'Market closed'
    : state.feed_status === 'WS_LIVE' || state.ws_connected ? 'Live market feed'
    : state.feed_status === 'HTTP_POLLING' || state.feed_status === 'LIVE' ? 'Polling market feed'
    : state.feed_status === 'STALE' || state.active_mode === 'stale' ? 'Market feed stale'
    : state.feed_status === 'ERROR' || state.active_mode === 'error' ? 'Market feed error' : 'Market feed unavailable';
  const screenLabel = stream.state === 'live' ? 'Screen updates live' : stream.state === 'connecting' ? 'Connecting screen updates'
    : stream.state === 'reconnecting' ? `Reconnecting screen updates · ${stream.ageSec}s since last update`
    : `Screen updates stale for ${stream.ageSec}s`;

  return (
    <section className="desk-panel px-3.5 py-2.5" aria-label="Desk status">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <strong className={`desk-pill ${!risk || blocked ? 'down' : 'up'}`}>{entryLabel}</strong>
          {entryReason && <span className="desk-down">{entryReason}</span>}
        </div>
        <span className={`desk-pill ${feedLabel.includes('Live') ? 'up' : 'warn'}`}>{feedLabel}</span>
        <span className={`desk-pill ${stream.state === 'live' ? 'up' : 'warn'}`} role="status">{screenLabel}</span>
        <span className="desk-num">{state.paper_portfolio?.active_positions?.length ?? 0} open</span>
        <span className="desk-num">{confirmedCount} confirmed</span>
      </div>
    </section>
  );
};
