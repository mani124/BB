import sqlite3
import pytest
from app.services.paper_trader import PaperTradingEngine, PaperPosition
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation

@pytest.fixture
def mock_signal():
    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50",
        underlying_price=22500.0,
        option_type="CE",
        atm_strike=22500,
        recommended_strike=22450,
        strike_symbol="NIFTY 22450 CE",
        lot_size=65,
        risk=30.0,
        stop_loss=22470.0,
        target_1=22545.0,
        target_2=22575.0,
        estimated_option_entry=150.0,
        option_sl_pts=16.5,
        option_target_1_pts=24.8,
        option_target_2_pts=41.3,
        option_sl_price=133.5,
        option_target_1_price=174.8,
        option_target_2_price=191.3,
        real_ask_price=152.0,  # +2.0 pts entry slippage
        real_bid_price=149.5,
        real_ltp=150.0,
        is_live_quote=True
    )
    return Signal(
        id="SIG_SLIP_001",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type="CE",
        timestamp="09:35:00",
        entry_price=22500.0,
        stop_loss=22470.0,
        target_1=22545.0,
        target_2=22575.0,
        strike_recommendation=rec,
        indicators_snapshot={
            "close": 22500.0,
            "bb_upper": 22520.0,
            "bb_middle": 22480.0,
            "bb_lower": 22440.0,
            "bandwidth": 3.5,
            "percent_b": 0.75,
            "vwap": 22490.0,
            "rsi": 62.0,
            "ema_9": 22495.0,
            "adx": 28.0
        },
        rationale="Test signal"
    )

def test_entry_slippage_calculation(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None
    # Signal theoretical entry = 150.0, Real Ask fill = 152.0 -> slippage = 2.0 pts
    assert pos.theoretical_entry == 150.0
    assert pos.option_entry == 152.0
    assert pos.entry_slippage == 2.0

def test_favorable_entry_slippage_clamped_to_zero(mock_signal):
    # Review Focus: Ask price lower than signal entry clamps slippage to 0.0
    mock_signal.id = "SIG_SLIP_002"
    mock_signal.strike_recommendation.real_ask_price = 148.0
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos.entry_slippage == 0.0
    assert pos.option_entry == 148.0

def test_favorable_exit_slippage_clamped_to_zero(mock_signal):
    # Review Focus: When exit bid is greater than theoretical target/exit, exit_slippage is clamped to 0.0
    mock_signal.id = "SIG_SLIP_002B"
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None
    closed = engine.close_position(
        pos.id,
        reason="Target 1 Hit",
        exit_price=174.8,
        real_bid_price=176.0,
    )
    assert closed is not None
    assert closed.exit_slippage == 0.0
    assert closed.current_option_price == 176.0

def test_exit_slippage_and_charges_on_target_exit(mock_signal, tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    
    # Target 2 hit: option price jumps to 191.3, but bid is 190.5 (-0.8 pts slippage)
    engine.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_price_map={getattr(pos, "option_security_id", ""): 190.5} if pos.option_security_id else None,
        option_bid_map={pos.id: 190.5}
    )
    portfolio = engine.get_portfolio()
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status in ["TARGET_2", "STOPPED_OUT", "CLOSED"]
    assert closed.gross_pnl > 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)
    assert closed.total_slippage_cost >= 0

def test_legacy_database_migration_backward_compatibility(tmp_path):
    # Review Focus: Database created without new columns must auto-migrate without error
    db_file = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE positions (
            id TEXT PRIMARY KEY, signal_id TEXT, symbol TEXT, option_type TEXT, strike_symbol TEXT,
            timeframe TEXT, setup_type TEXT, entry_time TEXT, underlying_entry REAL, underlying_sl REAL,
            underlying_target_1 REAL, underlying_target_2 REAL, option_entry REAL, option_sl REAL,
            option_target_1 REAL, option_target_2 REAL, lot_size INTEGER, lots INTEGER, quantity INTEGER,
            current_underlying REAL, current_option_price REAL, pnl_points REAL, pnl_rupees REAL,
            status TEXT, exit_time TEXT, exit_reason TEXT, initial_lots INTEGER, initial_quantity INTEGER,
            booked_lots INTEGER, booked_pnl_rupees REAL, option_security_id TEXT
        );
    """)
    conn.commit()
    conn.close()

    engine = PaperTradingEngine(db_path=db_file)
    # Check that it loaded cleanly without raising exceptions
    port = engine.get_portfolio()
    assert len(port.active_positions) == 0

def test_entry_fill_ltp_latency_buffer(mock_signal):
    # Ask price is 0, so LTP + 0.1% buffer is used: 150.0 * 1.001 = 150.15
    mock_signal.id = "SIG_SLIP_003"
    mock_signal.strike_recommendation.real_ask_price = 0.0
    mock_signal.strike_recommendation.real_ltp = 150.0
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos.theoretical_entry == 150.0
    assert pos.option_entry == 150.15
    assert pos.entry_slippage == 0.15

def test_multi_leg_charges_with_tp1_booking(mock_signal, tmp_path):
    db_file = str(tmp_path / "multi_leg.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None

    # Step 1: Hit Target 1 (174.8), books 1 lot
    engine.update_market_prices(
        price_map={"NIFTY 50": 22550.0},
        option_price_map={pos.id: 174.8}
    )
    port = engine.get_portfolio()
    assert len(port.active_positions) == 1
    active = port.active_positions[0]
    assert active.status == "TARGET_1"
    assert active.booked_lots == 1

    # Step 2: Hit Target 2 (191.3), runner closes
    engine.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_bid_map={pos.id: 191.0}
    )
    port = engine.get_portfolio()
    assert len(port.closed_trades) == 1
    closed = port.closed_trades[0]
    assert closed.charges_breakdown is not None
    # Booked lots > 0 means multi-leg execution with 3 orders
    assert closed.charges_breakdown["orders_count"] == 3
    assert closed.charges_breakdown["brokerage"] == 60.0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)

def test_portfolio_aggregate_metrics(mock_signal, tmp_path):
    db_file = str(tmp_path / "portfolio_metrics.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    
    # Close trade via market update
    engine.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_bid_map={pos.id: 190.5}
    )
    port = engine.get_portfolio()
    assert port.total_gross_pnl == port.closed_trades[0].gross_pnl
    assert port.total_charges == port.closed_trades[0].total_charges
    assert port.total_net_pnl == port.closed_trades[0].net_pnl
    assert port.total_slippage_cost == port.closed_trades[0].total_slippage_cost
    assert port.avg_slippage_points > 0.0

def test_exit_fill_real_opt_price_latency_buffer(mock_signal, tmp_path):
    db_file = str(tmp_path / "latency_buffer.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None

    # Target 2 hit: option_price_map provides 191.3, option_bid_map is None
    # P_fill_exit = round(191.3 * 0.999, 2) = 191.11 -> exit_slippage = 191.3 - 191.11 = 0.19 pts
    engine.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_price_map={pos.id: 191.3}
    )
    port = engine.get_portfolio()
    assert len(port.closed_trades) == 1
    closed = port.closed_trades[0]
    assert closed.theoretical_exit == 191.3
    assert closed.current_option_price == 191.11
    assert closed.exit_slippage == 0.19

def test_manual_close_charges_and_slippage(mock_signal, tmp_path):
    db_file = str(tmp_path / "manual_close.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None

    # Manually close position
    closed = engine.close_position(pos.id, reason="MANUAL_PROFIT_TAKE")
    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.exit_reason == "MANUAL_PROFIT_TAKE"
    assert closed.theoretical_exit == 152.0
    assert closed.exit_slippage == 0.0
    assert closed.gross_pnl == 0.0
    assert closed.total_charges > 0.0
    assert closed.net_pnl == -closed.total_charges
    assert closed.charges_breakdown is not None
    assert closed.charges_breakdown["orders_count"] == 2

def test_persistence_roundtrip_charges_breakdown(mock_signal, tmp_path):
    db_file = str(tmp_path / "roundtrip.db")
    engine1 = PaperTradingEngine(db_path=db_file)
    pos = engine1.open_position_from_signal(mock_signal, lots=2)
    engine1.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_bid_map={pos.id: 190.5}
    )
    closed1 = engine1.get_portfolio().closed_trades[0]
    assert closed1.charges_breakdown is not None

    # Restart engine with same DB and verify persistence
    engine2 = PaperTradingEngine(db_path=db_file)
    closed2 = engine2.get_portfolio().closed_trades[0]
    assert closed2.id == closed1.id
    assert closed2.theoretical_entry == closed1.theoretical_entry
    assert closed2.entry_slippage == closed1.entry_slippage
    assert closed2.theoretical_exit == closed1.theoretical_exit
    assert closed2.exit_slippage == closed1.exit_slippage
    assert closed2.total_slippage_cost == closed1.total_slippage_cost
    assert closed2.gross_pnl == closed1.gross_pnl
    assert closed2.total_charges == closed1.total_charges
    assert closed2.net_pnl == closed1.net_pnl
    assert closed2.charges_breakdown == closed1.charges_breakdown

def test_legacy_database_migration_with_existing_rows(tmp_path):
    db_file = str(tmp_path / "legacy_with_data.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE positions (
            id TEXT PRIMARY KEY, signal_id TEXT, symbol TEXT, option_type TEXT, strike_symbol TEXT,
            timeframe TEXT, setup_type TEXT, entry_time TEXT, underlying_entry REAL, underlying_sl REAL,
            underlying_target_1 REAL, underlying_target_2 REAL, option_entry REAL, option_sl REAL,
            option_target_1 REAL, option_target_2 REAL, lot_size INTEGER, lots INTEGER, quantity INTEGER,
            current_underlying REAL, current_option_price REAL, pnl_points REAL, pnl_rupees REAL,
            status TEXT, exit_time TEXT, exit_reason TEXT, initial_lots INTEGER, initial_quantity INTEGER,
            booked_lots INTEGER, booked_pnl_rupees REAL, option_security_id TEXT
        );
    """)
    # Insert one open position and one closed position from legacy schema
    conn.execute("""
        INSERT INTO positions VALUES (
            'POS_LEGACY_OPEN', 'SIG_01', 'NIFTY 50', 'CE', 'NIFTY 22450 CE',
            '5m', 'Setup 1: BB Squeeze Breakout', '09:15:00', 22500.0, 22450.0,
            22550.0, 22600.0, 150.0, 130.0, 175.0, 190.0,
            65, 2, 130, 22500.0, 150.0, 0.0, 0.0,
            'OPEN', NULL, NULL, 2, 130, 0, 0.0, 'SEC_123'
        );
    """)
    conn.execute("""
        INSERT INTO positions VALUES (
            'POS_LEGACY_CLOSED', 'SIG_02', 'BANKNIFTY', 'CE', 'BANKNIFTY 50000 CE',
            '5m', 'Setup 1: BB Squeeze Breakout', '09:20:00', 50000.0, 49900.0,
            50150.0, 50250.0, 200.0, 180.0, 230.0, 250.0,
            15, 2, 30, 50250.0, 250.0, 50.0, 1500.0,
            'TARGET_2', '09:45:00', 'Target 2 (1:2.5) Hit', 2, 30, 0, 0.0, 'SEC_456'
        );
    """)
    conn.commit()
    conn.close()

    engine = PaperTradingEngine(db_path=db_file)
    port = engine.get_portfolio()
    assert len(port.active_positions) == 1
    assert port.active_positions[0].id == "POS_LEGACY_OPEN"
    assert port.active_positions[0].theoretical_entry == 0.0
    assert len(port.closed_trades) == 1
    assert port.closed_trades[0].id == "POS_LEGACY_CLOSED"
    assert port.closed_trades[0].pnl_rupees == 1500.0
    assert port.closed_trades[0].gross_pnl == 1500.0
    assert port.total_realized_pnl == 1500.0

