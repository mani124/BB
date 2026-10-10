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
    # Total P&L must retain the booked profit from Target 1 plus runner P&L at observed exit price
    runner_pnl = round(closed.pnl_points * closed.quantity, 2)
    assert closed.pnl_rupees == pytest.approx(booked_profit + runner_pnl, rel=0.01)
    assert closed.pnl_rupees > 0
    assert portfolio.total_realized_pnl == closed.pnl_rupees
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
    engine.set_max_risk_per_trade(10000.0)
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

def test_risk_capped_position_sizing():
    engine = PaperTradingEngine()
    engine.set_default_lots(2) # Default is 2 lots
    engine.set_max_risk_per_trade(4000.0)

    # 1. Normal index trade: NIFTY 50 with 25 pt SL (14 pt option SL * 65 = ~910 risk/lot)
    # 2 lots = ~1820 risk <= 4000 -> full 2 lots allowed
    sig_nifty = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24975.0)
    pos_nifty = engine.open_position_from_signal(sig_nifty)
    assert pos_nifty is not None
    assert pos_nifty.lots == 2
    assert pos_nifty.quantity == 130

    # 2. Huge lot size stock (TATASTEEL lot 2750):
    # Option risk = 1.1 pts. Risk per lot = 1.1 * 2750 = 3025.
    # 2 lots = 6050 (> 4000). Must scale down to 1 lot!
    sig_tatasteel = create_mock_signal(symbol="TATASTEEL", opt="CE", entry=150.0, sl=149.0)
    pos_tatasteel = engine.open_position_from_signal(sig_tatasteel)
    assert pos_tatasteel is not None
    assert pos_tatasteel.lots == 1, f"Expected 1 lot for TATASTEEL due to max risk cap, got {pos_tatasteel.lots}"
    assert pos_tatasteel.quantity == 2750

    # 3. Excessive risk trade where 1 lot risk > max_risk_per_trade (> 4000)
    # TATASTEEL with 3.0 pt SL -> option risk ~1.65 * 2750 = 4537 risk for 1 lot! (> 4000)
    # Trade must be rejected / skipped to protect capital!
    sig_moderate_excess = create_mock_signal(symbol="TATASTEEL", opt="CE", entry=150.0, sl=147.0)
    pos_mod = engine.open_position_from_signal(sig_moderate_excess)
    assert pos_mod is None, "Trades where 1 lot risk exceeds max_risk_per_trade must be rejected"

def test_trailed_stop_exit_records_actual_observed_price_and_pnl():
    engine = PaperTradingEngine()
    # Signal with option entry 100.0, SL 90.0, Target 1 115.0
    sig = create_mock_signal(symbol="BANK NIFTY", opt="CE", entry=50000.0, sl=49900.0)
    sig.strike_recommendation.estimated_option_entry = 100.0
    sig.strike_recommendation.option_sl_price = 90.0
    sig.strike_recommendation.option_target_1_price = 115.0
    sig.strike_recommendation.option_security_id = "99881"

    pos = engine.open_position_from_signal(sig, lots=2)
    assert pos is not None
    # 1. Trigger Target 1 with real option price 116.0
    engine.update_market_prices(
        price_map={"BANK NIFTY": 50150.0},
        option_price_map={"99881": 116.0}
    )
    assert pos.status == "TARGET_1"
    assert pos.booked_lots == 1
    assert pos.booked_pnl_rupees == (116.0 - 100.0) * pos.lot_size
    # Stop loss trailed to 100.0
    assert pos.option_sl == 100.0

    # 2. Market pulls back and option price drops to 98.0 (slipping below 100.0)
    engine.update_market_prices(
        price_map={"BANK NIFTY": 49990.0},
        option_price_map={"99881": 98.0}
    )
    portfolio = engine.get_portfolio()
    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    # Exit price MUST be the real observed price (98.0), NOT rewritten to entry (100.0)
    assert closed.current_option_price == 98.0, f"Expected 98.0 actual exit price, got {closed.current_option_price}"
    assert closed.pnl_points == -2.0, f"Expected -2.0 runner pnl points, got {closed.pnl_points}"
    # Runner lost 2 pts * 1 lot, so total P&L = booked_pnl - (2.0 * lot_size)
    expected_total_pnl = ((116.0 - 100.0) * pos.lot_size) + ((98.0 - 100.0) * pos.lot_size)
    assert closed.pnl_rupees == expected_total_pnl

def test_manual_trades_must_not_exceed_max_risk_cap():
    engine = PaperTradingEngine()
    engine.set_max_risk_per_trade(4000.0)
    # TATASTEEL risk per lot is ~3025
    sig_tatasteel = create_mock_signal(symbol="TATASTEEL", opt="CE", entry=150.0, sl=149.0)
    # Manual attempt to open 2 lots (2 * 3025 = 6050 > 4000 cap)
    pos = engine.open_position_from_signal(sig_tatasteel, lots=2)
    # Must either clamp to 1 lot or reject; must NOT open 2 lots with 6050 risk
    if pos is not None:
        assert pos.lots == 1, "Manual lots must be clamped to respect max_risk_per_trade"

def test_live_contract_without_real_quote_does_not_use_synthetic_delta():
    engine = PaperTradingEngine()
    sig = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0)
    sig.strike_recommendation.option_security_id = "55555"
    sig.strike_recommendation.estimated_option_entry = 150.0

    pos = engine.open_position_from_signal(sig, lots=1)
    assert pos.current_option_price == 150.0

    # Spot moves up strongly from 25000 to 25100 (+100 pts)
    # But NO option quote provided for "55555"
    engine.update_market_prices(
        price_map={"NIFTY 50": 25100.0},
        option_price_map={}
    )
    # Must NOT fabricate a +55 pt option gain using 0.55 delta
    assert pos.current_option_price == 150.0
    assert pos.pnl_points == 0.0

def test_portfolio_separates_demo_and_live_trades():
    engine = PaperTradingEngine()
    sig_demo = create_mock_signal(symbol="NIFTY 50", opt="CE", entry=25000.0, sl=24950.0)
    sig_live = create_mock_signal(symbol="BANK NIFTY", opt="PE", entry=50000.0, sl=50100.0)
    sig_live.strike_recommendation.option_security_id = "54321"
    sig_live.strike_recommendation.is_live_quote = True
    sig_live.strike_recommendation.real_ask_price = 180.0

    pos_demo = engine.open_position_from_signal(sig_demo, lots=1, feed_mode="demo")
    pos_live = engine.open_position_from_signal(sig_live, lots=1, feed_mode="live")

    assert pos_demo.feed_mode == "demo"
    assert pos_live.feed_mode == "live"

    live_port = engine.get_portfolio(mode="live")
    assert len(live_port.active_positions) == 1
    assert live_port.active_positions[0].symbol == "BANK NIFTY"

    demo_port = engine.get_portfolio(mode="demo")
    assert len(demo_port.active_positions) == 1
    assert demo_port.active_positions[0].symbol == "NIFTY 50"





