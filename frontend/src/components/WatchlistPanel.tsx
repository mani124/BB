import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import type { WatchlistState } from '../types';

const when = (iso?: string) => {
  if (!iso) return '-';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const STATUS_TEXT: Record<string, string> = {
  built: 'Built just now',
  up_to_date: 'Up to date',
  no_credentials: 'Waiting for a Dhan login',
  before_build_time: 'Waiting for the final daily bar',
  disabled: 'Switched off in Settings',
  error: 'Last build failed',
};

/** Setup 16's after-close watchlist: when it was built, for which day, and why each stock is on it. */
export const WatchlistPanel: React.FC<{ initial?: WatchlistState }> = ({ initial }) => {
  const [data, setData] = useState<WatchlistState | null>(initial ?? null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/watchlist');
      if (res.ok) setData(await res.json());
    } catch { /* offline: keep what is shown */ }
  }, []);

  useEffect(() => { if (!initial) void load(); }, [initial, load]);

  const rebuild = async () => {
    setBusy(true);
    try {
      await apiFetch('/api/watchlist/run', { method: 'POST' });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const list = data?.candidates ?? [];
  const status = data?.last_cycle?.status;
  return (
    <section className="desk-panel shrink-0" aria-labelledby="watchlist-title" data-testid="watchlist-panel">
      <div className="desk-ph">
        <h3 id="watchlist-title">Setup 16 watchlist</h3>
        <span className={`desk-pill ${list.length ? 'up' : 'warn'}`}>
          {data?.built_for ? `${list.length} stocks for ${data.built_for}` : 'Not built yet'}
        </span>
        <div className="ml-auto flex gap-2">
          <button type="button" className="desk-btn sm" disabled={busy} onClick={() => void rebuild()}>Check now</button>
          <button type="button" className="desk-btn sm" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>
      <div className="px-3.5 py-2 text-xs desk-muted flex flex-wrap gap-x-4 gap-y-1">
        <span>Built <b className="desk-num">{when(data?.built_at)}</b></span>
        <span>From daily bars up to <b className="desk-num">{data?.last_bar_day ?? '-'}</b></span>
        <span>Screened <b className="desk-num">{data?.screened ?? '-'}</b></span>
        {status && <span>{STATUS_TEXT[status] ?? status}</span>}
        {data && data.enabled === false && <span>Switched off in Settings</span>}
      </div>
      {open && (
        list.length === 0 ? <div className="p-4 text-xs desk-muted">No stocks on the list.</div> : (
          <div className="overflow-x-auto"><table className="desk-table">
            <thead><tr><th scope="col">Stock</th><th scope="col" className="r">BandWidth %ile</th><th scope="col" className="r">Avg value (cr)</th><th scope="col">Why</th></tr></thead>
            <tbody>{list.map((c) => (
              <tr key={c.symbol}><td className="desk-sym">{c.symbol}</td><td className="r desk-num">{c.bw_percentile}</td>
                <td className="r desk-num">{c.avg_value_cr}</td><td>{c.reasons.join(', ')}</td></tr>
            ))}</tbody></table></div>
        )
      )}
    </section>
  );
};
