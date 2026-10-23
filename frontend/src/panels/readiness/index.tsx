import React from 'react';
import { useApp } from '../../data/appStore';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

interface Check { key: string; status: 'ok' | 'warn' | 'fail'; detail: string }
const TONE = { ok: 'up', warn: 'warn', fail: 'down' } as const;
const WORD = { ok: 'OK', warn: 'Warning', fail: 'Failed' } as const;

const ReadinessPanel: React.FC<PanelProps> = () => {
  const data = useApp((s) => s.health.readiness) as { status?: Check['status']; checks?: Check[] } | null;
  const checks = data?.checks ?? [];
  return (
    <PanelFrame title="Readiness" sources={['health']}>
      {!data ? <p className="p-4 text-sm desk-muted" role="status">No readiness data yet.</p> : (
        <>
          <p className="px-2 py-1 text-sm">Overall <span className={`desk-pill ${TONE[data.status ?? 'ok']}`}>{WORD[data.status ?? 'ok']}</span></p>
          <table className="desk-table" aria-label="Readiness checks">
            <thead><tr><th scope="col">Check</th><th scope="col">State</th><th scope="col">Detail</th></tr></thead>
            <tbody>{checks.map((c) => <tr key={c.key}><td>{c.key.replace(/_/g, ' ')}</td><td><span className={`desk-pill ${TONE[c.status]}`}>{WORD[c.status]}</span></td><td>{c.detail}</td></tr>)}</tbody>
          </table>
        </>
      )}
    </PanelFrame>
  );
};

export default ReadinessPanel;
