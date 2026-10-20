import type { StreamStatus } from '../components/Header';

export type ConnectionLevel = 'live' | 'delayed' | 'stale' | 'disconnected' | 'demo' | 'closed' | 'connecting';

export interface ConnectionInput {
  activeMode?: string;
  feedStatus?: string;
  wsConnected?: boolean;
  stream?: StreamStatus;
}

export interface ConnectionState {
  level: ConnectionLevel;
  /** Short pill text. */
  label: string;
  /** One plain sentence for tooltips and the warning banner. */
  detail: string;
  tone: 'up' | 'warn' | 'down' | 'mute';
  /** True when prices on screen may be out of date. */
  degraded: boolean;
}

/**
 * One answer to "can I trust the numbers on screen right now?".
 * The link between this browser and the server outranks the market feed, because a dead link
 * freezes everything regardless of what the feed is doing.
 */
export function connectionState({ activeMode, feedStatus, wsConnected, stream }: ConnectionInput): ConnectionState {
  if (stream?.state === 'reconnecting') {
    return { level: 'disconnected', label: 'Disconnected', tone: 'down', degraded: true,
      detail: `Lost the connection to the dashboard server ${stream.ageSec}s ago. Reconnecting; prices on screen are frozen.` };
  }
  if (stream?.state === 'stale') {
    return { level: 'stale', label: `Stale ${stream.ageSec}s`, tone: 'warn', degraded: true,
      detail: `No update from the dashboard server for ${stream.ageSec}s. Prices on screen may be out of date.` };
  }
  if (activeMode === 'error' || feedStatus === 'ERROR') {
    return { level: 'disconnected', label: 'Feed error', tone: 'down', degraded: true,
      detail: 'The market data feed reported an error. Prices on screen may be out of date.' };
  }
  if (activeMode === 'stale' || feedStatus === 'STALE') {
    return { level: 'stale', label: 'Feed stale', tone: 'warn', degraded: true,
      detail: 'The market data feed has stopped updating. Prices on screen may be out of date.' };
  }
  if (activeMode === 'closed') {
    return { level: 'closed', label: 'Market closed', tone: 'mute', degraded: false, detail: 'The market is closed. Nothing is updating.' };
  }
  if (activeMode === 'demo' && !wsConnected) {
    return { level: 'demo', label: 'Demo data', tone: 'warn', degraded: false, detail: 'Showing demo data, not live market prices. Connect Dhan for live prices.' };
  }
  if (wsConnected || feedStatus === 'WS_LIVE') {
    return { level: 'live', label: 'Live', tone: 'up', degraded: false, detail: 'Live market feed, updating about every second.' };
  }
  if (activeMode === 'live' || feedStatus === 'HTTP_POLLING' || feedStatus === 'LIVE') {
    return { level: 'delayed', label: 'Delayed', tone: 'warn', degraded: false, detail: 'Prices come from polling, a few seconds behind a live feed.' };
  }
  if (stream?.state === 'connecting') {
    return { level: 'connecting', label: 'Connecting', tone: 'mute', degraded: false, detail: 'Connecting to the dashboard server.' };
  }
  return { level: 'demo', label: 'Demo data', tone: 'warn', degraded: false, detail: 'Showing demo data, not live market prices.' };
}
