import { useEffect, useState } from 'react';
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
const tone = (n: number) => (n > 0 ? 'text-emerald-500' : n < 0 ? 'text-rose-500' : '');

export function SetupStatsTable({ rows }: { rows: SetupDayStats[] }) {
  if (rows.length === 0) {
    return <div className="px-3.5 py-3 text-xs desk-muted">No closed trades yet.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="desk-muted text-left">
            <th className="px-3.5 py-1.5">Setup / day</th>
            <th className="px-2 text-right">Trades</th>
            <th className="px-2 text-right">Win %</th>
            <th className="px-2 text-right">Avg R</th>
            <th className="px-2 text-right">Gross</th>
            <th className="px-2 text-right">Slippage</th>
            <th className="px-2 text-right">Charges</th>
            <th className="px-3.5 text-right">Net</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.setup_type}|${r.date}`} className={r.date === 'ALL' ? 'font-semibold border-t' : ''}>
              <td className={`px-3.5 py-1 ${r.date === 'ALL' ? '' : 'pl-7 desk-muted'}`}>
                {r.date === 'ALL' ? `${setupCode(r.setup_type)} · ${r.setup_type}` : r.date}
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
export function SetupStatsPanel({ refreshKey }: { refreshKey?: number }) {
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
        <span className="text-xs desk-muted">By exit day · R = net P&amp;L ÷ risk to stop</span>
      </div>
      <SetupStatsTable rows={rows} />
    </section>
  );
}
