import pytest
from datetime import datetime, timedelta
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import recommend_strike
from app.services.paper_trader import PaperTradingEngine

def make_test_signal(
    signal_id: str,
    symbol: str = "FINNIFTY",
    option_type: str = "CE",
    entry_price: float = 25000.0,
    sl: float = 24980.0,
    timestamp: str = "14:20:00"
) -> Signal:
    rec = recommend_strike(symbol, entry_price, option_type, sl)
    return Signal(
        id=signal_id,
        symbol=symbol,
        timeframe="5m",
        setup_type=SetupType.SETUP_2_WALKING,
        option_type=option_type,
        timestamp=timestamp,
        entry_price=entry_price,
        stop_loss=sl,
        target_1=rec.target_1,
        target_2=rec.target_2,
        strike_recommendation=rec,
        indicators_snapshot={},
        rationale="Test signal"
    )

def test_stopped_out_trade_blocks_reentry_in_same_chop_box(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    engine.set_auto_trade(True)

    # 1. First trade entered at 25,000
    sig1 = make_test_signal("SIG_1", symbol="FINNIFTY", option_type="CE", entry_price=25000.0, sl=24985.0)
    pos1 = engine.open_position_from_signal(sig1)
    assert pos1 is not None

    # 2. Position stops out at 24,980
    engine.update_market_prices({"FINNIFTY": 24980.0}, {})
    assert len(engine.get_portfolio().active_positions) == 0
    assert engine.get_portfolio().closed_trades[-1].status == "STOPPED_OUT"

    # 3. New signal arrives in the same chop box at 24,995 (below previous entry high of 25,000)
    sig2 = make_test_signal("SIG_2", symbol="FINNIFTY", option_type="CE", entry_price=24995.0, sl=24980.0)
    pos2 = engine.open_position_from_signal(sig2)

    # Must be BLOCKED to prevent consecutive stop-out churn
    assert pos2 is None, "Should block re-entry inside the failed chop box"

def test_stopped_out_trade_permits_reentry_on_higher_high_breakout(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    engine.set_auto_trade(True)

    # 1. First trade entered at 25,000
    sig1 = make_test_signal("SIG_1", symbol="FINNIFTY", option_type="CE", entry_price=25000.0, sl=24985.0)
    pos1 = engine.open_position_from_signal(sig1)
    assert pos1 is not None

    # 2. Position stops out
    engine.update_market_prices({"FINNIFTY": 24980.0}, {})
    assert len(engine.get_portfolio().active_positions) == 0

    # 3. Price breaks OUT of the chop box to a genuine Higher High at 25,015 (> 25,000)
    sig2 = make_test_signal("SIG_2", symbol="FINNIFTY", option_type="CE", entry_price=25015.0, sl=24995.0)
    pos2 = engine.open_position_from_signal(sig2)

    # Must be PERMITTED because genuine breakout momentum is proven
    assert pos2 is not None, "Should permit re-entry when price breaks above failed trade high"

def test_winning_trade_permits_immediate_reentry(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    engine.set_auto_trade(True)

    # 1. Enter trade at 72,500
    sig1 = make_test_signal("SIG_1", symbol="SENSEX", option_type="CE", entry_price=72500.0, sl=72450.0)
    pos1 = engine.open_position_from_signal(sig1)
    assert pos1 is not None

    # 2. Hits Target 2 at 72,630
    engine.update_market_prices({"SENSEX": 72630.0}, {})
    assert len(engine.get_portfolio().active_positions) == 0
    assert engine.get_portfolio().closed_trades[-1].status == "TARGET_2"

    # 3. Next signal arrives: winning trades should NEVER be blocked
    sig2 = make_test_signal("SIG_2", symbol="SENSEX", option_type="CE", entry_price=72555.0, sl=72510.0)
    pos2 = engine.open_position_from_signal(sig2)
    assert pos2 is not None, "Winning trades must have zero re-entry block"

def test_pe_stopped_out_trade_blocks_reentry_and_permits_on_lower_low(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    engine.set_auto_trade(True)

    # 1. First PE trade entered at 25,000, SL at 25,020
    sig1 = make_test_signal("SIG_1", symbol="FINNIFTY", option_type="PE", entry_price=25000.0, sl=25020.0)
    pos1 = engine.open_position_from_signal(sig1)
    assert pos1 is not None

    # 2. Position stops out at 25,025
    engine.update_market_prices({"FINNIFTY": 25025.0}, {})
    assert len(engine.get_portfolio().active_positions) == 0

    # 3. New PE signal arrives at 25,005 (still above previous entry low of 25,000) -> blocked
    sig2 = make_test_signal("SIG_2", symbol="FINNIFTY", option_type="PE", entry_price=25005.0, sl=25025.0)
    pos2 = engine.open_position_from_signal(sig2)
    assert pos2 is None, "Should block PE re-entry above failed trade entry"

    # 4. Price breaks DOWN to lower low at 24,980 (< 25,000) -> permitted!
    sig3 = make_test_signal("SIG_3", symbol="FINNIFTY", option_type="PE", entry_price=24980.0, sl=25000.0)
    pos3 = engine.open_position_from_signal(sig3)
    assert pos3 is not None, "Should permit PE re-entry on lower-low breakdown"

