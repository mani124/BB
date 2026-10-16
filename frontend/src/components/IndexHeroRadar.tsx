import React from 'react';
import { IndexRadarItem } from '../types';

interface IndexHeroRadarProps {
  radar: Record<string, IndexRadarItem>;
}

export const IndexHeroRadar: React.FC<IndexHeroRadarProps> = ({ radar }) => {
  const indexKeys = ['NIFTY 50', 'NIFTY BANK', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY', 'NIFTYNXT50'];

  return (
    <section
      className="desk-strip grid-cols-2 lg:grid-cols-6"
      aria-label="Benchmark indices Bollinger radar (5m)"
    >
      {indexKeys.map((key) => {
        const item = radar[key] || {
          symbol: key,
          close: 0,
          change_pct: 0,
          percent_b: 0.5,
          bandwidth: 0,
          is_squeeze: false,
          vwap_bias: 'ABOVE_VWAP',
          rsi: 50,
          trend_state: 'RANGE',
        };
        const isPositive = item.change_pct >= 0;
        const isAboveVwap = item.vwap_bias === 'ABOVE_VWAP';

        return (
          <div key={key} className="grid grid-cols-[1fr_auto] gap-x-2 gap-y-1">
            <b className="font-semibold">{item.symbol}</b>
            <span className="desk-num whitespace-nowrap">
              {item.close > 0 ? item.close.toLocaleString('en-IN') : '---'}{' '}
              <span className={isPositive ? 'desk-up' : 'desk-down'}>
                {isPositive ? '+' : ''}{item.change_pct.toFixed(2)}%
              </span>
            </span>
            <div className="desk-bar col-span-2 mt-0.5" title="Bollinger %B position">
              <i style={{ width: `${Math.max(0, Math.min(100, item.percent_b * 100))}%` }} />
            </div>
            <div className="col-span-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs desk-muted">
              <span className="desk-num">%B {item.percent_b.toFixed(2)}</span>
              <span className="desk-num">BW {item.bandwidth.toFixed(2)}%</span>
              <span className="desk-num">RSI {item.rsi.toFixed(0)}</span>
              {item.is_squeeze && <span className="desk-pill">Squeeze</span>}
              <span className={`desk-pill ${isAboveVwap ? 'up' : 'down'}`}>
                {isAboveVwap ? 'Above VWAP' : 'Below VWAP'}
              </span>
            </div>
          </div>
        );
      })}
    </section>
  );
};
