import React from 'react';
import { useApp } from '../../data/appStore';
import { formatIst } from '../../lib/time';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

interface Rec { enabled?: boolean; path?: string; buffered?: number; recorded_this_run?: number; dropped?: number; kinds?: Record<string, { bars: number; keys: number; first: string; last: string }>; days?: string[] }

const RecorderPanel: React.FC<PanelProps> = () => {
  const r = useApp((s) => s.health.recorder) as Rec | null;
  const kinds = Object.entries(r?.kinds ?? {});
  return (
    <PanelFrame title="Recorder" sources={['health']}>
      {!r ? <p className="p-4 text-sm desk-muted" role="status">No recorder data yet.</p> : (
        <>
          <p className="px-2 py-1 text-sm">
            <span className={`desk-pill ${r.enabled ? 'up' : 'mute'}`}>{r.enabled ? 'Recording' : 'Off'}</span>{' '}
            {r.recorded_this_run ?? 0} bars this run, {r.buffered ?? 0} buffered, <span className={r.dropped ? 'desk-down' : ''}>{r.dropped ?? 0} dropped</span>.
          </p>
          {kinds.length === 0 ? <p className="px-2 pb-2 text-xs desk-muted">No stored bars yet.</p> : (
            <table className="desk-table" aria-label="Stored bars">
              <thead><tr><th scope="col">Kind</th><th scope="col" className="r">Bars</th><th scope="col" className="r">Instruments</th><th scope="col">First</th><th scope="col">Last</th></tr></thead>
              <tbody>{kinds.map(([k, v]) => <tr key={k}><td>{k}</td><td className="r desk-num">{v.bars}</td><td className="r desk-num">{v.keys}</td><td>{v.first ? formatIst(v.first, 'datetime') : ''}</td><td>{v.last ? formatIst(v.last, 'datetime') : ''}</td></tr>)}</tbody>
            </table>
          )}
          {r.days && r.days.length > 0 && <p className="px-2 py-1 text-xs desk-muted">Recorded days: {r.days.join(', ')}</p>}
        </>
      )}
    </PanelFrame>
  );
};

export default RecorderPanel;
