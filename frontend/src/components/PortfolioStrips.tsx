import React from 'react';
import type { PaperPortfolio } from '../types';
import { INR, formatCurrency, pnlClass } from './format';

/* ---------- P&L strip ---------- */
export const PortfolioStrip: React.FC<{ portfolio?: PaperPortfolio }> = ({ portfolio }) => {
  const grossRealized = portfolio?.total_gross_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const slippageCost = portfolio?.total_slippage_cost ?? 0;
  const avgSlippagePts = portfolio?.avg_slippage_points ?? 0;
  const totalCharges = portfolio?.total_charges ?? 0;
  const netRealized = portfolio?.total_net_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const floating = portfolio?.total_unrealized_pnl ?? 0;
  const floatingCharges = portfolio?.total_unrealized_charges ?? 0;
  const floatingNet = portfolio?.total_unrealized_net ?? floating;
  const openCount = portfolio?.active_positions?.length ?? 0;
  // Profit already booked at Target 1 on trades that are still open: not in Net Realized until they close.
  const bookedOpen = (portfolio?.active_positions ?? []).reduce((sum, p) => sum + (p.booked_pnl_rupees ?? 0), 0);

  return (
    <section
      className="desk-strip grid-cols-2 md:grid-cols-3 lg:grid-cols-[1.4fr_repeat(5,1fr)]"
      aria-label="Portfolio performance"
    >
      <div className="col-span-2 md:col-span-3 lg:col-span-1">
        <div className="desk-label" title="Closed trades only, after charges. Open trades are not included.">Net Realized P&L</div>
        <div className={`desk-num text-2xl font-semibold ${pnlClass(netRealized)}`}>
          {formatCurrency(netRealized, true)}
        </div>
      </div>
      <div>
        <div className="desk-label">Gross Realized P&L</div>
        <div className={`desk-num text-lg font-semibold ${pnlClass(grossRealized)}`}>
          {formatCurrency(grossRealized, true)}
        </div>
        <div className="text-xs desk-muted">
          {portfolio?.winning_trades_count ?? 0}W / {portfolio?.losing_trades_count ?? 0}L
        </div>
      </div>
      <div>
        <div className="desk-label">Execution Slippage Impact</div>
        <div className="desk-num text-lg font-semibold" style={{ color: 'var(--warn)' }}>
          {slippageCost > 0 ? `-₹${slippageCost.toLocaleString('en-IN', INR)}` : '₹0.00'}
        </div>
        <div className="text-xs desk-muted">
          Avg drag {avgSlippagePts > 0 ? `-${avgSlippagePts.toFixed(1)}` : '0.0'} pts
        </div>
      </div>
      <div>
        <div className="desk-label">Brokerage & Regulatory Taxes</div>
        <div className="desk-num text-lg font-semibold">
          {totalCharges > 0 ? `-₹${totalCharges.toLocaleString('en-IN', INR)}` : '₹0.00'}
        </div>
        <div className="text-xs desk-muted">STT, GST, exchange, SEBI</div>
      </div>
      <div>
        <div className="desk-label">Unrealized P&L (open)</div>
        <div className={`desk-num text-lg font-semibold ${pnlClass(floating)}`}>
          {formatCurrency(floating, true)}
        </div>
        <div className="text-xs desk-muted">
          {openCount} open
          {bookedOpen !== 0 && <> · booked at T1 <span className={`desk-num ${pnlClass(bookedOpen)}`}>{formatCurrency(bookedOpen, true)}</span> (in Net Realized once closed)</>}
          {' '}· net if closed now{' '}
          <span className={`desk-num ${pnlClass(floatingNet)}`}>{formatCurrency(floatingNet, true)}</span>
          {floatingCharges > 0 && <> (est. charges ₹{floatingCharges.toLocaleString('en-IN', INR)})</>}
        </div>
      </div>
      <div>
        <div className="desk-label">Win rate</div>
        <div className="desk-num text-lg font-semibold">{(portfolio?.win_rate_pct ?? 0).toFixed(1)}%</div>
      </div>
    </section>
  );
};

/* ---------- Compact status strip (one line, always visible) ---------- */
export const CompactStrip: React.FC<{ portfolio?: PaperPortfolio }> = ({ portfolio }) => {
  const net = portfolio?.total_net_pnl ?? portfolio?.total_realized_pnl ?? 0;
  const floatingNet = portfolio?.total_unrealized_net ?? portfolio?.total_unrealized_pnl ?? 0;
  const openCount = portfolio?.active_positions?.length ?? 0;
  const slippage = portfolio?.total_slippage_cost ?? 0;
  const charges = portfolio?.total_charges ?? 0;
  const wins = portfolio?.winning_trades_count ?? 0;
  const losses = portfolio?.losing_trades_count ?? 0;
  const Item: React.FC<{ label: string; title?: string; children: React.ReactNode }> = ({ label, title, children }) => (
    <div title={title} className="flex items-baseline gap-2">
      <span className="desk-label">{label}</span>
      {children}
    </div>
  );
  if (!portfolio) {
    return (
      <section className="desk-ticker" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }} aria-label="Portfolio summary" aria-busy="true">
        {[0, 1, 2, 3, 4].map((i) => <div key={i}><div className="desk-skel h-4 w-24" /></div>)}
      </section>
    );
  }
  return (
    <section
      className="desk-ticker"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}
      aria-label="Portfolio summary"
    >
      <Item label="Net realized">
        <b className={`desk-num text-base ${pnlClass(net)}`}>{formatCurrency(net, true)}</b>
      </Item>
      <Item label="Unrealized" title="Open positions, net of estimated exit charges">
        <b className={`desk-num ${pnlClass(floatingNet)}`}>{formatCurrency(floatingNet, true)}</b>
        <span className="desk-muted desk-num">{openCount} open</span>
      </Item>
      <Item label="Win rate">
        <b className="desk-num">{(portfolio?.win_rate_pct ?? 0).toFixed(1)}%</b>
        <span className="desk-muted desk-num">{wins}W / {losses}L</span>
      </Item>
      <Item label="Slippage" title="Execution slippage cost on closed trades">
        <b className="desk-num" style={{ color: 'var(--warn)' }}>-{formatCurrency(slippage).replace('-', '')}</b>
      </Item>
      <Item label="Charges" title="Brokerage, STT, GST, exchange and SEBI fees">
        <b className="desk-num">{formatCurrency(charges)}</b>
      </Item>
    </section>
  );
};
