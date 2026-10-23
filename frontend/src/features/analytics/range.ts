import { istToday } from '../../lib/time';

export type RangeKey = 'today' | '5d' | '20d' | 'all' | 'custom';
export const RANGE_LABELS: Record<RangeKey, string> = { today: 'Today', '5d': '5D', '20d': '20D', all: 'All', custom: 'Custom' };
export const RANGE_KEYS = Object.keys(RANGE_LABELS) as RangeKey[];
export type BookKey = 'paper' | 'all';

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Calendar-day arithmetic on a YYYY-MM-DD string (no time zone involved). */
export function addDays(day: string, delta: number): string {
  const [y, m, d] = day.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + delta));
  return t.toISOString().slice(0, 10);
}

export function validDate(s: unknown): s is string {
  if (typeof s !== 'string' || !DATE.test(s)) return false;
  return addDays(s, 0) === s;
}

export interface RangeSpec { range: RangeKey; from?: string; to?: string }

/** Returns an error sentence when a custom range cannot be sent to the server. */
export function rangeError(spec: RangeSpec): string | null {
  if (spec.range !== 'custom') return null;
  if (!validDate(spec.from) || !validDate(spec.to)) return 'Enter both dates as YYYY-MM-DD.';
  if (spec.from > spec.to) return 'The start date must not be after the end date.';
  return null;
}

/** IST date bounds for the query string. 'All' sends none. 5D and 20D are calendar days including today. */
export function rangeQuery(spec: RangeSpec, now: Date = new Date()): { from?: string; to?: string } {
  const today = istToday(now);
  switch (spec.range) {
    case 'today': return { from: today, to: today };
    case '5d': return { from: addDays(today, -4), to: today };
    case '20d': return { from: addDays(today, -19), to: today };
    case 'custom': return rangeError(spec) ? {} : { from: spec.from, to: spec.to };
    default: return {};
  }
}

export function cleanRange(raw: Record<string, unknown>): RangeSpec {
  const range = (RANGE_KEYS as string[]).includes(raw.range as string) ? (raw.range as RangeKey) : 'all';
  return { range, from: validDate(raw.from) ? raw.from : undefined, to: validDate(raw.to) ? raw.to : undefined };
}
