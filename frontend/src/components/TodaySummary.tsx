import React from 'react';
import type { PaperPosition } from '../types';
import { setupCode } from './setupCode';
import { formatCurrency, pnlClass } from './format';
import { summarizeTrades } from './tradeUtils';

const dayOf = (t: PaperPosition) => (t.exit_datetime ?? t.entry_datetime ?? '').slice(0, 10);

/** Watch-screen filler: how the latest session is going, per setup, so the left pane is never blank. */
const TodaySummaryImpl: React.FC<{ trades: PaperPosition[] }> = ({ trades }) => {
  const latest = trades.reduce((d, t) => (dayOf(t) > d ? dayOf(t) : d), '');
  const todayIso = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  const day = trades.filter((t) => latest !== '' && dayOf(t) === latest);
  const total = summarizeTrades(day);
  const title = latest === '' || latest === todayIso
    ? 'Today so far'
    : `Last session · ${new Date(`${latest}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}`;

  const bySetup = new Map<string, PaperPosition[]>();
  day.forEach((t) => bySetup.set(setupCode(t.setup_type), [...(bySetup.get(setupCode(t.setup_type)) ?? []), t]));
  const rows = [...bySetup.entries()]
    .map(([code, list]) => ({ code, ...summarizeTrades(list) }))
    .sort((a, b) => a.net - b.net);

  return (
    <section className="desk-panel desk-pane flex-1 min-h-[9rem]" aria-labelledby="today-summary-title">
      <div className="desk-ph">
        <h2 id="today-summary-title">{title}</h2>
        {total.count > 0 && (
          <span className="ml-auto text-xs desk-num desk-muted">
            {total.count} {total.count === 1 ? 'trade' : 'trades'} · {Math.round(Number(total.winRate))}% win ·{' '}
            <b className={pnlClass(total.net)}>{formatCurrency(total.net, true)}</b>
          </span>
        )}
      </div>
      <div className="desk-scroll" tabIndex={0} aria-label="Per-setup results">
        {rows.length === 0 ? (
          <div className="p-6 text-center text-xs desk-muted">No closed trades yet this session.</div>
        ) : (
          <table className="desk-table">
            <thead>
              <tr><th scope="col">Setup</th><th scope="col" className="r">Trades</th><th scope="col" className="r">Win</th><th scope="col" className="r">Net</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.code}>
                  <td><span className="desk-code">{r.code}</span></td>
                  <td className="r desk-num">{r.count}</td>
                  <td className="r desk-num">{Math.round(Number(r.winRate))}%</td>
                  <td className={`r desk-num font-semibold ${pnlClass(r.net)}`}>{formatCurrency(r.net, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
};

export const TodaySummary = React.memo(TodaySummaryImpl);
