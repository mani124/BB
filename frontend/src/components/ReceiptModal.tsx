import React from 'react';
import { Dialog } from './Dialog';
import { X } from 'lucide-react';
import type { PaperPosition } from '../types';

export const ReceiptModal: React.FC<{ trade: PaperPosition; onClose: () => void }> = ({ trade: selectedTradeForReceipt, onClose }) => {
  return (
        <Dialog label="Charges receipt" onClose={onClose} className="p-5">
          <div>
            <div className="flex items-center justify-between pb-3" style={{ borderBottom: '1px solid var(--line)' }}>
              <div>
                <h4 className="text-sm font-semibold">Dhan & Statutory Taxes Receipt</h4>
                <p className="text-xs desk-muted font-mono">
                  {selectedTradeForReceipt.strike_symbol} • {selectedTradeForReceipt.setup_type}
                </p>
              </div>
              <button type="button" onClick={() => onClose()} aria-label="Close" className="desk-btn">
                <X className="h-4 w-4" />
              </button>
            </div>

            {(() => {
              const cb = selectedTradeForReceipt.charges_breakdown ?? {
                buy_turnover: selectedTradeForReceipt.option_entry * selectedTradeForReceipt.quantity,
                sell_turnover: selectedTradeForReceipt.current_option_price * selectedTradeForReceipt.quantity,
                total_turnover: (selectedTradeForReceipt.option_entry + selectedTradeForReceipt.current_option_price) * selectedTradeForReceipt.quantity,
                orders_count: 2,
                brokerage: 40.0,
                stt: 0,
                exchange_fee: 0,
                sebi_fee: 0,
                stamp_duty: 0,
                gst: 0,
                total_charges: selectedTradeForReceipt.total_charges ?? 0,
              };

              return (
                <>
                  {/* Turnover Summary */}
                  <div className="grid grid-cols-2 gap-2 my-3 p-3 rounded-md text-xs font-mono" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
                    <div>
                      <span className="text-xs desk-muted uppercase block font-sans">Buy Turnover</span>
                      <span className="font-bold">₹{cb.buy_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-xs desk-muted uppercase block font-sans">Sell Turnover</span>
                      <span className="font-bold">₹{cb.sell_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-xs desk-muted uppercase block font-sans">Total Turnover</span>
                      <span className="font-bold">₹{cb.total_turnover.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-xs desk-muted uppercase block font-sans">Orders Executed</span>
                      <span className="font-bold">{cb.orders_count} orders</span>
                    </div>
                  </div>

                  {/* Itemized Fees & Taxes */}
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">Brokerage (Dhan ₹20/order)</span>
                      <span className="font-mono font-bold">₹{cb.brokerage.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">STT (0.1% on Sell)</span>
                      <span className="font-mono font-bold">₹{cb.stt.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">NSE Exchange Fee (0.05%)</span>
                      <span className="font-mono font-bold">₹{cb.exchange_fee.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">GST (18%)</span>
                      <span className="font-mono font-bold">₹{cb.gst.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">Stamp Duty (0.003% on Buy)</span>
                      <span className="font-mono font-bold">₹{cb.stamp_duty.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1.5">
                      <span className="desk-muted">SEBI Turnover Fee</span>
                      <span className="font-mono font-bold">₹{cb.sebi_fee.toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Total Deductions */}
                  <div className="mt-4 pt-3 flex justify-between items-center" style={{ borderTop: '1px solid var(--line)' }}>
                    <div>
                      <span className="font-bold text-xs uppercase tracking-wider block">
                        Total Deductions
                      </span>
                      <span className="text-xs desk-muted font-sans">Dhan F&O Rate Card</span>
                    </div>
                    <span className="text-sm font-semibold font-mono desk-down">
                      -₹{cb.total_charges.toFixed(2)}
                    </span>
                  </div>
                </>
              );
            })()}
          </div>
        </Dialog>
  );
};
