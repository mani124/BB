import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PaperPortfolioView } from './PaperPortfolioView';
import { PaperPortfolio, PaperPosition } from '../types';

describe('PaperPortfolioView Setup Filter & Tax Popover', () => {
  const mockTrades: PaperPosition[] = [
    {
      id: 'POS_1',
      signal_id: 'SIG_1',
      symbol: 'NIFTY 50',
      option_type: 'CE',
      strike_symbol: 'NIFTY 22450 CE',
      timeframe: '5m',
      setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
      entry_time: '09:30:00',
      exit_time: '09:45:00',
      underlying_entry: 22500,
      underlying_sl: 22470,
      underlying_target_1: 22545,
      underlying_target_2: 22575,
      option_entry: 152.0,
      theoretical_entry: 150.0,
      entry_slippage: 2.0,
      option_sl: 133.5,
      option_target_1: 174.8,
      option_target_2: 191.3,
      lot_size: 65,
      lots: 2,
      quantity: 130,
      current_underlying: 22580,
      current_option_price: 190.5,
      theoretical_exit: 191.3,
      exit_slippage: 0.8,
      total_slippage_cost: 364.0,
      pnl_points: 38.5,
      pnl_rupees: 5005.0,
      gross_pnl: 5005.0,
      total_charges: 88.5,
      net_pnl: 4916.5,
      status: 'CLOSED',
      exit_reason: 'Target 2 Hit',
      charges_breakdown: {
        buy_turnover: 19760.0,
        sell_turnover: 24765.0,
        total_turnover: 44525.0,
        orders_count: 2,
        brokerage: 40.0,
        stt: 24.77,
        exchange_fee: 22.26,
        sebi_fee: 0.04,
        stamp_duty: 0.59,
        gst: 11.21,
        total_charges: 98.87
      }
    },
    {
      id: 'POS_2',
      signal_id: 'SIG_2',
      symbol: 'BANKNIFTY',
      option_type: 'PE',
      strike_symbol: 'BANKNIFTY 48500 PE',
      timeframe: '15m',
      setup_type: 'SETUP_2_WALKING_BANDS',
      entry_time: '10:00:00',
      exit_time: '10:15:00',
      underlying_entry: 48500,
      underlying_sl: 48600,
      underlying_target_1: 48350,
      underlying_target_2: 48250,
      option_entry: 250.0,
      theoretical_entry: 250.0,
      entry_slippage: 0.0,
      option_sl: 200.0,
      option_target_1: 325.0,
      option_target_2: 375.0,
      lot_size: 30,
      lots: 2,
      quantity: 60,
      current_underlying: 48610,
      current_option_price: 195.0,
      pnl_points: -55.0,
      pnl_rupees: -3300.0,
      gross_pnl: -3300.0,
      exit_slippage: 0.0,
      total_charges: 62.0,
      net_pnl: -3362.0,
      status: 'STOPPED_OUT',
      exit_reason: 'Stop-Loss Hit'
    }
  ];

  const mockPortfolio: PaperPortfolio = {
    active_positions: [],
    closed_trades: mockTrades,
    auto_trade_enabled: true,
    default_lots: 2,
    total_realized_pnl: 1554.5,
    total_unrealized_pnl: 0,
    total_pnl: 1554.5,
    total_gross_pnl: 1705.0,
    total_slippage_cost: 364.0,
    avg_slippage_points: 1.4,
    total_charges: 150.5,
    total_net_pnl: 1554.5,
    win_rate_pct: 50.0,
    total_trades_count: 2,
    winning_trades_count: 1,
    losing_trades_count: 1
  };

  it('renders filter pills and filters closed trades by setup', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    // Initial state: 2 trades shown
    expect(screen.getByText('NIFTY 22450 CE')).toBeInTheDocument();
    expect(screen.getByText('BANKNIFTY 48500 PE')).toBeInTheDocument();

    // Click Setup 1 pill
    const s1Button = screen.getByRole('button', { name: /Setup 1/i });
    fireEvent.click(s1Button);

    expect(screen.getByText('NIFTY 22450 CE')).toBeInTheDocument();
    expect(screen.queryByText('BANKNIFTY 48500 PE')).not.toBeInTheDocument();
  });

  it('displays 0.0% win rate cleanly when filtered setup has no trades', () => {
    // Review Focus: Zero matching trades must display 0.0% without NaN%
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    const s4Button = screen.getByRole('button', { name: /Setup 4/i });
    fireEvent.click(s4Button);

    expect(screen.getByText(/0 Trades/i)).toBeInTheDocument();
    expect(screen.getByText(/0.0% Win Rate/i)).toBeInTheDocument();
  });

  it('opens itemized charges breakdown popover when receipt icon is clicked', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    const receiptBtn = screen.getByTitle(/View Charges Breakdown/i);
    fireEvent.click(receiptBtn);

    expect(screen.getByText(/Dhan & Statutory Taxes Receipt/i)).toBeInTheDocument();
    const modal = screen.getByText(/Dhan & Statutory Taxes Receipt/i).closest('.shadow-2xl') as HTMLElement;
    expect(modal).toBeInTheDocument();
    expect(within(modal).getByText(/Brokerage/i)).toBeInTheDocument();
    expect(within(modal).getByText(/STT/i)).toBeInTheDocument();
    expect(within(modal).getByText(/NSE Exchange Fee/i)).toBeInTheDocument();
  });

  it('formats exit slippage correctly without negative zero', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    // POS_1 has exit_slippage = 0.8 -> (Slip: -0.8 pts)
    expect(screen.getByText('(Slip: -0.8 pts)')).toBeInTheDocument();
    // POS_2 has exit_slippage = 0.0 -> (Slip: 0.0 pts) (not -0.0 pts)
    expect(screen.getByText('(Slip: 0.0 pts)')).toBeInTheDocument();
    expect(screen.queryByText('(Slip: -0.0 pts)')).not.toBeInTheDocument();
  });

  it('filters closed trades by Setups 6, 7, and 8 correctly and updates dynamic summary strip', () => {
    const snapbackTrades: PaperPosition[] = [
      ...mockTrades,
      {
        id: 'POS_6',
        signal_id: 'SIG_6',
        symbol: 'NIFTY 50',
        option_type: 'PE',
        strike_symbol: 'NIFTY 22400 PE',
        timeframe: '5m',
        setup_type: 'SETUP_6_PINBAR_SNAPBACK',
        entry_time: '11:00:00',
        exit_time: '11:15:00',
        underlying_entry: 22450,
        underlying_sl: 22480,
        underlying_target_1: 22400,
        underlying_target_2: 22370,
        option_entry: 120.0,
        option_sl: 100.0,
        option_target_1: 150.0,
        option_target_2: 170.0,
        lot_size: 65,
        lots: 2,
        quantity: 130,
        current_underlying: 22390,
        current_option_price: 155.0,
        pnl_points: 35.0,
        pnl_rupees: 4550.0,
        gross_pnl: 4550.0,
        total_charges: 70.0,
        net_pnl: 4480.0,
        total_slippage_cost: 65.0,
        status: 'CLOSED',
        exit_reason: 'Target 1 Hit',
      },
      {
        id: 'POS_7',
        signal_id: 'SIG_7',
        symbol: 'BANKNIFTY',
        option_type: 'CE',
        strike_symbol: 'BANKNIFTY 48600 CE',
        timeframe: '5m',
        setup_type: 'SETUP_7_INSIDE_BAR_SNAPBACK',
        entry_time: '11:30:00',
        exit_time: '11:45:00',
        underlying_entry: 48550,
        underlying_sl: 48450,
        underlying_target_1: 48700,
        underlying_target_2: 48800,
        option_entry: 210.0,
        option_sl: 160.0,
        option_target_1: 280.0,
        option_target_2: 340.0,
        lot_size: 30,
        lots: 2,
        quantity: 60,
        current_underlying: 48440,
        current_option_price: 155.0,
        pnl_points: -55.0,
        pnl_rupees: -3300.0,
        gross_pnl: -3300.0,
        total_charges: 60.0,
        net_pnl: -3360.0,
        total_slippage_cost: 30.0,
        status: 'STOPPED_OUT',
        exit_reason: 'Stop-Loss Hit',
      },
      {
        id: 'POS_8',
        signal_id: 'SIG_8',
        symbol: 'FINNIFTY',
        option_type: 'PE',
        strike_symbol: 'FINNIFTY 21200 PE',
        timeframe: '15m',
        setup_type: 'SETUP_8_DIVERGENCE_SNAPBACK',
        entry_time: '12:00:00',
        exit_time: '12:20:00',
        underlying_entry: 21250,
        underlying_sl: 21290,
        underlying_target_1: 21190,
        underlying_target_2: 21150,
        option_entry: 110.0,
        option_sl: 85.0,
        option_target_1: 145.0,
        option_target_2: 170.0,
        lot_size: 65,
        lots: 2,
        quantity: 130,
        current_underlying: 21180,
        current_option_price: 148.0,
        pnl_points: 38.0,
        pnl_rupees: 4940.0,
        gross_pnl: 4940.0,
        total_charges: 75.0,
        net_pnl: 4865.0,
        total_slippage_cost: 50.0,
        status: 'CLOSED',
        exit_reason: 'Target 1 Hit',
      },
    ];

    const portfolioWithSnapback: PaperPortfolio = {
      ...mockPortfolio,
      closed_trades: snapbackTrades,
      total_trades_count: snapbackTrades.length,
    };

    render(
      <PaperPortfolioView
        portfolio={portfolioWithSnapback}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    // 1. Verify Setup 6 (Pin Bar) filter
    const s6Btn = screen.getByRole('button', { name: /Setup 6 \(Pin Bar\)/i });
    fireEvent.click(s6Btn);
    expect(screen.getByText('NIFTY 22400 PE')).toBeInTheDocument();
    expect(screen.queryByText('BANKNIFTY 48600 CE')).not.toBeInTheDocument();
    expect(screen.queryByText('FINNIFTY 21200 PE')).not.toBeInTheDocument();
    expect(screen.queryByText('NIFTY 22450 CE')).not.toBeInTheDocument();
    expect(screen.getByText(/1 Trades/i)).toBeInTheDocument();
    expect(screen.getByText(/100.0% Win Rate/i)).toBeInTheDocument();

    // 2. Verify Setup 7 (Inside Bar) filter
    const s7Btn = screen.getByRole('button', { name: /Setup 7 \(Inside Bar\)/i });
    fireEvent.click(s7Btn);
    expect(screen.getByText('BANKNIFTY 48600 CE')).toBeInTheDocument();
    expect(screen.queryByText('NIFTY 22400 PE')).not.toBeInTheDocument();
    expect(screen.queryByText('FINNIFTY 21200 PE')).not.toBeInTheDocument();
    expect(screen.getByText(/1 Trades/i)).toBeInTheDocument();
    expect(screen.getByText(/0.0% Win Rate/i)).toBeInTheDocument();

    // 3. Verify Setup 8 (Climax Divergence) filter
    const s8Btn = screen.getByRole('button', { name: /Setup 8 \(Climax Divergence\)/i });
    fireEvent.click(s8Btn);
    expect(screen.getByText('FINNIFTY 21200 PE')).toBeInTheDocument();
    expect(screen.queryByText('NIFTY 22400 PE')).not.toBeInTheDocument();
    expect(screen.queryByText('BANKNIFTY 48600 CE')).not.toBeInTheDocument();
    expect(screen.getByText(/1 Trades/i)).toBeInTheDocument();
    expect(screen.getByText(/100.0% Win Rate/i)).toBeInTheDocument();
  });
});

