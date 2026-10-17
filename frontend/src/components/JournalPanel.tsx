import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';

interface JournalTrade {
  id: string;
  date: string | null;
  strike_symbol: string;
  setup_type: string;
  exit_time: string | null;
  net_pnl: number;
  note: string;
  tag: string;
}

const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });

async function download(url: string, filename: string): Promise<string | null> {
  const res = await apiFetch(url);
  if (!res.ok) return `Download failed (${res.status})`;
  const href = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
  return null;
}

export function JournalPanel() {
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [trades, setTrades] = useState<JournalTrade[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { note: string; tag: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await apiFetch(`/api/journal/trades?start=${start}&end=${end}`);
    if (!res.ok) {
      setError(`Could not load journal (${res.status})`);
      return;
    }
    setError(null);
    setTrades(await res.json());
    setDrafts({});
  }, [start, end]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (t: JournalTrade) => {
    const d = drafts[t.id];
    if (!d) return;
    const res = await apiFetch(`/api/journal/trades/${t.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(d),
    });
    if (!res.ok) {
      setError(`Could not save note (${res.status})`);
      return;
    }
    await load();
  };

  const edit = (t: JournalTrade, patch: Partial<{ note: string; tag: string }>) =>
    setDrafts((prev) => ({ ...prev, [t.id]: { ...(prev[t.id] ?? { note: t.note, tag: t.tag }), ...patch } }));

  return (
    <section className="desk-panel p-3.5 space-y-3" aria-label="Daily journal">
      <div className="flex flex-wrap items-end gap-3">
        <h3 className="text-sm font-semibold mr-2">Daily journal</h3>
        <label className="text-xs desk-muted">From
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="desk-input ml-1" />
        </label>
        <label className="text-xs desk-muted">To
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="desk-input ml-1" />
        </label>
        <button type="button" className="desk-btn" onClick={async () =>
          setError(await download(`/api/journal/export.csv?start=${start}&end=${end}`, `journal_${start}_${end}.csv`))}>
          Export CSV
        </button>
        <button type="button" className="desk-btn" onClick={async () =>
          setError(await download(`/api/journal/summary.html?day=${end}`, `summary_${end}.html`))}>
          Day summary ({end})
        </button>
      </div>
      {error && <div className="desk-alert text-xs">{error}</div>}
      {trades.length === 0 ? (
        <p className="text-xs desk-muted">No closed trades in this range.</p>
      ) : (
        <table className="desk-table">
          <thead>
            <tr><th scope="col">Date</th><th scope="col">Contract</th><th scope="col">Net</th><th scope="col">Tag</th><th scope="col">Note</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const d = drafts[t.id] ?? { note: t.note, tag: t.tag };
              return (
                <tr key={t.id}>
                  <td className="desk-num">{t.date} {t.exit_time}</td>
                  <td>{t.strike_symbol}</td>
                  <td className={`desk-num ${t.net_pnl >= 0 ? 'desk-up' : 'desk-down'}`}>{t.net_pnl.toFixed(2)}</td>
                  <td><input aria-label={`Tag for ${t.strike_symbol}`} maxLength={40} className="desk-input" value={d.tag}
                    onChange={(e) => edit(t, { tag: e.target.value })} /></td>
                  <td><input aria-label={`Note for ${t.strike_symbol}`} maxLength={1000} className="desk-input w-full" value={d.note}
                    onChange={(e) => edit(t, { note: e.target.value })} /></td>
                  <td><button type="button" className="desk-btn" disabled={!drafts[t.id]} onClick={() => save(t)}>Save</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
