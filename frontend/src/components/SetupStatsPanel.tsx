import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { apiFetch } from '../api/client';
import { setupCode } from './setupCode';

export interface SetupDayStats {
  setup_type: string;
  date: string; // YYYY-MM-DD, or "ALL" for the setup total
  trades: number;
  wins: number;
  win_rate: number;
  avg_r: number | null;
  r_trades?: number;
  gross_pnl: number;
  total_slippage_cost: number;
  total_charges: number;
  net_pnl: number;
}

const inr = (n: number) => `${n < 0 ? '-' : ''}₹${Math.abs(Math.round(n)).toLocaleString('en-IN')}`;
const tone = (n: number) => (n > 0 ? 'desk-up' : n < 0 ? 'desk-down' : '');

export function SetupStatsTable({ rows, collapsible = false }: { rows: SetupDayStats[]; collapsible?: boolean }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (k: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  if (rows.length === 0) {
    return <div className="px-3.5 py-3 text-xs desk-muted">No closed trades yet.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="desk-muted text-left">
            <th scope="col" className="px-3.5 py-1.5">Setup / day</th>
            <th scope="col" className="px-2 text-right">Trades</th>
            <th scope="col" className="px-2 text-right">Win %</th>
            <th scope="col" className="px-2 text-right">Avg R</th>
            <th scope="col" className="px-2 text-right">Gross</th>
            <th scope="col" className="px-2 text-right">Slippage</th>
            <th scope="col" className="px-2 text-right">Charges</th>
            <th scope="col" className="px-3.5 text-right">Net</th>
          </tr>
        </thead>
        <tbody>
          {rows.filter((r) => !collapsible || r.date === 'ALL' || open.has(r.setup_type)).map((r) => (
            <tr
              key={`${r.setup_type}|${r.date}`}
              className={`${r.date === 'ALL' ? 'font-semibold border-t' : ''} ${collapsible && r.date === 'ALL' ? 'cursor-pointer' : ''}`}
              onClick={collapsible && r.date === 'ALL' ? () => toggle(r.setup_type) : undefined}
            >
              <td className={`px-3.5 py-1 ${r.date === 'ALL' ? '' : 'pl-7 desk-muted'}`}>
                {collapsible && r.date === 'ALL' ? (
                  <button
                    type="button"
                    className="text-left font-semibold"
                    aria-expanded={open.has(r.setup_type)}
                    onClick={(e) => { e.stopPropagation(); toggle(r.setup_type); }}
                  >
                    {open.has(r.setup_type)
                      ? <ChevronDown className="inline h-3.5 w-3.5 mr-1" aria-hidden="true" />
                      : <ChevronRight className="inline h-3.5 w-3.5 mr-1" aria-hidden="true" />}
                    {`${setupCode(r.setup_type)} · ${r.setup_type}`}
                  </button>
                ) : r.date === 'ALL' ? `${setupCode(r.setup_type)} · ${r.setup_type}` : r.date}
              </td>
              <td className="px-2 text-right">{r.trades}</td>
              <td className="px-2 text-right">{r.win_rate.toFixed(1)}%</td>
              <td className={`px-2 text-right ${tone(r.avg_r ?? 0)}`} title={`Average R over ${r.r_trades ?? '?'} of ${r.trades} trades; trades whose stop moved to entry after Target 1 have no measurable risk and are left out.`}>{r.avg_r === null ? '—' : r.avg_r.toFixed(2)}</td>
              <td className={`px-2 text-right ${tone(r.gross_pnl)}`}>{inr(r.gross_pnl)}</td>
              <td className="px-2 text-right">{inr(r.total_slippage_cost)}</td>
              <td className="px-2 text-right">{inr(r.total_charges)}</td>
              <td className={`px-3.5 text-right ${tone(r.net_pnl)}`}>{inr(r.net_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Per-setup, per-day stats from /api/paper/setup-stats (quarantined/archived trades excluded). */
export function SetupStatsPanel({ refreshKey, collapsible = false }: { refreshKey?: number; collapsible?: boolean }) {
  const [rows, setRows] = useState<SetupDayStats[]>([]);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const res = await apiFetch('/api/paper/setup-stats');
        if (res.ok && live) setRows(await res.json());
      } catch {
        /* panel is best-effort */
      }
    })();
    return () => {
      live = false;
    };
  }, [refreshKey]);
  return (
    <section className="desk-panel" aria-labelledby="setup-stats-title">
      <div className="desk-ph">
        <h2 id="setup-stats-title">Setup stats</h2>
        <span className="text-xs desk-muted">By exit day · R = net P&amp;L ÷ risk to stop{collapsible ? ' · click a setup for its days' : ''}</span>
      </div>
      <SetupStatsTable rows={rows} collapsible={collapsible} />
    </section>
  );
}
