import React from 'react';
import { X } from 'lucide-react';
import type { Signal } from '../types';
import { Dialog } from './Dialog';
import { setupCode } from './setupCode';

const price = (value: number | undefined) => value == null ? '—' : value.toLocaleString('en-IN', { maximumFractionDigits: 2 });

/** A read-first view of the evidence and price levels behind a scanner signal. */
export const SignalDetails: React.FC<{
  signal: Signal;
  onClose: () => void;
  onPaperBuy: (signal: Signal) => void;
  isBought: boolean;
}> = ({ signal, onClose, onPaperBuy, isBought }) => {
  const rec = signal.strike_recommendation;
  const ind = signal.indicators_snapshot;
  const unconfirmed = signal.is_confirmed === false;
  const quoteLabel = rec.is_live_quote ? 'Live quote available' : 'Entry price estimated';

  return (
    <Dialog label="Signal details" onClose={onClose} className="p-5" style={{ maxWidth: '40rem' }}>
      <div className="flex items-start justify-between gap-3 pb-3" style={{ borderBottom: '1px solid var(--line)' }}>
        <div>
          <h2 className="text-lg font-semibold">{rec.strike_symbol}</h2>
          <p className="text-xs desk-muted">{signal.symbol} · {setupCode(signal.setup_type)} · {signal.timeframe} · {signal.option_type}</p>
        </div>
        <button type="button" className="desk-btn" aria-label="Close signal details" onClick={onClose}><X className="h-4 w-4" /></button>
      </div>

      <div className="flex flex-wrap gap-2 mt-4">
        <span className={`desk-pill ${unconfirmed ? 'warn' : 'up'}`}>{unconfirmed ? 'Awaiting candle close' : 'Confirmed on candle close'}</span>
        <span className={`desk-pill ${rec.is_live_quote ? 'up' : 'warn'}`}>{quoteLabel}</span>
        {rec.expiry_date && <span className="desk-pill mute">Expiry {rec.expiry_date}</span>}
      </div>

      <section className="mt-5" aria-label="Signal reasoning">
        <h3 className="text-sm font-semibold mb-1">Why it appeared</h3>
        <p className="text-sm desk-muted">{signal.rationale || 'No reasoning was supplied for this signal.'}</p>
      </section>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-5">
        <section className="desk-panel p-3" aria-label="Option levels">
          <h3 className="text-sm font-semibold mb-2">Option levels</h3>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="desk-muted">Option entry</dt><dd className="desk-num text-right">{price(rec.estimated_option_entry)}</dd>
            {rec.real_ask_price != null && <><dt className="desk-muted">Current ask</dt><dd className="desk-num text-right">{price(rec.real_ask_price)}</dd></>}
            {rec.real_bid_price != null && <><dt className="desk-muted">Current bid</dt><dd className="desk-num text-right">{price(rec.real_bid_price)}</dd></>}
            <dt className="desk-muted">Stop</dt><dd className="desk-num text-right desk-down">{price(rec.option_sl_price)}</dd>
            <dt className="desk-muted">Target 1</dt><dd className="desk-num text-right desk-up">{price(rec.option_target_1_price)}</dd>
            <dt className="desk-muted">Target 2</dt><dd className="desk-num text-right desk-up">{price(rec.option_target_2_price)}</dd>
            <dt className="desk-muted">Lot size</dt><dd className="desk-num text-right">{rec.lot_size}</dd>
          </dl>
        </section>
        <section className="desk-panel p-3" aria-label="Underlying levels and indicators">
          <h3 className="text-sm font-semibold mb-2">Underlying</h3>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="desk-muted">Entry</dt><dd className="desk-num text-right">{price(signal.entry_price)}</dd>
            <dt className="desk-muted">Stop</dt><dd className="desk-num text-right">{price(signal.stop_loss)}</dd>
            <dt className="desk-muted">Target 1</dt><dd className="desk-num text-right">{price(signal.target_1)}</dd>
            <dt className="desk-muted">RSI</dt><dd className="desk-num text-right">{price(ind?.rsi)}</dd>
            <dt className="desk-muted">Band width</dt><dd className="desk-num text-right">{ind?.bandwidth == null ? '—' : `${price(ind.bandwidth)}%`}</dd>
          </dl>
        </section>
      </div>

      <div className="flex items-center justify-between gap-3 mt-5 pt-4" style={{ borderTop: '1px solid var(--line)' }}>
        <span className="text-xs desk-muted">Review the current quote and risk before entering.</span>
        {isBought ? <span className="desk-pill up">In portfolio</span> : (
          <button type="button" className="desk-btn accent" disabled={unconfirmed} onClick={() => onPaperBuy(signal)}>Paper buy</button>
        )}
      </div>
    </Dialog>
  );
};
