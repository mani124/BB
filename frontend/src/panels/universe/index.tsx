import React, { useMemo, useState } from 'react';
import { useApiData } from '../../data/hooks/useApiData';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

interface Inst { symbol: string; name: string; security_id: string; exchange_segment: string; instrument_type: string; default_timeframe: string; sector: string }
interface Universe { indices: Inst[]; stocks: Inst[]; fno_stocks: Inst[]; total_count: number; fno_count: number }

const UniversePanel: React.FC<PanelProps> = () => {
  const api = useApiData<Universe>('/api/universe', { refreshMs: 600_000 });
  const [q, setQ] = useState('');
  const rows = useMemo(() => {
    const u = api.data;
    if (!u) return [];
    const tagged = [...u.indices.map((i) => ({ ...i, list: 'Index' })), ...u.stocks.map((i) => ({ ...i, list: 'Momentum stock' })), ...u.fno_stocks.map((i) => ({ ...i, list: 'F&O stock' }))];
    const needle = q.trim().toLowerCase();
    return needle ? tagged.filter((r) => `${r.symbol} ${r.name} ${r.sector}`.toLowerCase().includes(needle)) : tagged;
  }, [api.data, q]);
  return (
    <PanelFrame title="Universe" sources={[]} onRetry={api.reload}>
      {api.error && <div className="desk-alert text-xs" role="alert">Could not load the universe: {api.error}. <button type="button" className="desk-btn" onClick={api.reload}>Retry</button></div>}
      {!api.data && !api.error && <p className="p-4 text-sm desk-muted" role="status">Loading universe…</p>}
      {api.data && (
        <>
          <div className="flex items-center gap-2 px-2 py-1 text-xs">
            <span>{api.data.total_count} instruments, {api.data.fno_count} F&O stocks.</span>
            <input className="desk-input ml-auto" style={{ width: '10rem' }} placeholder="Search symbol or sector" aria-label="Search universe" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {rows.length === 0 ? <p className="p-4 text-sm desk-muted">Nothing matches.</p> : (
            <table className="desk-table" aria-label="Universe">
              <thead><tr><th scope="col">Symbol</th><th scope="col">List</th><th scope="col">Sector</th><th scope="col">Segment</th><th scope="col">Timeframe</th></tr></thead>
              <tbody>{rows.slice(0, 400).map((r) => <tr key={`${r.list}:${r.symbol}`}><td className="desk-sym">{r.symbol}</td><td>{r.list}</td><td>{r.sector}</td><td>{r.exchange_segment}</td><td>{r.default_timeframe}</td></tr>)}</tbody>
            </table>
          )}
        </>
      )}
    </PanelFrame>
  );
};

export default UniversePanel;
