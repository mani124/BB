import React from 'react';
import type { ScannerState } from '../types';
import type { StreamStatus } from './Header';
import { ConnectionStatus } from './ConnectionStatus';

/** A single glance at whether the desk is receiving data and permitted to enter. */
export const WatchStatus: React.FC<{ state: ScannerState; stream: StreamStatus; confirmedCount: number }> = ({ state, stream, confirmedCount }) => {
  const risk = state.paper_portfolio?.risk;
  const blocked = risk?.entries_blocked || risk?.kill_switch_active || risk?.loss_cap_tripped;
  const entryLabel = state.active_mode === 'closed' ? 'Market closed · no entries' : !risk ? 'Entry status unavailable' : blocked ? 'Entries paused' : 'Risk permits entries';
  const entryReason = blocked ? (risk?.block_reason || risk?.loss_cap_reason || (risk?.kill_switch_active ? 'Kill switch is on' : 'Risk limit reached')) : null;
  return (
    <section className="desk-panel px-3.5 py-2.5" aria-label="Desk status">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <strong className={`desk-pill ${!risk || blocked ? 'down' : 'up'}`}>{entryLabel}</strong>
          {entryReason && <span className="desk-down">{entryReason}</span>}
        </div>
        <ConnectionStatus activeMode={state.active_mode} feedStatus={state.feed_status} wsConnected={state.ws_connected} stream={stream} />
        <span className="desk-num">{state.paper_portfolio?.active_positions?.length ?? 0} open</span>
        <span className="desk-num">{confirmedCount} confirmed</span>
      </div>
    </section>
  );
};
