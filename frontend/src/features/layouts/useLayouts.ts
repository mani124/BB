import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { alertsHook } from '../../data/alertsHook';
import { appStore } from '../../data/appStore';
import { PRESET_VERSION, WORKSPACE_NAMES, type LayoutSpec } from './layoutModel';
import { PRESETS } from './presets';
import { deleteLayout, exportLayout, importLayout, isWorkspaceName, layoutKey, listSnapshots, loadLayouts, restoreSnapshot, saveLayout, type ImportResult, type Snapshot } from './layoutApi';
import { validateLayout } from './layoutModel';

const LAST_KEY = 'bb_workspace';

function initialName(): string {
  try {
    const q = new URLSearchParams(window.location.search).get('workspace');
    if (q) return q;
  } catch { /* no window */ }
  try { return localStorage.getItem(LAST_KEY) || 'Trading'; } catch { return 'Trading'; }
}

const preset = (name: string): LayoutSpec => structuredClone(isWorkspaceName(name) ? PRESETS[name] : PRESETS.Trading);

export interface UseLayouts {
  ready: boolean;
  current: string;
  /** Changes when the dock must be rebuilt from `spec` (switch, reset, import, restore). */
  revision: number;
  spec: LayoutSpec;
  workspaces: string[];
  customs: string[];
  switchTo(name: string): void;
  onChange(spec: LayoutSpec): void;
  reset(): void;
  saveAs(name: string): string | null;
  rename(name: string): string | null;
  remove(): void;
  importJson(json: string): ImportResult;
  exportJson(): string;
  snapshots(): Promise<Snapshot[]>;
  restore(id: number): Promise<boolean>;
  presetOutdated: boolean;
  updateToDefault(): void;
  loadError: string | null;
  reportLoadError(reason: string): void;
}

export function useLayouts(): UseLayouts {
  const [ready, setReady] = useState(false);
  const [layouts, setLayouts] = useState<Record<string, LayoutSpec>>({});
  const layoutsRef = useRef(layouts);
  layoutsRef.current = layouts;
  const [current, setCurrent] = useState(initialName);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const warned = useRef(false);

  useEffect(() => {
    let cancelled = false;
    void loadLayouts().then((r) => {
      if (cancelled) return;
      setLayouts(r.layouts);
      if (r.invalid.length && !warned.current) {
        warned.current = true;
        alertsHook.push({ severity: 'warning', source: 'layout', message: 'Saved layout was invalid; default restored' });
      }
      setReady(true);
    });
    return () => { cancelled = true; };
  }, []);

  const spec = useMemo<LayoutSpec>(() => layouts[layoutKey(current)] ?? preset(current), [layouts, current]);
  const customs = useMemo(() => Object.keys(layouts).filter((k) => k.startsWith('custom:')).map((k) => k.slice(7)).sort(), [layouts]);

  const select = useCallback((name: string) => {
    setCurrent(name);
    setRevision((r) => r + 1);
    setLoadError(null);
    try { localStorage.setItem(LAST_KEY, name); } catch { /* storage unavailable */ }
    appStore.setState((s) => ({ ui: { ...s.ui, workspace: name } }));
  }, []);

  const store = useCallback((next: LayoutSpec) => {
    setLayouts((l) => ({ ...l, [layoutKey(next.name)]: next }));
    saveLayout(next);
  }, []);

  const onChange = useCallback((next: LayoutSpec) => { store(next); }, [store]);

  const validName = (name: string, allowSelf?: string): string | null => {
    const n = name.trim();
    if (!n) return 'Enter a name.';
    if (n.length > 40) return 'Use 40 characters or fewer.';
    if (isWorkspaceName(n)) return 'That name belongs to a built-in workspace.';
    if (n !== allowSelf && layoutsRef.current[layoutKey(n)]) return 'A layout with that name already exists.';
    return null;
  };

  return {
    ready, current, revision, spec,
    workspaces: [...WORKSPACE_NAMES],
    customs,
    switchTo: select,
    onChange,
    reset() {
      if (isWorkspaceName(current)) {
        void deleteLayout(current);
        setLayouts((l) => { const c = { ...l }; delete c[layoutKey(current)]; return c; });
      } else {
        const base = spec.based_on && isWorkspaceName(spec.based_on) ? PRESETS[spec.based_on] : PRESETS.Trading;
        store({ ...structuredClone(base), name: current, based_on: base.name });
      }
      setRevision((r) => r + 1);
    },
    saveAs(name) {
      const err = validName(name);
      if (err) return err;
      const n = name.trim();
      const based = spec.based_on ?? (isWorkspaceName(spec.name) ? spec.name : undefined);
      store({ ...structuredClone(spec), name: n, ...(based ? { based_on: based, preset_version: PRESET_VERSION } : {}) });
      select(n);
      return null;
    },
    rename(name) {
      if (isWorkspaceName(current)) return 'Built-in workspaces cannot be renamed.';
      const err = validName(name, current);
      if (err) return err;
      const n = name.trim();
      store({ ...spec, name: n });
      void deleteLayout(current);
      setLayouts((l) => { const c = { ...l }; delete c[layoutKey(current)]; return c; });
      select(n);
      return null;
    },
    remove() {
      if (isWorkspaceName(current)) return;
      void deleteLayout(current);
      setLayouts((l) => { const c = { ...l }; delete c[layoutKey(current)]; return c; });
      select('Trading');
    },
    importJson(json) {
      const r = importLayout(json);
      if (!r.ok) return r;
      store(r.layout);
      select(r.layout.name);
      return r;
    },
    exportJson: () => exportLayout(spec),
    snapshots: () => listSnapshots(current),
    async restore(id) {
      const restored = await restoreSnapshot(current, id);
      if (!restored) return false;
      setLayouts((l) => ({ ...l, [layoutKey(restored.name)]: restored }));
      setRevision((r) => r + 1);
      return true;
    },
    presetOutdated: Boolean(spec.based_on ?? (isWorkspaceName(spec.name) ? spec.name : null)) && (spec.preset_version ?? 0) < PRESET_VERSION,
    updateToDefault() {
      const baseName = spec.based_on ?? spec.name;
      if (!isWorkspaceName(baseName)) return;
      store({ ...structuredClone(PRESETS[baseName]), name: spec.name, based_on: isWorkspaceName(spec.name) ? undefined : baseName });
      setRevision((r) => r + 1);
    },
    loadError,
    reportLoadError(reason) {
      setLoadError(reason);
      alertsHook.push({ severity: 'warning', source: 'layout', message: 'Saved layout was invalid; default restored' });
    },
  };
}

/** Validates then returns the spec to render, or the preset when the saved one fails (used by DockApp as a last guard). */
export function safeSpec(spec: LayoutSpec, name: string): LayoutSpec {
  const v = validateLayout(spec);
  return v.ok ? v.layout : preset(name);
}
