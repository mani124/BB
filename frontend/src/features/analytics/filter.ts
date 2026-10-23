import type { DashboardTrade } from '../../types/dashboard';
import { toIst } from '../../lib/time';

export interface LinkedFilter { group: string; key: string }

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** Does a trade belong to the attribution row the user picked? Unknown groups match everything. */
export function tradeMatches(t: DashboardTrade, f: LinkedFilter | null): boolean {
  if (!f) return true;
  switch (f.group) {
    case 'setup': return t.setup === f.key;
    case 'symbol': return t.instrument === f.key || t.instrument.startsWith(`${f.key} `);
    case 'side': return t.instrument.endsWith(` ${f.key}`);
    case 'exit_reason': return (t.exit_reason ?? '').split(' (')[0].split(':')[0].trim() === f.key;
    case 'hour': case 'weekday': {
      if (!t.opened_at) return false;
      const p = toIst(t.opened_at);
      return f.group === 'hour' ? `${String(p.hour).padStart(2, '0')}:00` === f.key : WEEKDAYS[p.weekday] === f.key;
    }
    default: return true;
  }
}

/** The parts of a linked filter the analytics API understands. */
export function filterToQuery(f: LinkedFilter | null): { setup?: string; side?: string } {
  if (!f) return {};
  if (f.group === 'setup') return { setup: f.key };
  if (f.group === 'side' && (f.key === 'CE' || f.key === 'PE')) return { side: f.key };
  return {};
}
