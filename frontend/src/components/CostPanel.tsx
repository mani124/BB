import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';

export interface CostTotals {
  trades: number;
  gross_pnl: number;
  slippage: number;
  charges: number;
  net_pnl: number;
  gross_before_slippage: number;
  avg_slippage_per_trade: number;
}
export interface CostGroup extends CostTotals { key: string }
export interface CostDay extends CostTotals { date: string }
export interface CostTrade {
  id: string; symbol: string; setup_type: string; date: string; exit_time?: string | null;
  option_entry: number; gross_pnl: number; slippage: number; charges: number; net_pnl: number;
}
export interface CostReport {
  totals: CostTotals;
  trades: CostTrade[];
  by_day: CostDay[];
  by_setup: CostGroup[];
  by_symbol: CostGroup[];
  by_premium: CostGroup[];
}

const money = (v: number, plus = false) => {
  const s = Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v < 0 ? `-₹${s}` : `${plus && v > 0 ? '+' : ''}₹${s}`;
};
const tone = (v: number) => (v > 0 ? 'desk-pos' : v < 0 ? 'desk-neg' : '');

type View = 'day' | 'trade' | 'setup' | 'symbol' | 'premium';
const VIEWS: { id: View; label: string }[] = [
  { id: 'day', label: 'Per day' },
  { id: 'trade', label: 'Per trade' },
  { id: 'setup', label: 'By setup' },
  { id: 'symbol', label: 'By symbol' },
  { id: 'premium', label: 'By premium' },
];

const Row: React.FC<{ label: React.ReactNode; r: Omit<CostTotals, 'trades' | 'gross_before_slippage' | 'avg_slippage_per_trade'> & Partial<CostTotals> }> = ({ label, r }) => (
  <tr>
    <td>{label}</td>
    {r.trades !== undefined && <td className="r desk-num">{r.trades}</td>}
    <td className={`r desk-num ${tone(r.gross_pnl)}`}>{money(r.gross_pnl, true)}</td>
    <td className="r desk-num">{money(r.slippage)}</td>
    <td className="r desk-num">{money(r.charges)}</td>
    <td className={`r desk-num ${tone(r.net_pnl)}`}>{money(r.net_pnl, true)}</td>
  </tr>
);

export const CostPanel: React.FC<{ refreshKey?: number; initialReport?: CostReport }> = ({ refreshKey = 0, initialReport }) => {
  const [report, setReport] = useState<CostReport | null>(initialReport ?? null);
  const [view, setView] = useState<View>('day');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (initialReport) return;
    let cancelled = false;
    apiFetch('/api/paper/costs')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: CostReport) => { if (!cancelled) { setReport(data); setFailed(false); } })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [refreshKey, initialReport]);

  const t = report?.totals;
  const costShare = t && t.gross_before_slippage > 0
    ? Math.round(((t.slippage + t.charges) / t.gross_before_slippage) * 100)
    : null;

  let body: React.ReactNode = null;
  let firstCol = 'Day';
  let withTrades = true;
  if (report) {
    if (view === 'day') {
      body = report.by_day.map((d) => <Row key={d.date} label={d.date} r={d} />);
    } else if (view === 'trade') {
      firstCol = 'Trade'; withTrades = false;
      body = report.trades.slice(0, 100).map((x) => (
        <Row key={x.id} label={<>{x.date} <span className="desk-code">{x.symbol}</span></>} r={x} />
      ));
    } else {
      const rows = view === 'setup' ? report.by_setup : view === 'symbol' ? report.by_symbol : report.by_premium;
      firstCol = view === 'setup' ? 'Setup' : view === 'symbol' ? 'Symbol' : 'Entry premium (₹)';
      body = rows.map((g) => <Row key={g.key} label={g.key} r={g} />);
    }
  }

  return (
    <section className="desk-panel" aria-labelledby="cost-title">
      <div className="desk-ph">
        <h2 id="cost-title">Costs: slippage and charges</h2>
        <div className="desk-seg" role="group" aria-label="Cost view">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>
          ))}
        </div>
      </div>
      {failed && !report && <div className="p-6 text-center text-xs desk-muted">Could not load costs.</div>}
      {!report && !failed && <div className="p-6 text-center text-xs desk-muted">Loading costs...</div>}
      {report && t && t.trades === 0 && <div className="p-6 text-center text-xs desk-muted">Costs appear after the first closed trade.</div>}
      {report && t && t.trades > 0 && (
        <>
          <div className="px-3.5 py-2.5 text-xs flex flex-wrap gap-x-6 gap-y-1" data-testid="cost-summary">
            <span>Gross <b className={`desk-num ${tone(t.gross_pnl)}`}>{money(t.gross_pnl, true)}</b></span>
            <span>Slippage <b className="desk-num">{money(t.slippage)}</b> <span className="desk-muted">(already inside gross)</span></span>
            <span>Charges <b className="desk-num">{money(t.charges)}</b></span>
            <span>Net <b className={`desk-num ${tone(t.net_pnl)}`}>{money(t.net_pnl, true)}</b></span>
            {costShare !== null && <span className="desk-muted">Costs ate {costShare}% of the {money(t.gross_before_slippage)} the trades would have made at the intended prices.</span>}
          </div>
          <div className="overflow-x-auto">
            <table className="desk-table">
              <thead>
                <tr>
                  <th>{firstCol}</th>
                  {withTrades && <th className="r">Trades</th>}
                  <th className="r">Gross</th><th className="r">Slippage</th><th className="r">Charges</th><th className="r">Net</th>
                </tr>
              </thead>
              <tbody>{body}</tbody>
            </table>
          </div>
          <p className="px-3.5 py-2 text-xs desk-muted">
            Net = gross - charges. Slippage is how much worse the fills were than the intended prices; it is already reflected in gross, so it is not subtracted again.
          </p>
        </>
      )}
    </section>
  );
};
