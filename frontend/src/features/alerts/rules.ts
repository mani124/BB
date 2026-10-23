import type { AlertInput } from '../../data/alertsHook';
import type { AppState, Json } from '../../data/types';

export type Rule = (prev: AppState, next: AppState, now: number) => AlertInput[];

const info = (source: string, message: string): AlertInput => ({ severity: 'info', source, message });
const warn = (source: string, message: string): AlertInput => ({ severity: 'warning', source, message });
const crit = (source: string, message: string): AlertInput => ({ severity: 'critical', source, message });

const riskOf = (s: AppState) => s.scanner.paper_portfolio?.risk ?? null;

export const killSwitchRule: Rule = (p, n) => {
  const a = Boolean(riskOf(p)?.kill_switch_active);
  const b = Boolean(riskOf(n)?.kill_switch_active);
  if (!riskOf(p) || a === b) return [];
  return b ? [crit('kill_switch', 'Kill switch is ON: new entries are blocked.')] : [info('kill_switch', 'Kill switch released.')];
};

export const lossCapRule: Rule = (p, n) => {
  const was = Boolean(riskOf(p)?.loss_cap_tripped);
  const is = Boolean(riskOf(n)?.loss_cap_tripped);
  return riskOf(p) && !was && is ? [crit('loss_cap', riskOf(n)?.loss_cap_reason || 'The daily loss cap has been reached. New entries are blocked.')] : [];
};

export const cappedPoolRule: Rule = (p, n) => {
  const before = new Set(riskOf(p)?.capped_pools ?? []);
  return (riskOf(n)?.capped_pools ?? []).filter((x) => !before.has(x)).map((x) => warn('pool_cap', `Pool ${x} reached its own daily cap.`));
};

export const blockReasonRule: Rule = (p, n) => {
  const a = riskOf(p);
  const b = riskOf(n);
  if (!a || !b) return [];
  if (b.entries_blocked && (!a.entries_blocked || a.block_reason !== b.block_reason) && !b.kill_switch_active && !b.loss_cap_tripped) {
    return [warn('entries', `Entries blocked: ${b.block_reason || 'reason not given'}.`)];
  }
  return [];
};

export const streamRule: Rule = (p, n) => {
  const a = p.stream.state;
  const b = n.stream.state;
  if (a === b) return [];
  if (b === 'reconnecting') return [crit('stream', 'Lost the connection to the dashboard server. Prices are frozen.')];
  if (b === 'stale') return [warn('stream', `No update from the server for ${n.stream.ageSec} s.`)];
  if (b === 'live' && (a === 'stale' || a === 'reconnecting')) return [info('stream', 'Live stream recovered.')];
  return [];
};

export const feedRule: Rule = (p, n) => {
  const bad = (s: AppState) => (s.scanner.active_mode === 'error' || s.scanner.feed_status === 'ERROR' ? 'error' : s.scanner.active_mode === 'stale' || s.scanner.feed_status === 'STALE' ? 'stale' : 'ok');
  const a = bad(p);
  const b = bad(n);
  if (a === b) return [];
  if (b === 'error') return [crit('feed', 'The market data feed reported an error.')];
  if (b === 'stale') return [warn('feed', 'The market data feed is stale.')];
  return [info('feed', 'Market data feed recovered.')];
};

export const dhanRule: Rule = (p, n, now) => {
  const out: AlertInput[] = [];
  if (p.ui.dhan.loggedIn && !n.ui.dhan.loggedIn) out.push(warn('dhan', 'Dhan disconnected in this browser.'));
  const soon = (s: AppState) => s.ui.dhan.loggedIn && s.ui.dhan.expiry !== null && s.ui.dhan.expiry - now < 3_600_000;
  if (soon(n) && !soon(p)) {
    const mins = Math.max(0, Math.ceil(((n.ui.dhan.expiry ?? now) - now) / 60000));
    out.push(warn('dhan', mins === 0 ? 'The Dhan token has expired.' : `The Dhan token expires in ${mins} minutes.`));
  }
  return out;
};

export const rateLimitRule: Rule = (p, n) => {
  const cool = (s: AppState) => Number((s.health.rateLimit as Json | null)?.cooldown_s ?? 0) > 0;
  return !cool(p) && cool(n) ? [warn('rate_limit', 'Dhan rate limit hit: calls are paused for a moment.')] : [];
};

interface Check { key: string; status: string; detail?: string }
export const readinessRule: Rule = (p, n) => {
  const failed = (s: AppState): Check[] => ((s.health.readiness as { checks?: Check[] } | null)?.checks ?? []).filter((c) => c.status === 'fail');
  const before = new Set(failed(p).map((c) => c.key));
  return failed(n).filter((c) => !before.has(c.key)).map((c) => crit('readiness', `Readiness check failed: ${c.key.replace(/_/g, ' ')}${c.detail ? `. ${c.detail}` : ''}`));
};

export const liveHaltRule: Rule = (p, n) => {
  const h = (s: AppState) => Boolean((s.live.status as Json | null)?.halted);
  return !h(p) && h(n) ? [crit('live', 'Live routing is halted.')] : [];
};

const BAD_ORDER = new Set(['REJECTED', 'FAILED', 'ERROR']);
export const orderRule: Rule = (p, n) => {
  const seen = new Map(p.live.orders.map((o) => [String(o.id), String(o.status ?? '').toUpperCase()]));
  return n.live.orders
    .filter((o) => BAD_ORDER.has(String(o.status ?? '').toUpperCase()) && seen.get(String(o.id)) !== String(o.status ?? '').toUpperCase())
    .map((o) => crit('orders', `Order ${String(o.status).toLowerCase()}: ${String(o.side ?? '')} ${String(o.trading_symbol ?? '')}${o.message ? `. ${String(o.message)}` : ''}`));
};

export const positionClosedRule: Rule = (p, n) => {
  const was = new Set((p.scanner.paper_portfolio?.active_positions ?? []).map((x) => x.id));
  const open = new Set((n.scanner.paper_portfolio?.active_positions ?? []).map((x) => x.id));
  const out: AlertInput[] = [];
  for (const t of n.closedTrades) {
    if (!was.has(t.id) || open.has(t.id)) continue;
    if (t.quarantine_reason) out.push(warn('position', `${t.strike_symbol} was closed by quarantine: ${t.quarantine_reason}.`));
    else if (t.status === 'STOPPED_OUT') out.push(info('position', `${t.strike_symbol} was closed by its stop.`));
  }
  return out;
};

export const errorEventRule: Rule = (p, n) => {
  const seen = new Set(p.health.errors.map((e) => String(e.id)));
  const fresh = p.health.errors.length === 0 && p.meta.health.asOf === null ? [] : n.health.errors.filter((e) => !seen.has(String(e.id)));
  return fresh.filter((e) => ['ERROR', 'CRITICAL'].includes(String(e.severity ?? '').toUpperCase()))
    .map((e) => crit('errors', `${String(e.component ?? 'app')}: ${String(e.message ?? e.code ?? 'error')}`.slice(0, 200)));
};

export const RULES: { id: string; description: string; run: Rule }[] = [
  { id: 'kill_switch', description: 'Kill switch turned on or off', run: killSwitchRule },
  { id: 'loss_cap', description: 'Daily loss cap reached', run: lossCapRule },
  { id: 'pool_cap', description: 'A pool reached its own daily cap', run: cappedPoolRule },
  { id: 'entries', description: 'Entries blocked for a new reason', run: blockReasonRule },
  { id: 'stream', description: 'Stream reconnecting, stale or recovered', run: streamRule },
  { id: 'feed', description: 'Market feed error, stale or recovered', run: feedRule },
  { id: 'dhan', description: 'Dhan disconnected or token under 1 hour', run: dhanRule },
  { id: 'rate_limit', description: 'Dhan rate-limit cooldown started', run: rateLimitRule },
  { id: 'readiness', description: 'A readiness check failed', run: readinessRule },
  { id: 'live', description: 'Live routing halted', run: liveHaltRule },
  { id: 'orders', description: 'An order was rejected or failed', run: orderRule },
  { id: 'position', description: 'A position closed by its stop or by quarantine', run: positionClosedRule },
  { id: 'errors', description: 'New high-severity error events', run: errorEventRule },
];

/** All alerts raised by the change from `prev` to `next`. Unchanged conditions raise nothing. */
export function evaluateRules(prev: AppState, next: AppState, now: number = Date.now()): AlertInput[] {
  if (prev === next) return [];
  return RULES.flatMap((r) => { try { return r.run(prev, next, now); } catch { return []; } });
}
