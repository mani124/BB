import { describe, it, expect } from 'vitest';
import { PANELS } from './registry';

/** Spec 6.3 parity checklist: items 1-11 are panels; 12-17 live in the shell (checked in shell tests and e2e). */
export const PARITY: { item: number; what: string; panels: string[] }[] = [
  { item: 1, what: 'Signals list with filters, sort, watching, selection', panels: ['signals'] },
  { item: 2, what: 'Focus view for signal, position, candidate', panels: ['focus'] },
  { item: 3, what: 'Open positions list and table with close', panels: ['positions', 'positions-table'] },
  { item: 4, what: 'Chart for a selected position', panels: ['chart'] },
  { item: 5, what: 'Trades list and detail, close paper trade', panels: ['trades'] },
  { item: 6, what: 'Session timeline', panels: ['session'] },
  { item: 7, what: 'Review: costs, setups, telemetry, journal', panels: ['costs', 'setup-stats', 'telemetry', 'journal'] },
  { item: 8, what: 'Earnings book', panels: ['earnings'] },
  { item: 9, what: 'Runtime settings with audit', panels: ['settings'] },
  { item: 10, what: 'Live routing', panels: ['live'] },
  { item: 11, what: 'Control: auto-enter, kill switch, scan, key, setup modes, reset', panels: ['controls'] },
  { item: 13, what: 'Index radar strip', panels: ['market'] },
];

describe('parity registry', () => {
  it('every parity item maps to registered panels', () => {
    const ids = new Set(PANELS.map((d) => d.id));
    for (const row of PARITY) for (const id of row.panels) expect(ids.has(id), `${row.item} ${id}`).toBe(true);
  });
  it('every definition has title, category, icon and sources array', () => {
    for (const d of PANELS) {
      expect(d.title, d.id).toBeTruthy();
      expect(d.category, d.id).toBeTruthy();
      expect(d.icon, d.id).toBeTruthy();
      expect(Array.isArray(d.sources), d.id).toBe(true);
    }
  });
  it('ids are unique', () => {
    expect(new Set(PANELS.map((d) => d.id)).size).toBe(PANELS.length);
  });
});
