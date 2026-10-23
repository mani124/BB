import type { AppState, Json } from '../../data/types';

export type TileState = 'ok' | 'warn' | 'down' | 'unknown';
export interface Tile { id: string; label: string; state: TileState; word: string; detail: string; asOf: number | null; owner: string | null }

export interface HealthInputs {
  now: number;
  state: Pick<AppState, 'stream' | 'scanner' | 'health' | 'live' | 'meta'>;
  token: { loggedIn: boolean; expiry: number | null };
  version?: string | null;
}

const WORD: Record<TileState, string> = { ok: 'OK', warn: 'Warning', down: 'Down', unknown: 'Unknown' };
const tile = (id: string, label: string, state: TileState, detail: string, asOf: number | null, owner: string | null, word?: string): Tile =>
  ({ id, label, state, word: word ?? WORD[state], detail, asOf, owner });

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function buildTiles({ now, state, token, version }: HealthInputs): Tile[] {
  const { stream, scanner, health, live, meta } = state;
  const out: Tile[] = [];

  const streamTile: [TileState, string, string] =
    stream.state === 'live' ? ['ok', 'Live', 'Receiving updates from the dashboard server.']
      : stream.state === 'connecting' ? ['unknown', 'Connecting', 'Waiting for the first update.']
        : stream.state === 'stale' ? ['warn', `Stale ${stream.ageSec}s`, `No update for ${stream.ageSec} seconds.`]
          : ['down', 'Disconnected', `Lost the link ${stream.ageSec} seconds ago; reconnecting.`];
  out.push(tile('stream', 'Stream', streamTile[0], streamTile[2], meta.stream.asOf, null, streamTile[1]));

  const feed = scanner.feed_status ?? '';
  const mode = scanner.active_mode;
  const feedTile: [TileState, string, string] =
    mode === 'error' || feed === 'ERROR' ? ['down', 'Error', 'The market data feed reported an error.']
      : feed === 'STALE' || mode === 'stale' ? ['warn', 'Stale', 'The feed stopped updating.']
        : mode === 'closed' ? ['unknown', 'Market closed', 'Nothing is updating outside market hours.']
          : feed === 'WS_LIVE' || feed === 'LIVE' ? ['ok', 'Live', 'Real-time ticks.']
            : feed === 'HTTP_POLLING' ? ['warn', 'Polling', 'Using slower HTTP polling instead of the websocket.']
              : mode === 'demo' || feed === 'DEMO' ? ['warn', 'Demo data', 'Not live prices.']
                : ['unknown', 'Unknown', 'No feed status yet.'];
  out.push(tile('feed', 'Feed', feedTile[0], feedTile[2], meta.scanner.asOf, 'market', feedTile[1]));

  if (!token.loggedIn) out.push(tile('token', 'Dhan token', 'warn', 'Not connected in this browser tab.', null, null, 'Not connected'));
  else if (token.expiry === null) out.push(tile('token', 'Dhan token', 'unknown', 'Connected; expiry unknown.', null, null, 'Connected'));
  else {
    const left = token.expiry - now;
    const mins = Math.max(0, Math.ceil(left / 60000));
    out.push(left <= 0 ? tile('token', 'Dhan token', 'down', 'The token has expired. Connect again.', null, null, 'Expired')
      : left < 3_600_000 ? tile('token', 'Dhan token', 'warn', `Expires in ${mins} minutes.`, null, null, `${mins} min left`)
        : tile('token', 'Dhan token', 'ok', `Expires in ${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m.`, null, null, `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m left`));
  }

  const rl = health.rateLimit;
  if (!rl) out.push(tile('rate', 'Rate limit', 'unknown', 'No rate-limit data yet.', meta.health.asOf, 'telemetry'));
  else {
    const today = num(rl.today) ?? 0;
    const cool = num(rl.cooldown_s) ?? 0;
    out.push(cool > 0 ? tile('rate', 'Rate limit', 'warn', `Dhan calls paused for ${Math.round(cool)} s. ${today} rejections today.`, meta.health.asOf, 'telemetry', 'Cooling down')
      : tile('rate', 'Rate limit', today >= 50 ? 'warn' : 'ok', `${today} rejections (HTTP 429) today.`, meta.health.asOf, 'telemetry'));
  }

  out.push(scanner.last_scan_time
    ? tile('scanner', 'Scanner', scanner.is_scanning ? 'ok' : 'ok', `Cycle ${scanner.scan_cycle_count}, last scan ${scanner.last_scan_time}.`, meta.scanner.asOf, 'signals', scanner.is_scanning ? 'Scanning' : 'Idle')
    : tile('scanner', 'Scanner', 'unknown', 'No scan yet.', meta.scanner.asOf, 'signals'));

  const rec = health.recorder as Json | null;
  if (!rec) out.push(tile('recorder', 'Recorder', 'unknown', 'No recorder data yet.', meta.health.asOf, 'recorder'));
  else if (rec.enabled === false) out.push(tile('recorder', 'Recorder', 'unknown', 'Recording is off.', meta.health.asOf, 'recorder', 'Off'));
  else {
    const dropped = num(rec.dropped) ?? 0;
    out.push(dropped > 0 ? tile('recorder', 'Recorder', 'warn', `${dropped} bars dropped this run.`, meta.health.asOf, 'recorder')
      : tile('recorder', 'Recorder', 'ok', `${num(rec.recorded_this_run) ?? 0} bars recorded this run.`, meta.health.asOf, 'recorder'));
  }

  const rd = health.readiness as (Json & { checks?: { key: string; status: string; detail: string }[] }) | null;
  if (!rd) out.push(tile('readiness', 'Readiness', 'unknown', 'No readiness data yet.', meta.health.asOf, 'readiness'));
  else {
    const bad = (rd.checks ?? []).filter((c) => c.status !== 'ok');
    const s: TileState = rd.status === 'fail' ? 'down' : rd.status === 'warn' ? 'warn' : 'ok';
    out.push(tile('readiness', 'Readiness', s, bad.length ? bad.map((c) => `${c.key}: ${c.detail}`).slice(0, 2).join('; ') : 'All checks pass.', meta.health.asOf, 'readiness', s === 'down' ? 'Failed' : undefined));
  }

  const ls = live.status as Json | null;
  if (!ls) out.push(tile('live', 'Live broker', 'unknown', 'No live-routing data yet.', meta.live.asOf, 'live'));
  else if (ls.halted) out.push(tile('live', 'Live broker', 'down', 'Live routing is halted.', meta.live.asOf, 'live', 'Halted'));
  else if (ls.mode === 'off') out.push(tile('live', 'Live broker', 'unknown', 'Routing is off (paper only).', meta.live.asOf, 'live', 'Off'));
  else if (ls.mode === 'live' && ls.broker_session === false) out.push(tile('live', 'Live broker', 'down', 'Live mode but no broker session.', meta.live.asOf, 'live', 'No session'));
  else out.push(tile('live', 'Live broker', 'ok', `Mode ${String(ls.mode)}.`, meta.live.asOf, 'live'));

  const high = health.errors.filter((e) => ['ERROR', 'CRITICAL'].includes(String(e.severity ?? '').toUpperCase()));
  out.push(tile('errors', 'Errors', high.length ? 'warn' : 'ok', high.length ? `${high.length} errors in the latest ${health.errors.length} events.` : 'No recent errors.', meta.health.asOf, 'telemetry', high.length ? `${high.length} recent` : undefined));

  out.push(tile('build', 'Build', version ? 'ok' : 'unknown', version ? `Version ${version}.` : 'Version not available.', null, null, version ?? 'Unknown'));
  return out;
}

const SENSITIVE = /token|secret|key|password|totp|capability/i;

/** JSON for "Copy diagnostics": tile states and counters only; any field that looks like a credential is dropped. */
export function diagnostics(tiles: Tile[], extra: Record<string, unknown> = {}): string {
  const strip = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(strip);
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v as Record<string, unknown>).filter(([k]) => !SENSITIVE.test(k)).map(([k, x]) => [k, strip(x)]));
    return v;
  };
  return JSON.stringify(strip({ tiles: tiles.map((t) => ({ id: t.id, state: t.state, word: t.word, detail: t.detail, asOf: t.asOf })), ...extra }), null, 2);
}
