import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CxScreen } from './CxScreen';
import type { CxOverview, CxPosition } from '../types';

const pos: CxPosition = {
  id: 'p1', symbol: 'CRUDEOIL', pool: 'commodity', setup: 'SETUP_17_RANGE_BREAK', side: 'CE', status: 'OPEN', opened_at: '2026-10-19T19:05:00+05:30',
  strike: 6500, expiry: '2026-10-27', lots: 1, entry_price: 100, last_bid: 112, unrealized_net: 1100, invalidate_level: 6490,
};
const pool = { enabled: true, day_pnl: -300, loss_cap: 15000, loss_cap_tripped: false, realized_net_pnl: -300, unrealized_net_pnl: 0, open_positions: 0, closed_trades: 2, win_rate: 50, profit_factor: 0.8, total_charges: 90 };
const base: CxOverview = {
  summary: { enabled: false, starting_capital: 500000, equity: 499700, realized_net_pnl: -300, unrealized_net_pnl: 0, open_positions: 1, closed_trades: 2, win_rate: 50, total_charges: 90,
    pools: { commodity: pool, currency: { ...pool, enabled: false, parked: true, loss_cap: 5000 } },
    sessions: { MCX: { open: true, entry_allowed: true, square_off_due: false }, CURRENCY: { open: false, entry_allowed: false, square_off_due: true } },
    last_cycle: { status: 'ok' }, symbols: { CRUDEOIL: { state: 'WATCHING', contract: 'CRUDEOIL NOV FUT', expiry: '2026-10-27', last_bar: '2026-10-19 19:00:00' } } },
  open_positions: [pos], closed_today: [], recent_closed: [{ ...pos, status: 'CLOSED', closed_at: '2026-10-19T19:40:00+05:30', exit_price: 70, exit_reason: 'STOP_LOSS', net_pnl: -3100 }],
  decisions: [{ ts: '2026-10-19 19:05:00', symbol: 'CRUDEOIL', side: 'CE', strategy: 'SETUP_17_RANGE_BREAK', decision: 'ENTERED', reason: 'SIGNAL' }],
  settings: { lots: 1, sl_pct: 30, target_pct: 50, symbols: ['CRUDEOIL'] }, as_of: '19:10:00',
};

describe('CxScreen', () => {
  it('shows the off state, pools with separate loss caps, sessions, positions and decisions', () => {
    render(<CxScreen initial={base} />);
    expect(screen.getByText(/OFF: nothing is entered/)).toBeInTheDocument();
    expect(screen.getByText('Commodities (MCX)')).toBeInTheDocument();
    expect(screen.getByText('Parked until a USDINR data check passes')).toBeInTheDocument();
    expect(screen.getByTestId('cx-sessions')).toHaveTextContent('MCX open');
    expect(screen.getByTestId('cx-sessions')).not.toHaveTextContent('NSE currency');
    expect(screen.getByText('+₹1,100', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('STOP_LOSS')).toBeInTheDocument();
    expect(screen.getByText('Watching')).toBeInTheDocument();
    expect(screen.getAllByText('Setup 17 range break').length).toBeGreaterThan(0);
  });

  it('shows empty states', () => {
    render(<CxScreen initial={{ ...base, open_positions: [], recent_closed: [], decisions: [], summary: { ...base.summary, enabled: true, symbols: {} } }} />);
    expect(screen.getByText('No open positions.')).toBeInTheDocument();
    expect(screen.getByText(/No cycle has run yet/)).toBeInTheDocument();
    expect(screen.getByText('ON')).toBeInTheDocument();
  });

  it('says why nothing happens when the book is on but no Dhan login is connected', () => {
    render(<CxScreen initial={{ ...base, summary: { ...base.summary, enabled: true, last_cycle: { status: 'no_credentials' } } }} />);
    expect(screen.getByTestId('cx-cycle-note')).toHaveTextContent(/No Dhan login is connected/);
  });

  it('shows no note while cycles run fine', () => {
    render(<CxScreen initial={{ ...base, summary: { ...base.summary, enabled: true } }} />);
    expect(screen.queryByTestId('cx-cycle-note')).toBeNull();
  });
});
