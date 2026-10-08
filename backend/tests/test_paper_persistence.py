import os
import tempfile
import pytest
from app.services.paper_trader import PaperTradingEngine, PaperPosition
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation

def make_sample_signal(symbol="NIFTY 50", sig_id="TEST_SIG_01") -> Signal:
    rec = OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=25000.0,
        option_type="CE",
        atm_strike=25000,
        recommended_strike=24950,
        strike_symbol=f"{symbol} 24950 CE",
        lot_size=65,
        risk=40.0,
        stop_loss=24960.0,
        target_1=25060.0,
        target_2=25100.0,
        estimated_option_entry=150.0,
        option_sl_pts=22.0,
        option_target_1_pts=33.0,
        option_target_2_pts=55.0,
        option_sl_price=128.0,
        option_target_1_price=183.0,
        option_target_2_price=205.0,
    )
    return Signal(
        id=sig_id,
        symbol=symbol,
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type="CE",
        timestamp="2026-10-09 10:00:00",
        entry_price=25000.0,
        stop_loss=24960.0,
        target_1=25060.0,
        target_2=25100.0,
        strike_recommendation=rec,
        indicators_snapshot={"close": 25000.0},
        rationale="Test squeeze signal"
    )

def test_sqlite_persistence_initialization_creates_db(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    assert os.path.exists(db_file)
    port = engine.get_portfolio()
    assert port.active_positions == []
    assert port.closed_trades == []

def test_trade_persisted_and_restored_across_engine_restart(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    
    # Engine 1 opens position
    engine1 = PaperTradingEngine(db_path=db_file)
    sig = make_sample_signal("BANKNIFTY", "SIG_PERSIST_01")
    pos = engine1.open_position_from_signal(sig, lots=2)
    assert pos is not None
    assert len(engine1.get_portfolio().active_positions) == 1

    # Engine 2 simulates fresh reboot with same DB path
    engine2 = PaperTradingEngine(db_path=db_file)
    p2 = engine2.get_portfolio()
    assert len(p2.active_positions) == 1
    restored_pos = p2.active_positions[0]
    assert restored_pos.id == pos.id
    assert restored_pos.symbol == "BANKNIFTY"
    assert restored_pos.strike_symbol == pos.strike_symbol
    assert restored_pos.lots == 2
    assert restored_pos.underlying_entry == 25000.0
    assert restored_pos.status == "OPEN"

def test_closed_trade_and_metrics_restored_across_restart(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine1 = PaperTradingEngine(db_path=db_file)
    sig = make_sample_signal("NIFTY 50", "SIG_CLOSED_01")
    engine1.open_position_from_signal(sig, lots=2)

    # Move price to hit Target 1 and Target 2
    engine1.update_market_prices({"NIFTY 50": 25065.0})  # Target 1: half booked
    engine1.update_market_prices({"NIFTY 50": 25105.0})  # Target 2: fully closed
    
    p1 = engine1.get_portfolio()
    assert len(p1.active_positions) == 0
    assert len(p1.closed_trades) == 1
    assert p1.total_realized_pnl > 0
    assert p1.win_rate_pct == 100.0

    # Engine 2 reboot
    engine2 = PaperTradingEngine(db_path=db_file)
    p2 = engine2.get_portfolio()
    assert len(p2.active_positions) == 0
    assert len(p2.closed_trades) == 1
    assert p2.closed_trades[0].status == "TARGET_2"
    assert p2.closed_trades[0].exit_reason == "Target 2 (1:2.5) Hit"
    assert p2.total_realized_pnl == p1.total_realized_pnl
    assert p2.win_rate_pct == 100.0

def test_settings_and_duplicate_signal_protection_persisted(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine1 = PaperTradingEngine(db_path=db_file)
    engine1.set_auto_trade(False)
    engine1.set_default_lots(4)
    sig = make_sample_signal("NIFTY 50", "SIG_DEDUP_01")
    engine1.open_position_from_signal(sig, lots=4)

    # Engine 2 reboot
    engine2 = PaperTradingEngine(db_path=db_file)
    p2 = engine2.get_portfolio()
    assert p2.auto_trade_enabled is False
    assert p2.default_lots == 4

    # Duplicate signal should be rejected by restored _processed_signal_ids
    duplicate_res = engine2.open_position_from_signal(sig)
    assert duplicate_res is None

def test_reset_clears_db_and_restarts_cleanly(tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine1 = PaperTradingEngine(db_path=db_file)
    sig = make_sample_signal("NIFTY 50", "SIG_RESET_01")
    engine1.open_position_from_signal(sig, lots=2)
    assert len(engine1.get_portfolio().active_positions) == 1

    engine1.reset()
    assert len(engine1.get_portfolio().active_positions) == 0

    # Engine 2 reboot
    engine2 = PaperTradingEngine(db_path=db_file)
    p2 = engine2.get_portfolio()
    assert len(p2.active_positions) == 0
    assert len(p2.closed_trades) == 0
