import React from 'react';
import { IndexRadarItem } from '../types';

interface IndexHeroRadarProps {
  radar: Record<string, IndexRadarItem>;
}

// Short labels so all six indices fit one row on a laptop; the full name is in the tooltip.
const SHORT_NAMES: Record<string, string> = {
  'NIFTY 50': 'NIFTY', 'NIFTY BANK': 'BANKNIFTY', FINNIFTY: 'FINNIFTY', SENSEX: 'SENSEX', MIDCPNIFTY: 'MIDCP', NIFTYNXT50: 'NXT50',
};

export const IndexHeroRadar: React.FC<IndexHeroRadarProps> = ({ radar }) => {
  const indexKeys = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY', 'NIFTYNXT50'];

  return (
    <section
      className="desk-ticker grid-cols-2 lg:grid-cols-6"
      aria-label="Benchmark indices Bollinger radar (5m)"
    >
      {indexKeys.map((key) => {
        const item = radar[key];
        // No data for this index yet: show dashes, never invented %B / RSI / VWAP values.
        if (!item) {
          return (
            <div key={key} className="flex items-center gap-x-1.5 overflow-hidden whitespace-nowrap" title={`${key} · no data yet`}>
              <b className="font-semibold shrink-0">{SHORT_NAMES[key] ?? key}</b>
              <span className="desk-num desk-muted">---</span>
            </div>
          );
        }
        const isPositive = item.change_pct >= 0;
        const isAboveVwap = item.vwap_bias === 'ABOVE_VWAP';
        return (
          <div
            key={key}
            className="flex items-center gap-x-1.5 overflow-hidden whitespace-nowrap"
            title={`${item.symbol} · %B ${item.percent_b.toFixed(2)} · BW ${item.bandwidth.toFixed(2)}% · RSI ${item.rsi.toFixed(0)} · ${
              isAboveVwap ? 'above' : 'below'
            } VWAP${item.is_squeeze ? ' · squeeze' : ''}`}
          >
            <b className="font-semibold shrink-0">{SHORT_NAMES[key] ?? item.symbol}</b>
            <span className="desk-num">{item.close > 0 ? Math.round(item.close).toLocaleString('en-IN') : '---'}</span>
            <span className={`desk-num ${isPositive ? 'desk-up' : 'desk-down'}`}>
              {isPositive ? '+' : ''}{item.change_pct.toFixed(2)}%
            </span>
            <span className={`desk-num text-xs ${isAboveVwap ? 'desk-up' : 'desk-down'}`} aria-label={isAboveVwap ? 'above VWAP' : 'below VWAP'}>
              <span className="hidden xl:inline">VW</span>{isAboveVwap ? '▲' : '▼'}
            </span>
            {item.is_squeeze && <span className="desk-pill shrink-0">SQ</span>}
          </div>
        );
      })}
    </section>
  );
};
