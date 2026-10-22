import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useConfirm } from '../features/confirm/ConfirmProvider';
import { Dialog } from '../components/Dialog';
import type { UseLayouts } from '../features/layouts/useLayouts';
import type { Snapshot } from '../features/layouts/layoutApi';
import { pushToast } from '../data/toasts';

type Modal = null | 'saveAs' | 'rename' | 'import' | 'snapshots';

const NameDialog: React.FC<{ title: string; submit: string; initial?: string; onSubmit(name: string): string | null; onClose(): void }> = ({ title, submit, initial = '', onSubmit, onClose }) => {
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog label={title} onClose={onClose} className="p-4" closeOnBackdrop={false}>
      <form style={{ minWidth: 280 }} onSubmit={(e) => { e.preventDefault(); const err = onSubmit(name); if (err) setError(err); else onClose(); }}>
        <h2 className="text-base font-semibold mb-2">{title}</h2>
        <label className="block text-xs desk-muted mb-1" htmlFor="layout-name">Layout name</label>
        <input id="layout-name" className="desk-input w-full" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} autoFocus />
        {error && <p role="alert" className="desk-alert mt-2 text-xs">{error}</p>}
        <div className="flex justify-end gap-2 mt-3"><button type="button" className="desk-btn" onClick={onClose}>Cancel</button><button type="submit" className="desk-btn solid">{submit}</button></div>
      </form>
    </Dialog>
  );
};

const ImportDialog: React.FC<{ onImport(json: string): string | null; onClose(): void }> = ({ onImport, onClose }) => {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog label="Import layout" onClose={onClose} className="p-4" closeOnBackdrop={false}>
      <form style={{ minWidth: 320 }} onSubmit={(e) => { e.preventDefault(); const err = onImport(text); if (err) setError(err); else onClose(); }}>
        <h2 className="text-base font-semibold mb-2">Import layout</h2>
        <label className="block text-xs desk-muted mb-1" htmlFor="layout-json">Layout JSON</label>
        <textarea id="layout-json" className="desk-input w-full font-mono text-xs" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
        {error && <p role="alert" className="desk-alert mt-2 text-xs">{error}</p>}
        <div className="flex justify-end gap-2 mt-3"><button type="button" className="desk-btn" onClick={onClose}>Cancel</button><button type="submit" className="desk-btn solid">Import</button></div>
      </form>
    </Dialog>
  );
};

const SnapshotDialog: React.FC<{ layouts: UseLayouts; onClose(): void }> = ({ layouts, onClose }) => {
  const [rows, setRows] = useState<Snapshot[] | null>(null);
  React.useEffect(() => { void layouts.snapshots().then(setRows); }, [layouts]);
  return (
    <Dialog label="Revert to snapshot" onClose={onClose} className="p-4">
      <div style={{ minWidth: 300 }}>
        <h2 className="text-base font-semibold mb-2">Revert to snapshot</h2>
        {rows === null ? <p className="text-xs desk-muted" role="status">Loading</p> : rows.length === 0 ? <p className="text-xs desk-muted">No snapshots yet for this layout.</p> : (
          <ul className="space-y-1">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 text-xs">
                <span className="desk-num">{r.taken_at}</span>
                <button type="button" className="desk-btn sm" onClick={async () => { const ok = await layouts.restore(r.id); pushToast(ok, ok ? 'Layout restored.' : 'Could not restore that snapshot.'); if (ok) onClose(); }}>Restore</button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end mt-3"><button type="button" className="desk-btn" onClick={onClose}>Close</button></div>
      </div>
    </Dialog>
  );
};

/** Workspace tabs plus the layout management menu. */
export const WorkspaceSwitcher: React.FC<{ layouts: UseLayouts }> = ({ layouts }) => {
  const confirm = useConfirm();
  const [menu, setMenu] = useState(false);
  const [modal, setModal] = useState<Modal>(null);
  const builtIn = layouts.workspaces.includes(layouts.current);

  const close = () => setMenu(false);
  const doReset = async () => {
    close();
    if (await confirm({ title: `Reset ${layouts.current}?`, body: 'The workspace returns to its default layout. Your arrangement is replaced.', confirmLabel: 'Reset workspace', danger: true })) layouts.reset();
  };
  const doDelete = async () => {
    close();
    if (await confirm({ title: `Delete ${layouts.current}?`, body: 'This custom layout is removed.', confirmLabel: 'Delete layout', danger: true })) layouts.remove();
  };
  const doUpdate = async () => {
    close();
    if (await confirm({ title: 'Update to the new default?', body: 'Your changes to this layout are replaced by the new default arrangement.', confirmLabel: 'Update layout', danger: true })) layouts.updateToDefault();
  };
  const doExport = () => {
    close();
    const href = URL.createObjectURL(new Blob([layouts.exportJson()], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = href; a.download = `layout_${layouts.current}.json`; a.click();
    URL.revokeObjectURL(href);
  };

  return (
    <nav aria-label="Workspaces" className="flex items-center gap-1 flex-wrap" data-testid="workspace-switcher">
      {[...layouts.workspaces, ...layouts.customs].map((name) => (
        <button key={name} type="button" className="desk-btn sm" aria-current={layouts.current === name ? 'page' : undefined} aria-pressed={layouts.current === name}
          style={layouts.current === name ? { boxShadow: 'inset 0 -2px 0 var(--accent)', fontWeight: 600 } : undefined} onClick={() => layouts.switchTo(name)}>
          {name}
        </button>
      ))}
      <div className="relative">
        <button type="button" className="desk-btn sm" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
          Layout <ChevronDown className="h-3 w-3" aria-hidden />
        </button>
        {menu && (
          <div role="menu" aria-label="Layout" className="absolute z-50 mt-1 desk-panel p-1 flex flex-col" style={{ minWidth: 200, left: 0 }}
            onKeyDown={(e) => { if (e.key === 'Escape') setMenu(false); }}>
            <button type="button" role="menuitem" className="desk-btn" onClick={() => { close(); setModal('saveAs'); }}>Save layout as…</button>
            <button type="button" role="menuitem" className="desk-btn" disabled={builtIn} onClick={() => { close(); setModal('rename'); }}>Rename…</button>
            <button type="button" role="menuitem" className="desk-btn" disabled={builtIn} onClick={() => { void doDelete(); }}>Delete layout</button>
            <button type="button" role="menuitem" className="desk-btn" onClick={() => { void doReset(); }}>Reset workspace</button>
            <button type="button" role="menuitem" className="desk-btn" onClick={() => { close(); setModal('snapshots'); }}>Revert to snapshot…</button>
            <button type="button" role="menuitem" className="desk-btn" onClick={doExport}>Export layout</button>
            <button type="button" role="menuitem" className="desk-btn" onClick={() => { close(); setModal('import'); }}>Import layout…</button>
            {layouts.presetOutdated && <button type="button" role="menuitem" className="desk-btn" onClick={() => { void doUpdate(); }}>Update to new default</button>}
          </div>
        )}
      </div>
      {modal === 'saveAs' && <NameDialog title="Save layout as" submit="Save" onSubmit={(n) => layouts.saveAs(n)} onClose={() => setModal(null)} />}
      {modal === 'rename' && <NameDialog title="Rename layout" submit="Rename" initial={layouts.current} onSubmit={(n) => layouts.rename(n)} onClose={() => setModal(null)} />}
      {modal === 'import' && <ImportDialog onImport={(j) => { const r = layouts.importJson(j); return r.ok ? null : `Not a valid layout: ${r.reason}.`; }} onClose={() => setModal(null)} />}
      {modal === 'snapshots' && <SnapshotDialog layouts={layouts} onClose={() => setModal(null)} />}
    </nav>
  );
};
