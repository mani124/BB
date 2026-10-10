import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import UniverseManager
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation
from app.services.paper_trader import paper_trader


def test_paper_trader_executes_snapback_trades():
    paper_trader.reset_portfolio()
    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="PE",
        atm_strike=25000,
        recommended_strike=25050,
        strike_symbol="NIFTY 25050 PE",
        lot_size=65,
        risk=25.0,
        stop_loss=25035.0,
        target_1=24950.0,
        target_2=24900.0,
        estimated_option_entry=110.0,
        option_sl_pts=18.9,
        option_target_1_pts=27.0,
        option_target_2_pts=54.0,
        option_sl_price=91.1,
        option_target_1_price=137.0,
        option_target_2_price=164.0,
        real_ask_price=112.0,
        real_bid_price=109.0,
        real_ltp=110.0,
        is_live_quote=True,
    )
    sig_s6 = Signal(
        id="SIG_TEST_S6_001",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_6_PINBAR_SNAPBACK,
        option_type="PE",
        timestamp="10:00:00",
        entry_price=25000.0,
        stop_loss=25035.0,
        target_1=24950.0,
        target_2=24900.0,
        strike_recommendation=rec,
        indicators_snapshot={"rsi": 72.0, "adx": 19.0, "bandwidth": 6.5},
        rationale="Setup 6 Pin Bar PE Snapback",
    )

    pos = paper_trader.open_position_from_signal(sig_s6, lots=1)
    assert pos is not None
    assert pos.setup_type == SetupType.SETUP_6_PINBAR_SNAPBACK
    assert pos.option_entry == 112.0
    assert pos.entry_slippage == 2.0

    # Close position and verify charges & slippage calculation
    closed = paper_trader.close_position(pos.id, exit_price=137.0, real_bid_price=136.5)
    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.exit_slippage == 0.5
    assert closed.gross_pnl > 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)


def test_paper_trader_snapback_target_lifecycle():
    paper_trader.reset_portfolio()
    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50",
        underlying_price=24800.0,
        option_type="CE",
        atm_strike=24800,
        recommended_strike=24750,
        strike_symbol="NIFTY 24750 CE",
        lot_size=65,
        risk=30.0,
        stop_loss=24770.0,
        target_1=24845.0,
        target_2=24875.0,
        estimated_option_entry=120.0,
        option_sl_pts=16.2,
        option_target_1_pts=24.3,
        option_target_2_pts=40.5,
        option_sl_price=103.8,
        option_target_1_price=144.3,
        option_target_2_price=160.5,
        real_ask_price=120.0,
        real_bid_price=119.5,
        real_ltp=120.0,
        is_live_quote=True,
    )
    sig_s7 = Signal(
        id="SIG_TEST_S7_001",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_7_INSIDE_BAR_SNAPBACK,
        option_type="CE",
        timestamp="10:15:00",
        entry_price=24800.0,
        stop_loss=24770.0,
        target_1=24845.0,
        target_2=24875.0,
        strike_recommendation=rec,
        indicators_snapshot={"rsi": 28.0, "adx": 18.0, "bandwidth": 5.0},
        rationale="Setup 7 Inside Bar CE Snapback",
    )

    pos = paper_trader.open_position_from_signal(sig_s7, lots=2)
    assert pos is not None
    assert pos.status == "OPEN"
    assert pos.lots == 2

    # Spot moves to Target 1 (24850.0 >= 24845.0)
    paper_trader.update_market_prices(
        price_map={"NIFTY 50": 24850.0},
        option_price_map={pos.id: 145.0},
        option_bid_map={pos.id: 144.5},
    )
    assert pos.status == "TARGET_1"
    assert pos.lots == 1
    assert pos.booked_lots == 1
    assert pos.underlying_sl == 24800.0  # Trailed to entry
    assert pos.option_sl == 120.0  # Trailed to entry

    # Spot moves to Target 2 (24880.0 >= 24875.0)
    paper_trader.update_market_prices(
        price_map={"NIFTY 50": 24880.0},
        option_price_map={pos.id: 161.0},
        option_bid_map={pos.id: 160.0},
    )
    assert pos.status == "TARGET_2"
    assert len(paper_trader.get_portfolio().active_positions) == 0
    assert len(paper_trader.get_portfolio().closed_trades) == 1
    closed = paper_trader.get_portfolio().closed_trades[0]
    assert closed.gross_pnl > 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)


@pytest.mark.asyncio
async def test_scanner_worker_enrichment_uses_itm_1_for_snapback():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)

    sig_trend = Signal(
        id="SIG_TREND_1",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE,
        option_type="CE",
        timestamp="10:00:00",
        entry_price=25000.0,
        stop_loss=24950.0,
        target_1=25075.0,
        target_2=25125.0,
        strike_recommendation=OptionStrikeRecommendation(
            symbol="NIFTY 50",
            underlying_price=25000.0,
            option_type="CE",
            atm_strike=25000,
            recommended_strike=24950,
            strike_symbol="NIFTY 24950 CE",
            lot_size=65,
            risk=50.0,
            stop_loss=24950.0,
            target_1=25075.0,
            target_2=25125.0,
            estimated_option_entry=100.0,
            option_sl_pts=25.0,
            option_target_1_pts=37.5,
            option_target_2_pts=62.5,
            option_sl_price=75.0,
            option_target_1_price=137.5,
            option_target_2_price=162.5,
        ),
        indicators_snapshot={},
        rationale="Setup 1 Squeeze",
    )

    sig_snap = Signal(
        id="SIG_SNAP_6",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_6_PINBAR_SNAPBACK,
        option_type="PE",
        timestamp="10:00:00",
        entry_price=25000.0,
        stop_loss=25040.0,
        target_1=24940.0,
        target_2=24900.0,
        strike_recommendation=OptionStrikeRecommendation(
            symbol="NIFTY 50",
            underlying_price=25000.0,
            option_type="PE",
            atm_strike=25000,
            recommended_strike=25050,
            strike_symbol="NIFTY 25050 PE",
            lot_size=65,
            risk=40.0,
            stop_loss=25040.0,
            target_1=24940.0,
            target_2=24900.0,
            estimated_option_entry=100.0,
            option_sl_pts=20.0,
            option_target_1_pts=30.0,
            option_target_2_pts=50.0,
            option_sl_price=80.0,
            option_target_1_price=130.0,
            option_target_2_price=150.0,
        ),
        indicators_snapshot={},
        rationale="Setup 6 Snapback",
    )

    fake_oc = {
        "24950": {
            "ce": {
                "last_price": 120.0,
                "top_ask_price": 121.0,
                "top_bid_price": 119.0,
                "security_id": 111,
            }
        },
        "25050": {
            "pe": {
                "last_price": 110.0,
                "top_ask_price": 111.0,
                "top_bid_price": 109.0,
                "security_id": 222,
            }
        },
    }

    calls = []

    def fake_resolve(*args, **kwargs):
        calls.append(kwargs)
        return MagicMock()

    # Create dummy indicators dataframe
    df_ind = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp.now()],
            "close": [25000.0],
            "open": [24980.0],
            "bandwidth": [6.0],
            "bandwidth_20_min": [5.0],
            "percent_b": [0.5],
            "vwap": [25000.0],
            "rsi": [50.0],
            "adx": [20.0],
        }
    )

    worker._session_credentials = ("CID", "TOK")
    with patch("app.services.scanner_worker.resolve_live_strike_from_chain", side_effect=fake_resolve):
        with patch.object(worker, "get_or_fetch_option_chain", AsyncMock(return_value=("2026-10-15", fake_oc))):
            with patch("app.services.scanner_worker.evaluate_signals", return_value=[sig_trend, sig_snap]):
                with patch("app.services.scanner_worker.calculate_indicators", return_value=df_ind):
                    with patch.object(worker, "get_or_update_live_candles", return_value=df_ind):
                        with patch.object(
                            worker.momentum_ranker,
                            "rank_stocks",
                            return_value=MagicMock(top_bullish=[], top_bearish=[], get_bias=lambda s: "NEUTRAL"),
                        ):
                            with patch.object(paper_trader, "update_market_prices"):
                                with patch.object(paper_trader, "on_signals_cycle"):
                                    with patch.object(worker.dhan_client, "fetch_marketfeed_quotes", AsyncMock(return_value={"NSE_EQ": {"13": {"last_price": 25000.0}}})):
                                        await worker._execute_scan_cycle(client_id="CID", access_token="TOK")

    assert len(calls) >= 2
    # Find call for sig_trend (Setup 1)
    trend_calls = [c for c in calls if c.get("symbol") == "NIFTY 50" and c.get("option_type") == "CE"]
    assert len(trend_calls) >= 1
    trend_call = trend_calls[0]
    assert trend_call.get("strike_preference") == "DEFAULT"

    # Find call for sig_snap (Setup 6)
    snap_calls = [c for c in calls if c.get("symbol") == "NIFTY 50" and c.get("option_type") == "PE"]
    assert len(snap_calls) >= 1
    snap_call = snap_calls[0]
    assert snap_call.get("strike_preference") == "ITM_1"
    assert snap_call.get("target_1") == 24940.0
    assert snap_call.get("target_2") == 24900.0
