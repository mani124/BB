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
