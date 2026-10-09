import pytest
from app.services.paper_trader import PaperTradingEngine
from app.services.strike_selector import recommend_strike
from app.services.strategy_engine import Signal, SetupType

def create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0) -> Signal:
    rec = recommend_strike(symbol, entry, opt, sl)
    return Signal(
        id=f"test_sig_{symbol}_{opt}",
        symbol=symbol,
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type=opt,
        timestamp="09:30:00",
        entry_price=entry,
        stop_loss=sl,
        target_1=rec.target_1,
        target_2=rec.target_2,
        strike_recommendation=rec,
        indicators_snapshot={},
        rationale="Test"
    )

def test_paper_trading_open_and_metrics():
    engine = PaperTradingEngine()
    sig = create_mock_signal()
    
    pos = engine.open_position_from_signal(sig, lots=1)
    assert pos is not None
    assert pos.symbol == "NIFTY 50"
    assert pos.lot_size == 65
    assert pos.quantity == 65
    assert pos.status == "OPEN"

    portfolio = engine.get_portfolio()
    assert len(portfolio.active_positions) == 1
    assert portfolio.active_positions[0].id == pos.id

def test_paper_trading_sl_hit():
    engine = PaperTradingEngine()
    sig = create_mock_signal(entry=25000.0, sl=24950.0)
    pos = engine.open_position_from_signal(sig, lots=1)
    
    # Update market price below SL (e.g. 24940)
    engine.update_market_prices({"NIFTY 50": 24940.0})
    portfolio = engine.get_portfolio()
    
    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status == "STOPPED_OUT"
    assert closed.pnl_rupees < 0

def test_paper_trading_target_hit():
    engine = PaperTradingEngine()
    sig = create_mock_signal(entry=25000.0, sl=24950.0)
    pos = engine.open_position_from_signal(sig, lots=1)
    
    # Update market price above Target 2 (target 2 is 25000 + 2.5 * 50 = 25125)
    engine.update_market_prices({"NIFTY 50": 25130.0})
    portfolio = engine.get_portfolio()
    
    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status == "TARGET_2"
    assert closed.pnl_rupees > 0
    assert portfolio.win_rate_pct == 100.0

def test_default_lots_is_two():
    engine = PaperTradingEngine()
    portfolio = engine.get_portfolio()
    assert portfolio.default_lots == 2

def test_partial_profit_booking_at_target_1():
    engine = PaperTradingEngine()
    # NIFTY 50 entry 25000, SL 24950 (risk 50). Target 1 is 25000 + 1.5 * 50 = 25075
    sig = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0)
    pos = engine.open_position_from_signal(sig, lots=2)
    assert pos.lots == 2
    assert pos.quantity == 130 # 2 * 65

    # Price moves to Target 1 (25075.0)
    engine.update_market_prices({"NIFTY 50": 25075.0})
    portfolio = engine.get_portfolio()

    # Position should still be active, but 1 lot booked (50%) and 1 lot running
    assert len(portfolio.active_positions) == 1
    active_pos = portfolio.active_positions[0]
    assert active_pos.status == "TARGET_1"
    assert active_pos.lots == 1
    assert active_pos.quantity == 65
    assert active_pos.booked_lots == 1
    assert active_pos.booked_pnl_rupees > 0
    # Stop loss trailed to breakeven
    assert active_pos.underlying_sl == 25000.0
    assert active_pos.option_sl == active_pos.option_entry
    # Realized P&L immediately reflects the booked lot
    assert portfolio.total_realized_pnl > 0

def test_target_1_runner_hits_breakeven_sl_retains_profit():
    engine = PaperTradingEngine()
    sig = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0)
    engine.open_position_from_signal(sig, lots=2)

    # 1. Reach Target 1
    engine.update_market_prices({"NIFTY 50": 25075.0})
    portfolio = engine.get_portfolio()
    booked_profit = portfolio.total_realized_pnl
    assert booked_profit > 0

    # 2. Market pulls back to Entry (Breakeven SL trigger at 25000)
    engine.update_market_prices({"NIFTY 50": 24995.0})
    portfolio = engine.get_portfolio()

    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert "Breakeven Trailed SL Hit" in closed.exit_reason
    # Total P&L must retain the booked profit from Target 1!
    assert closed.pnl_rupees == pytest.approx(booked_profit, rel=0.01)
    assert portfolio.total_realized_pnl == pytest.approx(booked_profit, rel=0.01)
    assert portfolio.winning_trades_count == 1
    assert portfolio.win_rate_pct == 100.0

def test_target_1_runner_hits_target_2_full_booking():
    engine = PaperTradingEngine()
    # BANK NIFTY entry 50000, SL 49900 (risk 100). Target 1 is 50150, Target 2 is 50250
    sig = create_mock_signal(symbol="BANK NIFTY", opt="CE", entry=50000.0, sl=49900.0)
    engine.open_position_from_signal(sig, lots=2)

    # 1. Reach Target 1 (book 1 lot)
    engine.update_market_prices({"BANK NIFTY": 50150.0})
    booked_t1_pnl = engine.get_portfolio().total_realized_pnl
    assert booked_t1_pnl > 0

    # 2. Reach Target 2 (book runner lot)
    engine.update_market_prices({"BANK NIFTY": 50260.0})
    portfolio = engine.get_portfolio()

    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status == "TARGET_2"
    assert "Target 2" in closed.exit_reason
    # Total P&L must be greater than just Target 1 profit
    assert closed.pnl_rupees > booked_t1_pnl
    assert portfolio.total_realized_pnl == closed.pnl_rupees
    assert portfolio.win_rate_pct == 100.0

def test_pe_partial_profit_booking_and_runner_target_2():
    engine = PaperTradingEngine()
    # NIFTY 50 PE entry 25000, SL 25050 (risk 50). Target 1 is 25000 - 1.5 * 50 = 24925, Target 2 is 24875
    sig = create_mock_signal(symbol="NIFTY 50", opt="PE", entry=25000.0, sl=25050.0)
    pos = engine.open_position_from_signal(sig, lots=2)
    assert pos.lots == 2
    assert pos.quantity == 130

    # 1. Reach Target 1 (24925.0)
    engine.update_market_prices({"NIFTY 50": 24925.0})
    portfolio = engine.get_portfolio()
    assert len(portfolio.active_positions) == 1
    active_pos = portfolio.active_positions[0]
    assert active_pos.status == "TARGET_1"
    assert active_pos.lots == 1
    assert active_pos.quantity == 65
    assert active_pos.booked_lots == 1
    assert active_pos.booked_pnl_rupees > 0
    assert active_pos.underlying_sl == 25000.0
    booked_profit = portfolio.total_realized_pnl
    assert booked_profit > 0

    # 2. Reach Target 2 (24870.0)
    engine.update_market_prices({"NIFTY 50": 24870.0})
    portfolio = engine.get_portfolio()
    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status == "TARGET_2"
    assert closed.pnl_rupees > booked_profit
    assert portfolio.total_realized_pnl == closed.pnl_rupees

def test_four_lots_partial_booking_halves_position():
    engine = PaperTradingEngine()
    sig = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0)
    pos = engine.open_position_from_signal(sig, lots=4)
    assert pos.lots == 4
    assert pos.quantity == 260 # 4 * 65

    # Target 1 reached: 4 lots -> books 2 lots (50%), 2 lots remain
    engine.update_market_prices({"NIFTY 50": 25075.0})
    portfolio = engine.get_portfolio()
    active_pos = portfolio.active_positions[0]
    assert active_pos.status == "TARGET_1"
    assert active_pos.lots == 2
    assert active_pos.quantity == 130
    assert active_pos.booked_lots == 2
    assert active_pos.booked_pnl_rupees > 0

def test_live_option_quote_updates_pnl_directly():
    engine = PaperTradingEngine()
    sig = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=22500.0, sl=22450.0)
    # Set real option security id and real live entry price
    sig.strike_recommendation.option_security_id = "44608"
    sig.strike_recommendation.estimated_option_entry = 160.0
    sig.strike_recommendation.option_sl_price = 135.0
    sig.strike_recommendation.option_target_1_price = 195.0
    sig.strike_recommendation.option_target_2_price = 230.0

    pos = engine.open_position_from_signal(sig, lots=2)
    assert pos.option_security_id == "44608"
    assert pos.option_entry == 160.0
    assert pos.quantity == 130 # 2 lots of 65

    # Update with real option marketfeed quote at 172.5
    engine.update_market_prices(
        price_map={"NIFTY 50": 22520.0},
        option_price_map={"44608": 172.5}
    )
    portfolio = engine.get_portfolio()
    p = portfolio.active_positions[0]
    assert p.current_option_price == 172.5
    assert p.pnl_points == 12.5 # 172.5 - 160.0
    assert p.pnl_rupees == 12.5 * 130 # 1625.0
    assert portfolio.total_unrealized_pnl == 1625.0

    # Real option price hits Target 1 (195.0) -> partial profit booked on 1 lot
    engine.update_market_prices(
        price_map={"NIFTY 50": 22560.0},
        option_price_map={"44608": 196.0}
    )
    portfolio = engine.get_portfolio()
    p = portfolio.active_positions[0]
    assert p.status == "TARGET_1"
    assert p.lots == 1
    assert p.quantity == 65
    assert p.booked_lots == 1
    assert p.booked_pnl_rupees == round(36.0 * 65, 2) # (196.0 - 160.0) * 65 = 2340.0



