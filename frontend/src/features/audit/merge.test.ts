import { describe, it, expect } from 'vitest';
import { filterAudit, fromActions, fromLive, fromSettings, mergeAudit } from './merge';

const ops = fromActions([{ id: 1, ts: '2026-10-22T10:00:00+05:30', action: 'paper.close', target: 'P1', outcome: 'ok', method: 'POST', route: '/api/paper/close/P1', status: 200 }]);
const set = fromSettings([{ changed_at: '2026-10-22T11:00:00+05:30', key: 'max_open_positions', old_value: '5', new_value: '6', actor: 'dashboard' }]);
const live = fromLive([{ id: 7, ts: '2026-10-22T09:00:00+05:30', actor: 'system', action: 'mode', detail: 'dry run' }]);

describe('audit merge', () => {
  it('orders newest first across sources', () => { expect(mergeAudit(ops, set, live).map((r) => r.source)).toEqual(['settings', 'operator', 'live']); });
  it('keeps before and after for settings rows', () => { expect(set[0]).toMatchObject({ before: '5', after: '6', detail: '5 → 6', action: 'setting.change' }); });
  it('rows with unreadable times sort last', () => { expect(mergeAudit([{ ...ops[0], ts: 'bad' }], set).map((r) => r.source)).toEqual(['settings', 'operator']); });
  it('filters by source, outcome, text and day', () => {
    const all = mergeAudit(ops, set, live);
    expect(filterAudit(all, { source: 'live', outcome: 'all', text: '', day: '' })).toHaveLength(1);
    expect(filterAudit(all, { source: 'all', outcome: 'error', text: '', day: '' })).toHaveLength(0);
    expect(filterAudit(all, { source: 'all', outcome: 'all', text: 'MAX_OPEN', day: '' })).toHaveLength(1);
    expect(filterAudit(all, { source: 'all', outcome: 'all', text: '', day: '2026-10-21' })).toHaveLength(0);
  });
});
