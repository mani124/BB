import { describe, expect, it } from 'vitest';
import { connectionState } from './connectionState';

const live = { state: 'live' as const, ageSec: 0 };

describe('connectionState', () => {
  it('says Live on the websocket feed and Delayed on polling', () => {
    expect(connectionState({ activeMode: 'live', feedStatus: 'WS_LIVE', wsConnected: true, stream: live }).label).toBe('Live');
    expect(connectionState({ activeMode: 'live', feedStatus: 'HTTP_POLLING', wsConnected: false, stream: live }).label).toBe('Delayed');
  });

  it('puts a lost browser link ahead of a healthy market feed', () => {
    const s = connectionState({ activeMode: 'live', feedStatus: 'WS_LIVE', wsConnected: true, stream: { state: 'reconnecting', ageSec: 12 } });
    expect(s.label).toBe('Disconnected');
    expect(s.degraded).toBe(true);
  });

  it('shows how stale the screen is and flags it as degraded', () => {
    const s = connectionState({ activeMode: 'live', wsConnected: true, stream: { state: 'stale', ageSec: 42 } });
    expect(s.label).toBe('Stale 42s');
    expect(s.degraded).toBe(true);
  });

  it('does not alarm for demo data or a closed market', () => {
    expect(connectionState({ activeMode: 'demo', stream: live }).degraded).toBe(false);
    expect(connectionState({ activeMode: 'closed', stream: live }).label).toBe('Market closed');
  });

  it('reports a feed error as degraded', () => {
    expect(connectionState({ activeMode: 'error', stream: live })).toMatchObject({ label: 'Feed error', degraded: true });
  });
});
