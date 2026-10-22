import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Briefcase, Crosshair, ListFilter, MoreHorizontal, Table2 } from 'lucide-react';
import { useApp } from '../data/appStore';
import { PANELS, type PanelCategory, type PanelDefinition, type PanelId } from '../panels/registry';
import { PanelCommandsContext } from '../panels/PanelCommands';

type Pane = 'signals' | 'detail' | 'positions' | 'tables' | 'more';

const PANE_PANEL: Record<Exclude<Pane, 'tables' | 'more'>, PanelId> = { signals: 'signals', detail: 'focus', positions: 'positions' };
const TABLE_PANELS: PanelId[] = ['positions-table', 'trades', 'session'];
const CATEGORY_LABEL: Record<PanelCategory, string> = { trading: 'Trading', risk: 'Risk', performance: 'Performance', execution: 'Execution', operations: 'Operations', books: 'Books', review: 'Review' };

const Loading: React.FC = () => <div className="p-3 text-xs desk-muted" role="status">Loading panel</div>;

/** Renders one registry panel full screen. Params live in this component (phones do not persist layouts). */
const FullPanel: React.FC<{ def: PanelDefinition }> = ({ def }) => {
  const [params, setParams] = useState<Record<string, unknown>>({});
  const Component = def.component;
  return (
    <Suspense fallback={<Loading />}>
      <Component id={def.id} params={params} setParams={setParams} />
    </Suspense>
  );
};

const byId = (id: PanelId): PanelDefinition | undefined => PANELS.find((d) => d.id === id);

/** Phone layout (< 1024 px): four panes behind a bottom nav, and "More" for every other registered panel. */
export const MobileShell: React.FC = () => {
  const [pane, setPane] = useState<Pane>('signals');
  const [tableId, setTableId] = useState<PanelId>('positions-table');
  const [moreId, setMoreId] = useState<PanelId | null>(null);
  const selection = useApp((s) => s.selection);
  const prev = useRef(selection);

  // Choosing something in Signals or Positions shows it in Detail (the behaviour of the legacy terminal).
  useEffect(() => {
    if (selection && (prev.current?.kind !== selection.kind || prev.current?.id !== selection.id)) {
      setPane((p) => (p === 'signals' || p === 'positions' ? 'detail' : p));
    }
    prev.current = selection;
  }, [selection]);

  const openPanel = useCallback((id: PanelId) => {
    const known = (Object.entries(PANE_PANEL) as [Pane, PanelId][]).find(([, pid]) => pid === id);
    if (known) { setPane(known[0]); setMoreId(null); return; }
    if (TABLE_PANELS.includes(id)) { setTableId(id); setPane('tables'); setMoreId(null); return; }
    setMoreId(id); setPane('more');
  }, []);
  const commands = useMemo(() => ({ openPanel }), [openPanel]);

  const bar: { id: Pane; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'signals', label: 'Signals', Icon: ListFilter },
    { id: 'detail', label: 'Detail', Icon: Crosshair },
    { id: 'positions', label: 'Positions', Icon: Briefcase },
    { id: 'tables', label: 'Tables', Icon: Table2 },
    { id: 'more', label: 'More', Icon: MoreHorizontal },
  ];

  const moreDef = moreId ? byId(moreId) : undefined;
  const categories = useMemo(() => {
    const groups = new Map<PanelCategory, PanelDefinition[]>();
    for (const d of PANELS) groups.set(d.category, [...(groups.get(d.category) ?? []), d]);
    return [...groups.entries()];
  }, []);

  let body: React.ReactNode;
  if (pane === 'more') {
    body = moreDef ? (
      <div className="flex flex-col min-h-0 h-full">
        <div className="px-2 py-1" style={{ borderBottom: '1px solid var(--line)' }}>
          <button type="button" className="desk-btn" onClick={() => setMoreId(null)}><ArrowLeft className="h-4 w-4" aria-hidden /> Back</button>
        </div>
        <div className="flex-1 min-h-0"><FullPanel key={moreDef.id} def={moreDef} /></div>
      </div>
    ) : (
      <div className="desk-scroll p-3 flex flex-col gap-4 h-full" tabIndex={0} aria-label="All panels">
        {categories.map(([cat, defs]) => (
          <section key={cat} aria-label={CATEGORY_LABEL[cat]}>
            <h2 className="desk-label mb-1">{CATEGORY_LABEL[cat]}</h2>
            <ul className="grid grid-cols-2 gap-2">
              {defs.map((d) => (
                <li key={d.id}><button type="button" className="desk-btn w-full" onClick={() => openPanel(d.id)}>{d.title}</button></li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    );
  } else if (pane === 'tables') {
    const def = byId(tableId);
    body = (
      <div className="flex flex-col min-h-0 h-full">
        <div className="desk-seg m-2 self-start" role="group" aria-label="Tables">
          {TABLE_PANELS.map((id) => <button key={id} type="button" aria-pressed={tableId === id} onClick={() => setTableId(id)}>{byId(id)?.title ?? id}</button>)}
        </div>
        <div className="flex-1 min-h-0">{def && <FullPanel key={def.id} def={def} />}</div>
      </div>
    );
  } else {
    const def = byId(PANE_PANEL[pane]);
    body = def ? <FullPanel key={def.id} def={def} /> : null;
  }

  return (
    <PanelCommandsContext.Provider value={commands}>
      <div className="flex flex-col min-h-0 h-full" data-testid="mobile-shell">
        <div className="flex-1 min-h-0 overflow-hidden" role="group" aria-label="Screen">{body}</div>
        <nav className="desk-panebar" aria-label="Screen sections">
          {bar.map(({ id, label, Icon }) => (
            <button key={id} type="button" className="desk-navtab" aria-current={pane === id ? 'page' : undefined} onClick={() => { setPane(id); if (id === 'more') setMoreId(null); }}>
              <Icon className="h-[18px] w-[18px]" aria-hidden /><span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
    </PanelCommandsContext.Provider>
  );
};
