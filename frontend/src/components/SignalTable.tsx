import React from 'react';
import { Signal } from '../types';
import { setupCode } from './setupCode';

interface SignalTableProps {
  signals: Signal[];
  onPaperBuy?: (signal: Signal) => void;
  activeSignalIds?: Set<string>;
  /** First snapshot has not arrived yet: show placeholder rows instead of the empty state. */
  loading?: boolean;
}

// "2026-10-14T10:40:00+05:30" or "10:40:00" -> "10:40"
const signalTime = (ts?: string): string => {
  if (!ts) return '--:--';
  const m = ts.match(/(\d{2}:\d{2})/);
  return m ? m[1] : ts;
};

export const SignalTable: React.FC<SignalTableProps> = ({ signals, onPaperBuy, activeSignalIds, loading = false }) => {
  if (loading) {
    return (
      <div className="p-3 flex flex-col gap-2" role="status" aria-label="Loading signals">
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="desk-skel h-9" />)}
      </div>
    );
  }
  if (signals.length === 0) {
    return (
      <div className="p-10 text-center">
        <p className="text-sm font-semibold mb-1">No Active Signals Matching Current Filter</p>
        <p className="text-xs desk-muted">
          The background scanner cycles every ~8 seconds. Signals will appear here as soon as a candle trigger fires.
        </p>
      </div>
    );
  }

  return (
    <div>
      <table className="desk-table">
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Instrument</th>
            <th scope="col">Setup</th>
            <th scope="col" className="r">Entry</th>
            <th scope="col" className="r">SL</th>
            <th scope="col" className="r">T1</th>
            <th scope="col" className="r">RSI / BW</th>
            <th scope="col"><span className="sr-only">Action</span></th>
          </tr>
        </thead>
        <tbody>
          {signals.map((sig) => {
            const rec = sig.strike_recommendation;
            const ind = sig.indicators_snapshot;
            const isBought = activeSignalIds?.has(sig.id) || false;
            const isOptionChart = sig.setup_type.includes('Setup 5') || sig.setup_type.includes('SETUP_5') || sig.setup_type.includes('Setup 10') || sig.setup_type.includes('SETUP_10') || sig.setup_type.includes('Setup 11') || sig.setup_type.includes('SETUP_11') || sig.setup_type.includes('Setup 13') || sig.setup_type.includes('SETUP_13') || sig.setup_type.includes('Setup 16') || sig.setup_type.includes('SETUP_16');
            const unconfirmed = sig.is_confirmed === false;

            return (
              <tr key={sig.id}>
                <td className="desk-num">{signalTime(sig.timestamp)}</td>
                <td>
                  <span className="desk-sym">{rec.strike_symbol}</span>{' '}
                  <span className={`desk-side ${sig.option_type === 'CE' ? 'ce' : 'pe'}`}>{sig.option_type}</span>
                  <span className="desk-sub">
                    {sig.symbol} · {sig.timeframe}
                    {isOptionChart ? '' : ` · spot ${sig.entry_price}`}
                    {unconfirmed ? ' · awaiting candle close' : ''}
                  </span>
                </td>
                <td>
                  <span className="desk-code" title={sig.setup_type}>{setupCode(sig.setup_type)}</span>
                </td>
                <td className="r desk-num">
                  {rec.estimated_option_entry}
                  <span className="desk-sub">lot {rec.lot_size}</span>
                </td>
                <td className="r desk-num desk-down">
                  {rec.option_sl_price}
                  <span className="desk-sub">-{rec.option_sl_pts}p</span>
                </td>
                <td className="r desk-num desk-up">
                  {rec.option_target_1_price}
                  <span className="desk-sub">+{rec.option_target_1_pts}p</span>
                </td>
                <td className="r desk-num">
                  {ind?.rsi != null ? ind.rsi.toFixed(1) : '-'}
                  {ind?.rsi != null && (
                    <span className="desk-mini" role="img" aria-label={`RSI ${ind.rsi.toFixed(0)} of 100`}>
                      <i style={{ width: `${Math.max(0, Math.min(100, ind.rsi))}%` }} />
                    </span>
                  )}
                  <span className="desk-sub">{ind?.bandwidth != null ? `BW ${ind.bandwidth.toFixed(2)}%` : '-'}</span>
                </td>
                <td className="r">
                  {onPaperBuy &&
                    (isBought ? (
                      <span className="desk-pill up">In portfolio</span>
                    ) : (
                      <button
                        type="button"
                        className="desk-btn ghost"
                        onClick={() => !unconfirmed && onPaperBuy(sig)}
                        disabled={unconfirmed}
                        title={unconfirmed ? 'Awaiting candle close confirmation' : undefined}
                      >
                        Paper buy
                      </button>
                    ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
