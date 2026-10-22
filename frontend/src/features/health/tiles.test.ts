import { describe, it, expect } from 'vitest';
import { initialState } from '../../data/appStore';
import { buildTiles, diagnostics } from './tiles';

const NOW = Date.parse('2026-10-22T05:00:00Z');
const build = (over: Partial<ReturnType<typeof initialState>> = {}, token: { loggedIn: boolean; expiry: number | null } = { loggedIn: true, expiry: NOW + 5 * 3_600_000 }, version: string | null = '1.2.3') =>
  buildTiles({ now: NOW, state: { ...initialState(), ...over }, token, version });
const by = (tiles: ReturnType<typeof build>, id: string) => tiles.find((t) => t.id === id)!;

describe('health tiles', () => {
  it('has one tile per subject', () => {
    expect(build().map((t) => t.id)).toEqual(['stream', 'feed', 'token', 'rate', 'scanner', 'recorder', 'readiness', 'live', 'errors', 'build']);
  });
  it('maps the stream states', () => {
    const s = initialState();
    expect(by(build({ stream: { state: 'live', ageSec: 0 } }), 'stream').state).toBe('ok');
    expect(by(build({ stream: { state: 'stale', ageSec: 20 } }), 'stream')).toMatchObject({ state: 'warn', word: 'Stale 20s' });
    expect(by(build({ stream: { state: 'reconnecting', ageSec: 9 } }), 'stream').state).toBe('down');
    expect(by(build({ stream: s.stream }), 'stream').state).toBe('unknown');
  });
  it('maps the feed', () => {
    const f = (feed_status: string, active_mode = 'live') => by(build({ scanner: { ...initialState().scanner, feed_status, active_mode } as never }), 'feed').state;
    expect(f('WS_LIVE')).toBe('ok'); expect(f('HTTP_POLLING')).toBe('warn'); expect(f('STALE')).toBe('warn'); expect(f('ERROR')).toBe('down'); expect(f('X', 'closed')).toBe('unknown');
  });
  it('counts down the Dhan token', () => {
    expect(by(build(), 'token').state).toBe('ok');
    expect(by(build({}, { loggedIn: true, expiry: NOW + 30 * 60000 }), 'token')).toMatchObject({ state: 'warn', word: '30 min left' });
    expect(by(build({}, { loggedIn: true, expiry: NOW - 1 }), 'token')).toMatchObject({ state: 'down', word: 'Expired' });
    expect(by(build({}, { loggedIn: false, expiry: null }), 'token').state).toBe('warn');
  });
  it('maps rate limit, recorder, readiness, live and errors', () => {
    const h = initialState().health;
    expect(by(build({ health: { ...h, rateLimit: { today: 3, cooldown_s: 4 } } }), 'rate').state).toBe('warn');
    expect(by(build({ health: { ...h, rateLimit: { today: 3, cooldown_s: 0 } } }), 'rate').state).toBe('ok');
    expect(by(build({ health: { ...h, recorder: { enabled: true, dropped: 2 } } }), 'recorder').state).toBe('warn');
    expect(by(build({ health: { ...h, recorder: { enabled: false } } }), 'recorder').word).toBe('Off');
    expect(by(build({ health: { ...h, readiness: { status: 'fail', checks: [{ key: 'dhan_login', status: 'fail', detail: 'no token' }] } } }), 'readiness')).toMatchObject({ state: 'down', word: 'Failed' });
    expect(by(build({ live: { status: { mode: 'live', halted: true }, orders: [] } }), 'live').state).toBe('down');
    expect(by(build({ live: { status: { mode: 'off' }, orders: [] } }), 'live').word).toBe('Off');
    expect(by(build({ health: { ...h, errors: [{ severity: 'ERROR' }, { severity: 'WARNING' }] } }), 'errors').state).toBe('warn');
  });
  it('diagnostics carry no credential-like fields', () => {
    const text = diagnostics(build(), { token: 'SECRET-1', nested: { apiKey: 'SECRET-2', capability: 'SECRET-3', ok: 1 } });
    expect(text).not.toMatch(/SECRET/);
    expect(JSON.parse(text).nested).toEqual({ ok: 1 });
    expect(Object.keys(JSON.parse(text))).not.toContain('token');
  });
});
