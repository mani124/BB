import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { OpenPositionsPanel, PortfolioStrip } from './PaperPortfolioView';
import type { PaperPosition, PaperPortfolio } from '../types';

const pos = (over: Partial<PaperPosition>): PaperPosition => ({
  id: 'p1', signal_id: 's1', symbol: 'GVT&D', option_type: 'PE', strike_symbol: 'GVT&D 4000 PE',
  timeframe: '5m', setup_type: 'SETUP_5_OPTION_BB', entry_time: '11:20:03', underlying_entry: 4000,
  underlying_sl: 4010, underlying_target_1: 3990, underlying_target_2: 3980, option_entry: 92,
  option_sl: 92, option_target_1: 120, option_target_2: 134.8, lot_size: 125, lots: 1, quantity: 125,
  current_underlying: 3990, current_option_price: 125, pnl_points: 33, pnl_rupees: 4125,
  status: 'TARGET_1', ...over,
});

describe('open position P&L', () => {
  it('shows booked amount and unrealized split for a partial exit', () => {
    render(
      <OpenPositionsPanel
        positions={[pos({ booked_lots: 1, initial_lots: 2, booked_pnl_rupees: 3500, unrealized_pnl_rupees: 4125, pnl_rupees: 7625, est_exit_charges: 140, est_net_pnl: 7485 })]}
        onClosePosition={() => {}}
      />,
    );
    expect(screen.getByText(/1 of 2 lots booked at T1/)).toHaveTextContent('+₹3,500.00 locked in');
    expect(screen.getByText(/Unrealized \+₹4,125.00/)).toBeInTheDocument();
    expect(screen.getByText(/Net if closed now \+₹7,485.00/)).toBeInTheDocument();
  });

  it('does not claim a booking when a single lot hit T1', () => {
    render(<OpenPositionsPanel positions={[pos({ booked_lots: 0, booked_pnl_rupees: 0 })]} onClosePosition={() => {}} />);
    expect(screen.getByText(/nothing is booked/)).toBeInTheDocument();
    expect(screen.queryByText(/lots booked/)).toBeNull();
  });

  it('strip shows the unrealized block', () => {
    const portfolio = { active_positions: [pos({})], total_unrealized_pnl: 4125, total_unrealized_net: 3985, total_unrealized_charges: 140 } as PaperPortfolio;
    render(<PortfolioStrip portfolio={portfolio} />);
    expect(screen.getByText(/Unrealized P&L \(open\)/)).toBeInTheDocument();
    expect(screen.getByText('+₹4,125.00')).toBeInTheDocument();
  });
});
