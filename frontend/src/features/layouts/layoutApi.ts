import { apiFetch } from '../../api/client';
import { WORKSPACE_NAMES, validateLayout, type LayoutSpec, type WorkspaceName } from './layoutModel';

const CACHE_KEY = 'bb_layouts';
const DEBOUNCE_MS = 800;
const MIN_GAP_MS = 1000;

interface CacheEntry { updated_at: string; spec: LayoutSpec }
type Cache = Record<string, CacheEntry>;

/** Storage key: presets are `workspace:<name>`, everything else `custom:<name>`. */
export const layoutKey = (name: string): string => ((WORKSPACE_NAMES as string[]).includes(name) ? `workspace:${name}` : `custom:${name}`);
export const isWorkspaceName = (name: string): name is WorkspaceName => (WORKSPACE_NAMES as string[]).includes(name);

function readCache(): Cache {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? (parsed as Cache) : {};
  } catch { return {}; }
}
function writeCache(cache: Cache): void {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch { /* storage unavailable or full */ }
}

export interface LoadedLayouts {
  layouts: Record<string, LayoutSpec>;
  /** Keys whose saved body failed validation (the caller falls back to the preset and warns). */
  invalid: string[];
  /** Panel ids dropped while cleaning saved layouts, per key. */
  dropped: Record<string, string[]>;
  serverOk: boolean;
}

interface ServerRow { name: string; schema_version: number; body: unknown; updated_at: string }

/** Server first, local cache as fallback; per layout the newest `updated_at` wins. Never throws. */
export async function loadLayouts(): Promise<LoadedLayouts> {
  const cache = readCache();
  const candidates: Record<string, { updated_at: string; raw: unknown }> = {};
  for (const [key, e] of Object.entries(cache)) if (e && typeof e === 'object') candidates[key] = { updated_at: String(e.updated_at ?? ''), raw: e.spec };
  let serverOk = false;
  try {
    const res = await apiFetch('/api/ui/layouts');
    if (res.ok) {
      const rows = (await res.json()) as ServerRow[] | { layouts: ServerRow[] };
      const list = Array.isArray(rows) ? rows : rows.layouts;
      serverOk = Array.isArray(list);
      for (const row of serverOk ? list : []) {
        const prev = candidates[row.name];
        if (!prev || String(row.updated_at) >= prev.updated_at) candidates[row.name] = { updated_at: String(row.updated_at), raw: row.body };
      }
    }
  } catch { /* offline or server error: the cache is used */ }

  const layouts: Record<string, LayoutSpec> = {};
  const invalid: string[] = [];
  const dropped: Record<string, string[]> = {};
  for (const [key, c] of Object.entries(candidates)) {
    const v = validateLayout(c.raw);
    if (v.ok) { layouts[key] = v.layout; if (v.dropped.length) dropped[key] = v.dropped; } else invalid.push(key);
  }
  return { layouts, invalid, dropped, serverOk };
}

// ---- Debounced save -------------------------------------------------------------------------------

const timers = new Map<string, ReturnType<typeof setTimeout>>();
const pending = new Map<string, LayoutSpec>();
let lastWrite = 0;

async function put(key: string, spec: LayoutSpec): Promise<void> {
  lastWrite = Date.now();
  try {
    await apiFetch(`/api/ui/layouts/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: key.startsWith('workspace:') ? 'workspace' : 'custom', schema_version: spec.schema_version, body: spec }),
    });
  } catch { /* the cache already holds it; the next change retries */ }
}

/** Writes the cache now and the server after a pause (at most one write per second). */
export function saveLayout(spec: LayoutSpec): void {
  const key = layoutKey(spec.name);
  const cache = readCache();
  cache[key] = { updated_at: new Date().toISOString(), spec };
  writeCache(cache);
  pending.set(key, spec);
  const existing = timers.get(key);
  if (existing) clearTimeout(existing);
  const wait = Math.max(DEBOUNCE_MS, MIN_GAP_MS - Math.max(0, Date.now() - lastWrite));
  timers.set(key, setTimeout(() => {
    timers.delete(key);
    const latest = pending.get(key);
    pending.delete(key);
    if (latest) void put(key, latest);
  }, wait));
}

/** Test helper. */
export function resetLayoutApi(): void {
  for (const t of timers.values()) clearTimeout(t);
  timers.clear();
  pending.clear();
  lastWrite = 0;
}

/** Sends anything still waiting (page hide, tests). */
export async function flushLayouts(): Promise<void> {
  for (const t of timers.values()) clearTimeout(t);
  timers.clear();
  const items = [...pending.entries()];
  pending.clear();
  await Promise.all(items.map(([k, s]) => put(k, s)));
}

export async function deleteLayout(name: string): Promise<void> {
  const key = layoutKey(name);
  const t = timers.get(key);
  if (t) clearTimeout(t);
  timers.delete(key);
  pending.delete(key);
  const cache = readCache();
  delete cache[key];
  writeCache(cache);
  try { await apiFetch(`/api/ui/layouts/${encodeURIComponent(key)}`, { method: 'DELETE' }); } catch { /* cache already cleared */ }
}

export interface Snapshot { id: number; taken_at: string }

export async function listSnapshots(name: string): Promise<Snapshot[]> {
  try {
    const res = await apiFetch(`/api/ui/layouts/${encodeURIComponent(layoutKey(name))}/snapshots`);
    if (!res.ok) return [];
    const rows = await res.json();
    return Array.isArray(rows) ? rows : [];
  } catch { return []; }
}

export async function restoreSnapshot(name: string, id: number): Promise<LayoutSpec | null> {
  try {
    const key = layoutKey(name);
    const res = await apiFetch(`/api/ui/layouts/${encodeURIComponent(key)}/restore/${id}`, { method: 'POST' });
    if (!res.ok) return null;
    const row = await res.json();
    const v = validateLayout((row as { body?: unknown }).body ?? row);
    if (!v.ok) return null;
    const cache = readCache();
    cache[key] = { updated_at: new Date().toISOString(), spec: v.layout };
    writeCache(cache);
    return v.layout;
  } catch { return null; }
}

export function exportLayout(spec: LayoutSpec): string {
  return JSON.stringify(spec, null, 2);
}

export type ImportResult = { ok: true; layout: LayoutSpec; dropped: string[] } | { ok: false; reason: string };

/** Validates pasted or uploaded JSON; nothing is saved here. */
export function importLayout(json: string): ImportResult {
  const v = validateLayout(json);
  return v.ok ? { ok: true, layout: v.layout, dropped: v.dropped } : { ok: false, reason: v.reason };
}
