// The ONLY file that imports Dockview (free MIT edition, pinned in package.json). Everything else talks to DockCommands.
import React, { Suspense, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type IDockviewHeaderActionsProps, type IDockviewPanel, type IDockviewPanelHeaderProps, type IDockviewPanelProps, type IWatermarkPanelProps } from 'dockview-react';
import 'dockview-react/dist/styles/dockview.css';
import { alertsHook } from '../data/alertsHook';
import { pushToast } from '../data/toasts';
import { fromDockviewJson, toDockviewJson, validateLayout, type LayoutSpec } from '../features/layouts/layoutModel';
import { DEFINITIONS } from '../panels/definitions';
import { PanelCommandsContext } from '../panels/PanelCommands';
import { PanelErrorBoundary } from '../panels/PanelErrorBoundary';
import { PanelMenuContext, type PanelMenuItem } from '../panels/PanelFrame';
import { baseId } from '../features/layouts/layoutModel';
import type { DockCommands } from '../features/commands/dockCommands';
import { useTheme } from '../context/ThemeContext';

interface HostContextValue { commands: React.MutableRefObject<DockCommands>; changed: () => void }
const HostContext = React.createContext<HostContextValue | null>(null);

const Loading: React.FC = () => <div className="p-3 text-xs desk-muted" role="status">Loading panel</div>;

const PanelHost: React.FC<IDockviewPanelProps> = ({ api, params, containerApi }) => {
  const host = useContext(HostContext);
  const def = DEFINITIONS.find((d) => d.id === baseId(api.id));
  const [current, setCurrent] = useState<Record<string, unknown>>(params ?? {});
  useEffect(() => {
    const d = api.onDidParametersChange((p) => setCurrent((p ?? {}) as Record<string, unknown>));
    return () => d.dispose();
  }, [api]);
  const setParams = useCallback((p: Record<string, unknown>) => { api.updateParameters(p); setCurrent(p); host?.changed(); }, [api, host]);

  const menu: PanelMenuItem[] = useMemo(() => {
    const run = (fn: (c: DockCommands) => void) => () => { api.setActive(); fn(host!.commands.current); };
    return [
      { id: 'float', label: 'Float', run: run((c) => c.float()) },
      { id: 'dock', label: 'Dock', run: run((c) => c.dock()) },
      { id: 'popout', label: 'Pop out', run: run((c) => c.popOut()) },
      { id: 'next', label: 'Move to next group', run: run((c) => c.movePanelToGroup(1)) },
      { id: 'prev', label: 'Move to previous group', run: run((c) => c.movePanelToGroup(-1)) },
      { id: 'right', label: 'Split right', run: run((c) => c.split('right')) },
      { id: 'down', label: 'Split down', run: run((c) => c.split('down')) },
      { id: 'max', label: 'Maximise or restore', run: run((c) => c.maximise()) },
      { id: 'close', label: 'Close panel', run: run((c) => c.close()) },
    ];
  }, [api, host]);

  if (!def) return <div className="p-3 text-xs desk-muted">Unknown panel {api.id}</div>;
  const Component = def.component;
  void containerApi;
  return (
    <PanelMenuContext.Provider value={menu}>
      <PanelErrorBoundary panel={def.id}><Suspense fallback={<Loading />}>
        <Component id={api.id} params={current} setParams={setParams} api={{ id: api.id, setTitle: (t) => api.setTitle(t), close: () => api.close(), setActive: () => api.setActive() }} />
      </Suspense></PanelErrorBoundary>
    </PanelMenuContext.Provider>
  );
};

/** Tab with the title only. Dockview supplies tab roles; no nested button (axe nested-interactive). Close is Alt+W or the panel menu. */
const TabTitle: React.FC<IDockviewPanelHeaderProps> = ({ api }) => {
  const [title, setTitle] = useState(api.title ?? api.id);
  useEffect(() => {
    const d = api.onDidTitleChange((e) => setTitle(e.title));
    return () => d.dispose();
  }, [api]);
  return <span className="dv-default-tab-content px-2 truncate" title={title}>{title}</span>;
};

const Watermark: React.FC<IWatermarkPanelProps> = () => (
  <div className="p-4 text-sm desk-muted">Empty group: open a panel from the command palette (Ctrl+K).</div>
);

const HeaderActions: React.FC<IDockviewHeaderActionsProps> = () => null;

const COMPONENTS = Object.fromEntries(DEFINITIONS.map((d) => [d.id, PanelHost])) as Record<string, React.FC<IDockviewPanelProps>>;

export interface DockHostProps {
  layout: LayoutSpec;
  onLayoutChange(spec: LayoutSpec): void;
  commandsRef: React.MutableRefObject<DockCommands>;
  /** Called when the saved layout could not be loaded and the fallback was used. */
  onLoadError?(reason: string): void;
  onReset(): void;
}

export const DockHost: React.FC<DockHostProps> = ({ layout, onLayoutChange, commandsRef, onLoadError, onReset }) => {
  const { theme } = useTheme();
  const dockTheme = useMemo(() => ({ name: 'bb', className: 'dockview-theme-bb', colorScheme: theme === 'dark' ? ('dark' as const) : ('light' as const), gap: 0 }), [theme]);
  const apiRef = useRef<DockviewApi | null>(null);
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const loading = useRef(true);
  const kickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resetRef = useRef(onReset);
  resetRef.current = onReset;
  const [popoutIds, setPopoutIds] = useState<string[]>(layout.popouts ?? []);

  const emit = useCallback(() => {
    const api = apiRef.current;
    if (!api || loading.current) return;
    const spec = fromDockviewJson(api.toJSON(), layoutRef.current);
    layoutRef.current = spec;
    onLayoutChange(spec);
  }, [onLayoutChange]);

  const sortedGroups = () => {
    const api = apiRef.current!;
    const rect = (g: { element: HTMLElement }) => g.element.getBoundingClientRect();
    return [...api.groups].sort((a, b) => { const ra = rect(a); const rb = rect(b); return Math.abs(ra.top - rb.top) > 8 ? ra.top - rb.top : ra.left - rb.left; });
  };

  const buildCommands = useCallback((): DockCommands => {
    const api = () => apiRef.current!;
    const activePanel = (): IDockviewPanel | undefined => api().activePanel;
    return {
      openPanel(id, opts) {
        const a = api();
        const def = DEFINITIONS.find((d) => d.id === id);
        if (!def) return;
        const existing = a.panels.filter((p) => baseId(p.id) === id);
        if (existing.length && (def.singleton || !opts?.newInstance)) { existing[0].api.setActive(); return; }
        let newId = id;
        for (let n = 2; a.getPanel(newId); n += 1) newId = `${id}#${n}`;
        const ref = a.activeGroup;
        a.addPanel({ id: newId, component: id, title: def.title, ...(ref ? { position: { referenceGroup: ref } } : {}) });
        a.getPanel(newId)?.api.setActive();
      },
      focusGroup(dir) {
        const groups = sortedGroups();
        if (!groups.length) return;
        const cur = groups.findIndex((g) => g.id === api().activeGroup?.id);
        const next = groups[(cur + dir + groups.length) % groups.length];
        next.api.setActive();
        next.element.querySelector<HTMLElement>('[role="tab"][aria-selected="true"], .dv-tab')?.focus();
      },
      nextTab() { cycleTab(1); },
      prevTab() { cycleTab(-1); },
      movePanelToGroup(dir) {
        const p = activePanel();
        const groups = sortedGroups().filter((g) => g.api.location.type === 'grid');
        if (!p || groups.length < 2) return;
        const cur = groups.findIndex((g) => g.id === p.group.id);
        const target = groups[(cur + dir + groups.length) % groups.length];
        p.api.moveTo({ group: target });
        p.api.setActive();
      },
      split(dir) {
        const p = activePanel();
        if (!p) return;
        if (p.group.panels.length < 2) { pushToast(false, 'A group with one panel cannot be split. Open another panel in it first.'); return; }
        const g = api().addGroup({ referenceGroup: p.group, direction: dir === 'right' ? 'right' : 'below' });
        p.api.moveTo({ group: g });
        p.api.setActive();
      },
      float() {
        const p = activePanel();
        if (!p || p.api.location.type === 'floating') return;
        api().addFloatingGroup(p, { x: 120, y: 90, width: 520, height: 380 });
      },
      dock() {
        const p = activePanel();
        if (!p || p.api.location.type !== 'floating') return;
        const target = sortedGroups().find((g) => g.api.location.type === 'grid');
        if (target) { p.api.moveTo({ group: target }); p.api.setActive(); }
      },
      popOut() {
        const p = activePanel();
        if (!p) return;
        void api().addPopoutGroup(p, { popoutUrl: '/popout.html' }).then((ok) => {
          if (!ok) {
            const message = 'Pop-out was blocked by the browser. Allow pop-ups for this site.';
            alertsHook.push({ severity: 'warning', source: 'dock.popout', message });
            pushToast(false, message);
          }
        }).catch(() => {
          const message = 'Pop-out was blocked by the browser. Allow pop-ups for this site.';
          alertsHook.push({ severity: 'warning', source: 'dock.popout', message });
          pushToast(false, message);
        });
      },
      maximise() {
        const p = activePanel();
        if (api().hasMaximizedGroup()) api().exitMaximizedGroup();
        else if (p) api().maximizeGroup(p);
      },
      close() { activePanel()?.api.close(); },
      resetWorkspace() { resetRef.current(); },
    };

    function cycleTab(dir: 1 | -1) {
      const g = api().activeGroup;
      const p = activePanel();
      if (!g || !p || g.panels.length < 2) return;
      const i = g.panels.findIndex((x) => x.id === p.id);
      g.panels[(i + dir + g.panels.length) % g.panels.length].api.setActive();
    }
  }, []);

  useEffect(() => { commandsRef.current = buildCommands(); }, [buildCommands, commandsRef]);

  const onReady = useCallback((e: DockviewReadyEvent) => {
    apiRef.current = e.api;
    commandsRef.current = buildCommands();
    loading.current = true;
    let spec = layoutRef.current;
    try {
      const v = validateLayout(spec);
      if (!v.ok) throw new Error(v.reason);
      spec = v.layout;
      e.api.fromJSON(toDockviewJson(spec) as never);
    } catch (err) {
      const reason = err instanceof Error ? err.message : 'unknown';
      onLoadError?.(reason);
      try { e.api.clear(); } catch { /* nothing to clear */ }
    }
    loading.current = false;
    const kick = () => { if (kickTimer.current) clearTimeout(kickTimer.current); kickTimer.current = setTimeout(emit, 50); };
    e.api.onDidLayoutChange(kick);
    e.api.onDidActivePanelChange(kick);
    e.api.onDidMovePanel(kick);
    e.api.onDidAddPanel(kick);
    e.api.onDidRemovePanel(kick);
    e.api.onDidAddGroup(kick);
    e.api.onDidRemoveGroup(kick);
  }, [buildCommands, commandsRef, emit, onLoadError]);

  useEffect(() => () => { if (kickTimer.current) clearTimeout(kickTimer.current); }, []);

  const hostEl = useRef<HTMLDivElement>(null);
  // Dockview puts aria-level="0" on floating-group dialogs, which is not a valid value. Drop it so assistive tools do not trip on it.
  useEffect(() => {
    const el = hostEl.current;
    if (!el) return undefined;
    const clean = () => el.querySelectorAll('.dv-resize-container[aria-level]').forEach((n) => n.removeAttribute('aria-level'));
    clean();
    const mo = new MutationObserver(clean);
    mo.observe(el, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-level'] });
    return () => mo.disconnect();
  }, []);

  const reopenPopouts = () => {
    const a = apiRef.current;
    if (!a) return;
    for (const id of popoutIds) { const p = a.getPanel(id); if (p) void a.addPopoutGroup(p, { popoutUrl: '/popout.html' }); }
    setPopoutIds([]);
  };

  const ctx = useMemo<HostContextValue>(() => ({ commands: commandsRef, changed: emit }), [commandsRef, emit]);
  const panelCommands = useMemo(() => ({ openPanel: (id: string) => commandsRef.current.openPanel(id) }), [commandsRef]);

  return (
    <HostContext.Provider value={ctx}>
      <PanelCommandsContext.Provider value={panelCommands}>
        {popoutIds.length > 0 && (
          <div className="px-2 py-1 text-xs flex items-center gap-2" role="status" data-testid="popout-banner" style={{ background: 'var(--alt)', borderBottom: '1px solid var(--line)' }}>
            {popoutIds.length} panel{popoutIds.length > 1 ? 's were' : ' was'} in a pop-out window. Browsers need a click to open windows.
            <button type="button" className="desk-btn sm" onClick={reopenPopouts}>Re-open pop-outs</button>
          </div>
        )}
        <div ref={hostEl} data-theme-mode={theme} style={{ height: '100%', width: '100%' }} data-testid="dock-host">
          <DockviewReact theme={dockTheme} components={COMPONENTS} defaultTabComponent={TabTitle} watermarkComponent={Watermark}
            rightHeaderActionsComponent={HeaderActions} onReady={onReady} />
        </div>
      </PanelCommandsContext.Provider>
    </HostContext.Provider>
  );
};
