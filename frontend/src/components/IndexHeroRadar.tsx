import React from 'react';
import { IndexRadarItem } from '../types';

interface IndexHeroRadarProps {
  radar: Record<string, IndexRadarItem>;
  /** One scrolling line for the global market strip. */
  compact?: boolean;
}

// Short labels so all six indices fit one row on a laptop; the full name is in the tooltip.
const SHORT_NAMES: Record<string, string> = {
  'NIFTY 50': 'NIFTY', 'NIFTY BANK': 'BANKNIFTY', FINNIFTY: 'FINNIFTY', SENSEX: 'SENSEX', MIDCPNIFTY: 'MIDCP', NIFTYNXT50: 'NXT50',
};

export const IndexHeroRadar: React.FC<IndexHeroRadarProps> = ({ radar, compact = false }) => {
  const indexKeys = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY', 'NIFTYNXT50'];

  return (
    <section
      className={compact ? 'desk-marketstrip' : 'desk-ticker grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'}
      aria-label="Benchmark indices Bollinger radar (5m)"
    >
      {indexKeys.map((key) => {
        const item = radar[key];
        // No data for this index yet: show dashes, never invented %B / RSI / VWAP values.
        if (!item) {
          return (
            <div key={key} title={`${key} · no data yet`}>
              <b className="font-semibold">{SHORT_NAMES[key] ?? key}</b>
              <div className="desk-num desk-muted">---</div>
            </div>
          );
        }
        const isPositive = item.change_pct >= 0;
        const isAboveVwap = item.vwap_bias === 'ABOVE_VWAP';
        return (
          <div
            key={key}
            title={`${item.symbol} · %B ${item.percent_b.toFixed(2)} · BW ${item.bandwidth.toFixed(2)}% · RSI ${item.rsi.toFixed(0)} · ${
              isAboveVwap ? 'above' : 'below'
            } VWAP${item.is_squeeze ? ' · squeeze' : ''}`}
          >
            <div className="flex items-center gap-x-2">
              <b className="font-semibold">{SHORT_NAMES[key] ?? item.symbol}</b>
              <span className={`desk-num text-xs ${isAboveVwap ? 'desk-up' : 'desk-down'}`} aria-label={isAboveVwap ? 'above VWAP' : 'below VWAP'}>
                VW{isAboveVwap ? '▲' : '▼'}
              </span>
              {item.is_squeeze && <span className="desk-pill" title="Bollinger squeeze">SQ</span>}
            </div>
            <div className="flex items-baseline gap-x-2">
              <span className="desk-num text-base font-semibold">{item.close > 0 ? Math.round(item.close).toLocaleString('en-IN') : '---'}</span>
              <span className={`desk-num ${isPositive ? 'desk-up' : 'desk-down'}`}>
                {isPositive ? '+' : ''}{item.change_pct.toFixed(2)}%
              </span>
            </div>
          </div>
        );
      })}
    </section>
  );
};
