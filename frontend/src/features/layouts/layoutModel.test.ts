import { describe, it, expect } from 'vitest';
import { PANELS } from '../../panels/registry';
import { PLANNED_PANEL_IDS, PRESETS } from './presets';
import { WORKSPACE_NAMES, allPanelIds, fromDockviewJson, migrateLayout, toDockviewJson, validateLayout, ensureSingletons, type LayoutSpec } from './layoutModel';

const ok = (r: ReturnType<typeof validateLayout>) => { if (!r.ok) throw new Error(r.reason); return r; };

describe('presets', () => {
  it('has the seven workspaces', () => { expect(Object.keys(PRESETS).sort()).toEqual([...WORKSPACE_NAMES].sort()); });
  it('every preset validates and only drops panels that are planned for later phases', () => {
    const planned = new Set(PLANNED_PANEL_IDS);
    const registered = new Set(PANELS.map((d) => d.id));
    for (const name of WORKSPACE_NAMES) {
      const r = ok(validateLayout(PRESETS[name]));
      for (const d of r.dropped) expect(planned.has(d.split('#')[0]) && !registered.has(d.split('#')[0]), `${name}: ${d}`).toBe(true);
      for (const id of allPanelIds(PRESETS[name])) expect(registered.has(id.split('#')[0]) || planned.has(id.split('#')[0]), `${name}: ${id}`).toBe(true);
    }
  });
  it('Trading starts with signals, focus, positions-table and positions', () => {
    const ids = allPanelIds(ok(validateLayout(PRESETS.Trading)).layout);
    for (const id of ['signals', 'focus', 'positions-table', 'positions']) expect(ids).toContain(id);
  });
});

describe('validateLayout', () => {
  it.each([['corrupt JSON string', '{not json'], ['null', null], ['array', []], ['number', 5], ['wrong types', { schema_version: 'x', name: 5, root: 3 }], ['missing root', { schema_version: 1, name: 'x' }]])('%s is rejected', (_n, raw) => {
    expect(validateLayout(raw).ok).toBe(false);
  });
  it('rejects a newer schema', () => {
    const r = validateLayout({ schema_version: 99, name: 'x', root: { type: 'group', panels: [{ id: 'signals' }] } });
    expect(r).toEqual({ ok: false, reason: 'newer schema' });
  });
  it('accepts a JSON string', () => { expect(validateLayout(JSON.stringify(PRESETS.Earnings)).ok).toBe(true); });
  it('drops unknown panels, lists them and keeps the rest valid', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'nope' }, { id: 'signals' }] } }));
    expect(r.dropped).toEqual(['nope']);
    expect(allPanelIds(r.layout)).toEqual(['signals']);
  });
  it('removes a group left empty and renormalises sizes to sum 1', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'split', direction: 'row', sizes: [0.2, 0.3, 0.5], children: [
      { type: 'group', panels: [{ id: 'signals' }] }, { type: 'group', panels: [{ id: 'ghost' }] }, { type: 'group', panels: [{ id: 'focus' }] },
    ] } }));
    expect(r.layout.root.type).toBe('split');
    if (r.layout.root.type === 'split') {
      expect(r.layout.root.children).toHaveLength(2);
      expect(r.layout.root.sizes.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
      expect(r.layout.root.sizes[1] / r.layout.root.sizes[0]).toBeCloseTo(2.5);
    }
  });
  it('collapses a split with a single remaining child', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'split', direction: 'row', sizes: [0.5, 0.5], children: [{ type: 'group', panels: [{ id: 'ghost' }] }, { type: 'group', panels: [{ id: 'focus' }] }] } }));
    expect(r.layout.root.type).toBe('group');
  });
  it('de-duplicates singleton panels but allows several instances of a non-singleton', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'positions' }, { id: 'positions' }, { id: 'positions#2' }, { id: 'signals' }, { id: 'signals#2' }] } }));
    expect(allPanelIds(r.layout)).toEqual(['positions', 'signals', 'signals#2']);
    expect(r.dropped).toEqual(['positions', 'positions#2']);
  });
  it('fails when nothing valid is left', () => {
    expect(validateLayout({ schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'ghost' }] } }).ok).toBe(false);
  });
  it('ensureSingletons returns a clean copy', () => {
    const dup: LayoutSpec = { schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'positions' }, { id: 'positions' }] } };
    expect(allPanelIds(ensureSingletons(dup))).toEqual(['positions']);
  });
  it('drops invalid floating entries', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'signals' }] }, floating: [{ panelId: 'focus', x: 1, y: 2, w: 300, h: 200 }, { panelId: 'chart', x: 'a' }] }));
    expect(r.layout.floating).toHaveLength(1);
  });
});

describe('migrateLayout', () => {
  it('upgrades a v0 layout (tabs / orientation / tree) to v1', () => {
    const v0 = { name: 'old', tree: { orientation: 'vertical', sizes: [1, 1], children: [{ tabs: ['signals'] }, { tabs: ['focus', 'chart'], active: 'chart' }] } };
    const m = migrateLayout(v0) as LayoutSpec;
    expect(m.schema_version).toBe(1);
    const r = ok(validateLayout(v0));
    expect(allPanelIds(r.layout)).toEqual(['signals', 'focus', 'chart']);
    expect(r.layout.root.type === 'split' && r.layout.root.direction).toBe('column');
  });
  it('leaves current layouts alone', () => { expect(migrateLayout(PRESETS.Earnings)).toEqual(PRESETS.Earnings); });
});

describe('dockview conversion', () => {
  it.each(WORKSPACE_NAMES)('%s round-trips through Dockview JSON', (name) => {
    const clean = ok(validateLayout(PRESETS[name])).layout;
    const back = fromDockviewJson(toDockviewJson(clean), clean);
    expect(back).toEqual(clean);
  });
  it('writes known component ids and sizes that sum to the grid size', () => {
    const json = toDockviewJson(ok(validateLayout(PRESETS.Trading)).layout);
    const known = new Set(PANELS.map((d) => d.id));
    for (const p of Object.values(json.panels)) expect(known.has(p.contentComponent)).toBe(true);
    const sum = json.grid.root.data.reduce((a, c) => a + c.size, 0);
    expect(Math.abs(sum - json.grid.width)).toBeLessThan(5);
  });
  it('keeps per-panel params and custom titles', () => {
    const clean = ok(validateLayout(PRESETS.Trading)).layout;
    const json = toDockviewJson(clean);
    expect(json.panels['signals#2'].title).toBe('Earnings watch');
    expect((json.panels['signals#2'].params as { view: { mode: string } }).view.mode).toBe('watching');
  });
  it('floating and popout panels are written as floating groups and read back as floating', () => {
    const spec: LayoutSpec = { schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'signals' }] },
      floating: [{ panelId: 'chart', x: 40, y: 50, w: 400, h: 300 }], popouts: ['session'] };
    const clean = ok(validateLayout(spec)).layout;
    const json = toDockviewJson(clean);
    expect(json.floatingGroups).toHaveLength(2);
    const back = fromDockviewJson(json, clean);
    expect(back.floating?.map((f) => f.panelId)).toEqual(['chart', 'session']);
    expect(back.floating?.[0]).toMatchObject({ x: 40, y: 50, w: 400, h: 300 });
  });
  it('a duplicate of a docked panel in floating is dropped', () => {
    const r = ok(validateLayout({ schema_version: 1, name: 'x', root: { type: 'group', panels: [{ id: 'chart' }] }, floating: [{ panelId: 'chart', x: 1, y: 1, w: 300, h: 200 }] }));
    expect(r.layout.floating).toBeUndefined();
  });
});
