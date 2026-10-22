import { PANELS, type PanelDefinition, type PanelId } from '../../panels/registry';

export const LAYOUT_SCHEMA_VERSION = 1;
export const PRESET_VERSION = 1;

export type WorkspaceName = 'Trading' | 'Risk' | 'Performance' | 'Execution' | 'Review' | 'Operations' | 'Earnings';
export const WORKSPACE_NAMES: WorkspaceName[] = ['Trading', 'Risk', 'Performance', 'Execution', 'Review', 'Operations', 'Earnings'];

export interface LayoutPanel { id: PanelId; params?: Record<string, unknown>; title?: string }
export type LayoutNode =
  | { type: 'split'; direction: 'row' | 'column'; sizes: number[]; children: LayoutNode[] }
  | { type: 'group'; panels: LayoutPanel[]; active?: PanelId };
export interface FloatingPanel { panelId: PanelId; x: number; y: number; w: number; h: number }
export interface LayoutSpec {
  schema_version: number;
  name: string;
  based_on?: string;
  preset_version?: number;
  root: LayoutNode;
  floating?: FloatingPanel[];
  popouts?: PanelId[];
}

/** Panel instance ids are the definition id, or `<id>#<n>` for extra instances of non-singleton panels. */
export const baseId = (id: PanelId): string => id.split('#')[0];

export function collectPanels(node: LayoutNode): LayoutPanel[] {
  return node.type === 'group' ? node.panels : node.children.flatMap(collectPanels);
}

export const allPanelIds = (spec: LayoutSpec): PanelId[] => [
  ...collectPanels(spec.root).map((p) => p.id), ...(spec.floating ?? []).map((f) => f.panelId), ...(spec.popouts ?? []),
];

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Append-only migrations keyed by the schema version they upgrade from. Unversioned (v0) layouts used `tabs`, `orientation`, `tree`. */
export function migrateLayout(raw: unknown): unknown {
  if (!isObj(raw)) return raw;
  let cur: Record<string, unknown> = raw;
  if (!isNum(cur.schema_version)) {
    const mapNode = (n: unknown): unknown => {
      if (!isObj(n)) return n;
      if (Array.isArray(n.children)) {
        return { type: 'split', direction: n.orientation === 'vertical' ? 'column' : 'row', sizes: n.sizes, children: n.children.map(mapNode) };
      }
      const tabs = Array.isArray(n.tabs) ? n.tabs : [];
      return { type: 'group', panels: tabs.map((id) => ({ id })), active: n.active };
    };
    cur = { ...cur, schema_version: 1, root: mapNode(cur.tree ?? cur.root) };
    delete cur.tree;
  }
  return cur;
}

type Fail = { ok: false; reason: string };
export type Validated = { ok: true; layout: LayoutSpec; dropped: string[] } | Fail;

function normalise(sizes: unknown, n: number): number[] {
  const arr = Array.isArray(sizes) && sizes.length === n && sizes.every((s) => isNum(s) && s > 0) ? (sizes as number[]) : Array.from({ length: n }, () => 1);
  const sum = arr.reduce((a, b) => a + b, 0);
  return arr.map((s) => s / sum);
}

/**
 * Validates untrusted layout JSON (string or object). Unknown panel ids are dropped and listed; groups left empty are removed;
 * sizes are renormalised to sum 1; a duplicate singleton panel is dropped.
 */
export function validateLayout(raw: unknown, registry: PanelDefinition[] = PANELS): Validated {
  let value = raw;
  if (typeof value === 'string') {
    try { value = JSON.parse(value); } catch { return { ok: false, reason: 'not valid JSON' }; }
  }
  if (!isObj(value)) return { ok: false, reason: 'not an object' };
  if (isNum(value.schema_version) && value.schema_version > LAYOUT_SCHEMA_VERSION) return { ok: false, reason: 'newer schema' };
  const migrated = migrateLayout(value);
  if (!isObj(migrated)) return { ok: false, reason: 'not an object' };
  if (typeof migrated.name !== 'string' || !migrated.name) return { ok: false, reason: 'missing name' };
  if (!isObj(migrated.root)) return { ok: false, reason: 'missing root' };

  const defs = new Map(registry.map((d) => [d.id, d]));
  const dropped: string[] = [];
  const seen = new Set<string>();
  const accept = (id: unknown): id is string => {
    if (typeof id !== 'string' || !id) return false;
    const def = defs.get(baseId(id));
    if (!def) { dropped.push(id); return false; }
    if (seen.has(id) || (def.singleton && [...seen].some((s) => baseId(s) === def.id))) { dropped.push(id); return false; }
    seen.add(id);
    return true;
  };

  const clean = (n: unknown, depth: number): LayoutNode | null => {
    if (!isObj(n) || depth > 12) return null;
    if (n.type === 'group') {
      if (!Array.isArray(n.panels)) return null;
      const panels: LayoutPanel[] = [];
      for (const p of n.panels) {
        if (!isObj(p) || !accept(p.id)) continue;
        panels.push({ id: p.id as string, ...(isObj(p.params) ? { params: p.params } : {}), ...(typeof p.title === 'string' ? { title: p.title } : {}) });
      }
      if (panels.length === 0) return null;
      const active = typeof n.active === 'string' && panels.some((p) => p.id === n.active) ? n.active : panels[0].id;
      return { type: 'group', panels, active };
    }
    if (n.type === 'split') {
      if (!Array.isArray(n.children) || (n.direction !== 'row' && n.direction !== 'column')) return null;
      const kept: { node: LayoutNode; size: unknown }[] = [];
      n.children.forEach((c, i) => {
        const node = clean(c, depth + 1);
        if (node) kept.push({ node, size: Array.isArray(n.sizes) ? n.sizes[i] : undefined });
      });
      if (kept.length === 0) return null;
      if (kept.length === 1) return kept[0].node;
      const sizes = normalise(kept.map((k) => k.size), kept.length);
      return { type: 'split', direction: n.direction, sizes, children: kept.map((k) => k.node) };
    }
    return null;
  };

  const root = clean(migrated.root, 0);
  if (!root) return { ok: false, reason: 'no valid panels' };

  const floating: FloatingPanel[] = [];
  if (Array.isArray(migrated.floating)) {
    for (const f of migrated.floating) {
      if (isObj(f) && isNum(f.x) && isNum(f.y) && isNum(f.w) && isNum(f.h) && accept(f.panelId)) floating.push({ panelId: f.panelId as string, x: f.x, y: f.y, w: Math.max(120, f.w), h: Math.max(80, f.h) });
    }
  }
  const popouts: PanelId[] = [];
  if (Array.isArray(migrated.popouts)) for (const id of migrated.popouts) if (accept(id)) popouts.push(id as string);

  const layout: LayoutSpec = {
    schema_version: LAYOUT_SCHEMA_VERSION,
    name: migrated.name,
    ...(typeof migrated.based_on === 'string' ? { based_on: migrated.based_on } : {}),
    ...(isNum(migrated.preset_version) ? { preset_version: migrated.preset_version } : {}),
    root,
    ...(floating.length ? { floating } : {}),
    ...(popouts.length ? { popouts } : {}),
  };
  return { ok: true, layout, dropped };
}

/** Removes duplicate singleton panels (keeps the first). Pure; used after programmatic edits. */
export function ensureSingletons(spec: LayoutSpec, registry: PanelDefinition[] = PANELS): LayoutSpec {
  const res = validateLayout(spec, registry);
  return res.ok ? res.layout : spec;
}

// ---- Dockview JSON ------------------------------------------------------------------------------

const NOMINAL = 1000;
interface DvLeaf { type: 'leaf'; data: { views: string[]; activeView?: string; id: string }; size: number }
interface DvBranch { type: 'branch'; data: (DvLeaf | DvBranch)[]; size: number }
export interface DockviewJson {
  grid: { root: DvBranch; width: number; height: number; orientation: 'HORIZONTAL' | 'VERTICAL' };
  panels: Record<string, { id: string; contentComponent: string; title: string; params?: Record<string, unknown> }>;
  activeGroup?: string;
  floatingGroups?: { data: { views: string[]; activeView?: string; id: string }; position: { left: number; top: number; width: number; height: number } }[];
  popoutGroups?: unknown[];
}

export function toDockviewJson(spec: LayoutSpec, registry: PanelDefinition[] = PANELS): DockviewJson {
  const defs = new Map(registry.map((d) => [d.id, d]));
  const panels: DockviewJson['panels'] = {};
  let groupSeq = 0;
  const addPanel = (p: LayoutPanel) => {
    const def = defs.get(baseId(p.id));
    panels[p.id] = { id: p.id, contentComponent: baseId(p.id), title: p.title ?? def?.title ?? p.id, ...(p.params ? { params: p.params } : {}) };
  };
  const rootNode: LayoutNode = spec.root.type === 'group' ? { type: 'split', direction: 'row', sizes: [1], children: [spec.root] } : spec.root;
  let firstGroup: string | undefined;

  const conv = (n: LayoutNode, size: number): DvLeaf | DvBranch => {
    if (n.type === 'group') {
      n.panels.forEach(addPanel);
      const id = String(++groupSeq);
      firstGroup ??= id;
      return { type: 'leaf', size, data: { views: n.panels.map((p) => p.id), activeView: n.active ?? n.panels[0]?.id, id } };
    }
    const total = n.direction === 'row' ? NOMINAL : NOMINAL;
    return { type: 'branch', size, data: n.children.map((c, i) => conv(c, Math.round(n.sizes[i] * total))) };
  };
  const rootBranch = conv(rootNode, NOMINAL) as DvBranch;

  const floatingGroups: NonNullable<DockviewJson['floatingGroups']> = [];
  const floats: FloatingPanel[] = [
    ...(spec.floating ?? []),
    ...(spec.popouts ?? []).map((panelId, i) => ({ panelId, x: 80 + i * 32, y: 80 + i * 32, w: 520, h: 380 })),
  ];
  for (const f of floats) {
    addPanel({ id: f.panelId });
    const id = String(++groupSeq);
    floatingGroups.push({ data: { views: [f.panelId], activeView: f.panelId, id }, position: { left: f.x, top: f.y, width: f.w, height: f.h } });
  }
  return {
    grid: { root: rootBranch, width: NOMINAL, height: NOMINAL, orientation: rootNode.type === 'split' && rootNode.direction === 'column' ? 'VERTICAL' : 'HORIZONTAL' },
    panels,
    activeGroup: firstGroup,
    ...(floatingGroups.length ? { floatingGroups } : {}),
  };
}

/** Reads Dockview's `toJSON()` back into our spec; `based` supplies the name and preset metadata. */
export function fromDockviewJson(json: unknown, based?: LayoutSpec): LayoutSpec {
  const j = json as DockviewJson;
  const paramsOf = (id: string): Pick<LayoutPanel, 'params' | 'title'> => {
    const p = j.panels?.[id];
    const out: Pick<LayoutPanel, 'params' | 'title'> = {};
    if (p?.params && Object.keys(p.params).length) out.params = p.params;
    if (p && p.title && p.title !== getTitle(baseId(id))) out.title = p.title;
    return out;
  };
  const getTitle = (id: string) => PANELS.find((d) => d.id === id)?.title;
  const horizontal = j.grid.orientation === 'HORIZONTAL';
  const conv = (n: DvLeaf | DvBranch, rowDir: boolean): LayoutNode => {
    if (n.type === 'leaf') {
      return { type: 'group', panels: n.data.views.map((id) => ({ id, ...paramsOf(id) })), ...(n.data.activeView ? { active: n.data.activeView } : {}) };
    }
    const total = n.data.reduce((a, c) => a + c.size, 0) || 1;
    return { type: 'split', direction: rowDir ? 'row' : 'column', sizes: n.data.map((c) => c.size / total), children: n.data.map((c) => conv(c, !rowDir)) };
  };
  let root = conv(j.grid.root, horizontal);
  // A one-child root branch is how Dockview stores a single group.
  if (root.type === 'split' && root.children.length === 1) root = root.children[0];
  const floating: FloatingPanel[] = (j.floatingGroups ?? []).flatMap((g) => g.data.views.slice(0, 1).map((panelId) => ({ panelId, x: Math.round(g.position.left ?? 0), y: Math.round(g.position.top ?? 0), w: Math.round(g.position.width), h: Math.round(g.position.height) })));
  const popouts = ((j.popoutGroups ?? []) as { data?: { views: string[] } }[]).flatMap((g) => g.data?.views ?? []);
  return {
    schema_version: LAYOUT_SCHEMA_VERSION,
    name: based?.name ?? 'Custom',
    ...(based?.based_on ? { based_on: based.based_on } : {}),
    ...(based?.preset_version ? { preset_version: based.preset_version } : {}),
    root,
    ...(floating.length ? { floating } : {}),
    ...(popouts.length ? { popouts } : {}),
  };
}
