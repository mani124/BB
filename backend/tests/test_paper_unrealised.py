import pytest
from app.services.paper_trader import PaperTradingEngine
from app.services.strategy_engine import SetupType
from tests.test_paper_slippage import mock_signal  # noqa: F401


def _s5(mock_signal):
    return mock_signal.model_copy(update={"setup_type": SetupType.SETUP_5_OPTION_BB})


def test_setup5_headline_pnl_tracks_price(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(_s5(mock_signal), lots=2)
    engine.update_market_prices(price_map={}, option_price_map={pos.id: 160.0})
    active = engine.get_portfolio().active_positions[0]
    assert active.pnl_points == round(160.0 - active.option_entry, 2)
    assert active.pnl_rupees == round(active.pnl_points * active.quantity, 2)
    assert active.pnl_rupees != 0


def test_setup5_partial_booking_is_included_in_headline(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(_s5(mock_signal), lots=2)
    engine.update_market_prices(price_map={}, option_price_map={pos.id: 175.0})
    engine.update_market_prices(price_map={}, option_price_map={pos.id: 180.0})
    active = engine.get_portfolio().active_positions[0]
    assert active.booked_lots == 1 and active.booked_pnl_rupees > 0
    runner = round(active.pnl_points * active.quantity, 2)
    assert active.pnl_rupees == round(active.booked_pnl_rupees + runner, 2)
    assert active.unrealized_pnl_rupees == runner


def test_single_lot_at_target1_books_nothing(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(_s5(mock_signal), lots=1)
    engine.update_market_prices(price_map={}, option_price_map={pos.id: 175.0})
    active = engine.get_portfolio().active_positions[0]
    assert active.status == "TARGET_1"
    assert active.booked_lots == 0 and active.booked_pnl_rupees == 0


def test_unrealised_estimates_net_of_charges(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    engine.update_market_prices(price_map={"NIFTY 50": 22500.0}, option_price_map={pos.id: 160.0})
    port = engine.get_portfolio()
    active = port.active_positions[0]
    assert active.est_exit_charges > 0
    assert active.est_net_pnl == round(active.pnl_rupees - active.est_exit_charges, 2)
    assert port.total_unrealized_charges == active.est_exit_charges
    assert port.total_unrealized_net == round(port.total_unrealized_pnl - active.est_exit_charges, 2)
    # Matches what closing right now would book.
    closed = engine.close_position(pos.id, real_bid_price=160.0, real_opt_price=160.0)
    assert abs(closed.net_pnl - active.est_net_pnl) < 5
