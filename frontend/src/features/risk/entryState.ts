import type { RiskStatus } from '../../types';

export type BlockCode = 'kill_switch' | 'loss_cap' | 'capped_pools' | 'auto_enter_off' | 'max_open' | 'market_closed' | 'stream_stale';

export interface BlockReason {
  code: BlockCode;
  text: string;
  /** false: only part of the book is affected (capped pools), so entries are not blocked as a whole. */
  blocking: boolean;
}

export interface EntryInputs {
  risk: RiskStatus | null | undefined;
  autoTrade: boolean | undefined;
  openCount: number;
  maxOpen: number | null | undefined;
  session: 'pre-open' | 'open' | 'closed' | 'weekend';
  stream: 'connecting' | 'live' | 'reconnecting' | 'stale';
}

/** Why new entries are or are not allowed, most important first. */
export function entryReasons(i: EntryInputs): BlockReason[] {
  const out: BlockReason[] = [];
  if (i.risk?.kill_switch_active) out.push({ code: 'kill_switch', blocking: true, text: `Kill switch is on${i.risk.kill_switch_since ? ` since ${i.risk.kill_switch_since}` : ''}.` });
  if (i.risk?.loss_cap_tripped) out.push({ code: 'loss_cap', blocking: true, text: i.risk.loss_cap_reason || 'The daily loss cap has been reached.' });
  const pools = i.risk?.capped_pools ?? [];
  if (pools.length) out.push({ code: 'capped_pools', blocking: false, text: `Capped pools: ${pools.join(', ')}. Other setups keep trading.` });
  if (i.autoTrade === false) out.push({ code: 'auto_enter_off', blocking: true, text: 'Auto-enter is off. Signals are shown but not entered.' });
  if (i.maxOpen && i.maxOpen > 0 && i.openCount >= i.maxOpen) out.push({ code: 'max_open', blocking: true, text: `${i.openCount} open positions; the maximum is ${i.maxOpen}.` });
  if (i.session !== 'open') out.push({ code: 'market_closed', blocking: true, text: i.session === 'weekend' ? 'The market is closed for the weekend.' : i.session === 'pre-open' ? 'The market has not opened yet (09:15 IST).' : 'The market is closed (after 15:30 IST).' });
  if (i.stream === 'stale' || i.stream === 'reconnecting') out.push({ code: 'stream_stale', blocking: true, text: 'The live stream is not updating, so figures may be old.' });
  return out;
}

export const entriesAllowed = (reasons: BlockReason[]): boolean => !reasons.some((r) => r.blocking);

/** Share of the loss cap used, 0..1, or null when the cap is off. A day in profit uses none of it. */
export function lossCapUsage(risk: RiskStatus | null | undefined): number | null {
  if (!risk || !risk.daily_loss_limit || risk.daily_loss_limit <= 0) return null;
  return Math.min(1, Math.max(0, -risk.day_pnl / risk.daily_loss_limit));
}

export interface ExposureRow { key: string; count: number; risk_rupees: number; notional: number }

/** Largest share (0..100) any row has of the total notional, and the row. */
export function concentration(rows: ExposureRow[]): { pct: number; key: string | null } {
  const total = rows.reduce((a, r) => a + r.notional, 0);
  if (total <= 0) return { pct: 0, key: null };
  const top = rows.reduce((a, r) => (r.notional > a.notional ? r : a), rows[0]);
  return { pct: (top.notional / total) * 100, key: top.key };
}

export const CONCENTRATION_MIN = 10;
export const CONCENTRATION_MAX = 100;
export function cleanConcentration(v: unknown): number {
  const n = typeof v === 'number' && Number.isFinite(v) ? v : 50;
  return Math.min(CONCENTRATION_MAX, Math.max(CONCENTRATION_MIN, Math.round(n)));
}
