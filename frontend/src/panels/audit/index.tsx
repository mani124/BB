import React, { useMemo, useState } from 'react';
import { useApiData } from '../../data/hooks/useApiData';
import { filterAudit, fromActions, fromLive, fromSettings, mergeAudit, type AuditFilter, type AuditRow } from '../../features/audit/merge';
import { formatIst, istToday } from '../../lib/time';
import { downloadCsv, toCsv } from '../../lib/csv';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

type Raw = Record<string, unknown>;
const COLS = [
  { key: 'ts', label: 'Time' }, { key: 'source', label: 'Source' }, { key: 'actor', label: 'Actor' }, { key: 'action', label: 'Action' },
  { key: 'target', label: 'Target' }, { key: 'outcome', label: 'Outcome' }, { key: 'detail', label: 'Detail' },
];
const tone = (o: string) => (o === 'ok' ? 'up' : o === 'error' ? 'down' : o === 'denied' ? 'warn' : 'mute');

const AuditPanel: React.FC<PanelProps> = () => {
  const ops = useApiData<Raw[]>('/api/audit/actions?limit=500', { refreshMs: 60_000 });
  const settings = useApiData<Raw[]>('/api/settings/audit?limit=300', { refreshMs: 60_000 });
  const live = useApiData<Raw[]>('/api/live/audit?limit=300', { refreshMs: 60_000 });
  const [f, setF] = useState<AuditFilter>({ source: 'all', outcome: 'all', text: '', day: '' });
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => mergeAudit(fromActions(ops.data ?? []), fromSettings(settings.data ?? []), fromLive(live.data ?? [])), [ops.data, settings.data, live.data]);
  const shown = useMemo(() => filterAudit(rows, f), [rows, f]);
  const failed = [['operator actions', ops], ['settings changes', settings], ['live routing', live]] as const;
  const exportCsv = () => downloadCsv(`audit_${istToday()}.csv`, toCsv(shown as unknown as Record<string, unknown>[], COLS));
  return (
    <PanelFrame title="Audit trail" sources={[]} exportCsv={exportCsv} onRetry={() => { ops.reload(); settings.reload(); live.reload(); }}>
      {failed.filter(([, h]) => h.error).map(([name, h]) => (
        <div key={name} className="desk-alert text-xs flex items-center gap-2" role="alert">
          <span>Could not load {name}: {h.error}. Other sources are still listed.</span>
          <button type="button" className="desk-btn ml-auto" onClick={h.reload}>Retry</button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 px-2 py-1 text-xs" style={{ borderBottom: '1px solid var(--line)' }}>
        <label>Source <select className="desk-input" style={{ width: 'auto' }} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value as AuditFilter['source'] })}>
          <option value="all">All</option><option value="operator">Operator actions</option><option value="settings">Settings</option><option value="live">Live routing</option></select></label>
        <label>Outcome <select className="desk-input" style={{ width: 'auto' }} value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })}>
          <option value="all">All</option><option value="ok">ok</option><option value="error">error</option><option value="denied">denied</option></select></label>
        <label>Day <input className="desk-input" style={{ width: '8.5rem' }} placeholder="YYYY-MM-DD" value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} /></label>
        <label>Search <input className="desk-input" style={{ width: '10rem' }} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} aria-label="Search audit rows" /></label>
        <span className="desk-muted ml-auto">{shown.length} of {rows.length} rows. The trail is read-only.</span>
      </div>
      {shown.length === 0 ? <p className="p-6 text-center text-sm desk-muted">{rows.length === 0 ? 'No audited actions yet.' : 'No rows match these filters.'}</p> : (
        <div className="overflow-x-auto" tabIndex={0} role="group" aria-label="Audit rows, scrollable">
          <table className="desk-table" aria-label="Audit rows">
            <thead><tr><th scope="col">Time (IST)</th><th scope="col">Source</th><th scope="col">Actor</th><th scope="col">Action</th><th scope="col">Target</th><th scope="col">Outcome</th><th scope="col">Detail</th></tr></thead>
            <tbody>
              {shown.slice(0, 500).map((r: AuditRow) => (
                <React.Fragment key={r.id}>
                  <tr>
                    <td>{r.ts ? formatIst(r.ts, 'datetime') : ''}</td><td>{r.source}</td><td>{r.actor}</td><td>{r.action}</td><td>{r.target}</td>
                    <td><span className={`desk-pill ${tone(r.outcome)}`}>{r.outcome}</span></td>
                    <td>
                      {r.before !== undefined
                        ? <button type="button" className="desk-btn" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{r.detail}</button>
                        : <span title={r.detail}>{r.detail}</span>}
                    </td>
                  </tr>
                  {open === r.id && r.before !== undefined && (
                    <tr><td colSpan={7}><dl className="text-xs grid grid-cols-[auto_1fr] gap-x-2"><dt className="desk-muted">Before</dt><dd className="desk-num">{r.before || '(empty)'}</dd><dt className="desk-muted">After</dt><dd className="desk-num">{r.after || '(empty)'}</dd></dl></td></tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelFrame>
  );
};

export default AuditPanel;
