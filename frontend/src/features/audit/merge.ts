export type AuditSource = 'operator' | 'settings' | 'live';
export interface AuditRow {
  id: string; ts: string; source: AuditSource; actor: string; action: string; target: string; outcome: string; detail: string;
  before?: string; after?: string;
}

type Raw = Record<string, unknown>;
const s = (v: unknown): string => (v === null || v === undefined ? '' : String(v));

export const fromActions = (rows: Raw[]): AuditRow[] => rows.map((r) => ({
  id: `operator:${s(r.id)}`, ts: s(r.ts), source: 'operator', actor: s(r.client) || 'dashboard', action: s(r.action), target: s(r.target),
  outcome: s(r.outcome), detail: s(r.detail) || `${s(r.method)} ${s(r.route)} → ${s(r.status)}`,
}));

export const fromSettings = (rows: Raw[]): AuditRow[] => rows.map((r, i) => ({
  id: `settings:${s(r.changed_at)}:${s(r.key)}:${i}`, ts: s(r.changed_at), source: 'settings', actor: s(r.actor) || 'dashboard', action: 'setting.change', target: s(r.key),
  outcome: 'ok', detail: `${s(r.old_value)} → ${s(r.new_value)}`, before: s(r.old_value), after: s(r.new_value),
}));

export const fromLive = (rows: Raw[]): AuditRow[] => rows.map((r) => ({
  id: `live:${s(r.id)}`, ts: s(r.ts), source: 'live', actor: s(r.actor) || 'system', action: s(r.action), target: '', outcome: 'ok', detail: s(r.detail),
}));

const time = (t: string): number => { const v = new Date(t).getTime(); return Number.isFinite(v) ? v : 0; };

/** Newest first across sources. Rows with unreadable times sort last. */
export function mergeAudit(...lists: AuditRow[][]): AuditRow[] {
  return lists.flat().sort((a, b) => time(b.ts) - time(a.ts));
}

export interface AuditFilter { source: AuditSource | 'all'; outcome: string; text: string; day: string }

export function filterAudit(rows: AuditRow[], f: AuditFilter): AuditRow[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter((r) => (f.source === 'all' || r.source === f.source)
    && (f.outcome === 'all' || r.outcome === f.outcome)
    && (!f.day || r.ts.slice(0, 10) === f.day)
    && (!q || `${r.action} ${r.target} ${r.detail} ${r.actor}`.toLowerCase().includes(q)));
}
