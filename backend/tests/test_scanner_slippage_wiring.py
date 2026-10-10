import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import UniverseManager
from app.services.paper_trader import paper_trader
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation
from fastapi.testclient import TestClient
from app.main import app

def make_test_signal(
    signal_id: str = "SIG_WS_SLIP_1",
    symbol: str = "NIFTY 50",
    sec_id: str = "44608",
    opt_entry: float = 150.0,
    opt_sl: float = 130.0,
    opt_t2: float = 190.0,
) -> Signal:
    rec = OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=22500.0,
        option_type="CE",
        atm_strike=22500,
        recommended_strike=22450,
        strike_symbol=f"{symbol} 22450 CE",
        lot_size=65,
        risk=30.0,
        stop_loss=22470.0,
        target_1=22545.0,
        target_2=22575.0,
        estimated_option_entry=opt_entry,
        option_sl_pts=20.0,
        option_target_1_pts=25.0,
        option_target_2_pts=40.0,
        option_sl_price=opt_sl,
        option_target_1_price=175.0,
        option_target_2_price=opt_t2,
        option_security_id=sec_id,
        real_ask_price=opt_entry + 1.0,
        real_bid_price=opt_entry - 0.5,
        real_ltp=opt_entry,
        is_live_quote=True,
    )
    return Signal(
        id=signal_id,
        symbol=symbol,
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
            "bandwidth": 3.5,
            "percent_b": 0.75,
            "vwap": 22490.0,
            "rsi": 62.0,
        },
        rationale="Test signal for slippage wiring",
    )

@pytest.fixture(autouse=True)
def clean_paper_trader():
    paper_trader.reset()
    yield
    paper_trader.reset()

@pytest.mark.asyncio
async def test_scanner_worker_ws_tick_passes_bid_and_computes_slippage():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)
    assert hasattr(worker, "run_single_scan_cycle")

    # 1. Open live paper position
    sig = make_test_signal(signal_id="SIG_WS_TICK_01", sec_id="44608", opt_entry=150.0, opt_t2=190.0)
    pos = paper_trader.open_position_from_signal(sig, feed_mode="live")
    assert pos is not None
    assert pos.option_security_id == "44608"

    # 2. Dispatch live option tick hitting Target 2 with bid price providing exit slippage
    # Theoretical exit = 190.0, LTP = 192.0, Bid = 188.5 -> slippage = 1.5 pts
    tick = {
        "response_code": 2,
        "security_id": 44608,
        "ltp": 192.0,
        "bid_price": 188.5,
        "exchange_segment": 2,
        "volume": 12000,
    }

    await worker._handle_incoming_ws_tick(tick)

    # 3. Verify position closed with accurate exit slippage and charges
    portfolio = paper_trader.get_portfolio(mode="live")
    assert len(portfolio.active_positions) == 0
    assert len(portfolio.closed_trades) == 1

    closed = portfolio.closed_trades[0]
    assert closed.status == "TARGET_2"
    assert closed.theoretical_exit == 190.0
    assert closed.current_option_price == 188.5
    assert closed.exit_slippage == 1.5
    assert closed.total_slippage_cost > 0
    assert closed.gross_pnl > 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)

    # 4. Verify worker state paper_portfolio is synced
    worker_port = worker._state.paper_portfolio
    assert len(worker_port.closed_trades) == 1
    assert worker_port.total_charges > 0
    assert worker_port.total_net_pnl == closed.net_pnl

@pytest.mark.asyncio
async def test_scanner_worker_ws_tick_bid_fallback_and_stop_loss():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)

    sig = make_test_signal(signal_id="SIG_WS_SL_01", sec_id="55123", opt_entry=150.0, opt_sl=130.0)
    pos = paper_trader.open_position_from_signal(sig, feed_mode="live")
    assert pos is not None

    # Tick drops below SL (130.0) with "bid" fallback key
    # Theoretical exit = 130.0, LTP = 128.0, Bid = 127.0 -> exit slippage = 3.0 pts
    tick = {
        "response_code": 2,
        "security_id": 55123,
        "ltp": 128.0,
        "bid": 127.0,
        "exchange_segment": 2,
    }

    await worker._handle_incoming_ws_tick(tick)

    portfolio = paper_trader.get_portfolio(mode="live")
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status == "STOPPED_OUT"
    assert closed.theoretical_exit == 130.0
    assert closed.current_option_price == 127.0
    assert closed.exit_slippage == 3.0
    assert closed.gross_pnl < 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)

@pytest.mark.asyncio
async def test_scanner_scan_cycle_builds_option_bid_map():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)

    # Mock dhan_client marketfeed quotes with NSE_FNO quotes containing top_bid_price
    mock_quotes = {
        "NSE_FNO": {
            "44608": {
                "last_price": 175.0,
                "top_bid_price": 174.2,
                "top_ask_price": 175.5,
            },
            "44609": {
                "last_price": 95.0,
                "bid": 94.5,
            }
        },
        "NSE_EQ": {
            "1333": {"last_price": 22500.0}
        }
    }
    worker.dhan_client.fetch_marketfeed_quotes = AsyncMock(return_value=mock_quotes)
    worker.dhan_client.fetch_expiry_list = AsyncMock(return_value=["2026-10-15"])

    # Mock option chain containing strike bids
    mock_oc = {
        "22500.0": {
            "ce": {
                "security_id": 44610,
                "last_price": 180.0,
                "top_bid_price": 179.0,
                "top_ask_price": 180.5,
            },
            "pe": {
                "security_id": 44611,
                "last_price": 90.0,
                "top_bid_price": 89.2,
                "top_ask_price": 90.5,
            }
        }
    }
    worker.dhan_client.fetch_option_chain = AsyncMock(return_value=mock_oc)

    with patch.object(paper_trader, "update_market_prices", wraps=paper_trader.update_market_prices) as mock_update:
        await worker._execute_scan_cycle(client_id="TEST_CID", access_token="TEST_TOK")

        assert mock_update.called
        # Check call arguments of update_market_prices
        called_args, called_kwargs = mock_update.call_args
        passed_bid_map = called_kwargs.get("option_bid_map")
        assert passed_bid_map is not None
        assert "44608" in passed_bid_map
        assert passed_bid_map["44608"] == 174.2
        assert "44609" in passed_bid_map
        assert passed_bid_map["44609"] == 94.5
        assert "44610" in passed_bid_map
        assert passed_bid_map["44610"] == 179.0
        assert "44611" in passed_bid_map
        assert passed_bid_map["44611"] == 89.2

def test_api_manual_close_with_bid_and_charges():
    client = TestClient(app)
    client.post("/api/paper/reset")

    sig = make_test_signal(signal_id="SIG_MANUAL_01", sec_id="66123", opt_entry=150.0)
    trade_res = client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    assert trade_res.status_code == 200
    pos_id = trade_res.json()["id"]

    # Manual close with real bid price passed in request
    close_res = client.post(
        f"/api/paper/close/{pos_id}",
        json={
            "reason": "Manual Close Test",
            "exit_price": 155.0,
            "real_bid_price": 153.5,
        }
    )
    assert close_res.status_code == 200
    data = close_res.json()
    assert data["status"] == "CLOSED"
    assert data["exit_reason"] == "Manual Close Test"
    assert data["theoretical_exit"] == 155.0
    assert data["current_option_price"] == 153.5
    assert data["exit_slippage"] == 1.5
    assert data["total_charges"] > 0
    assert data["net_pnl"] == round(data["gross_pnl"] - data["total_charges"], 2)

def test_api_manual_close_backward_compatibility_no_body():
    client = TestClient(app)
    client.post("/api/paper/reset")

    sig = make_test_signal(signal_id="SIG_NO_BODY_01", sec_id="66124", opt_entry=150.0)
    trade_res = client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    assert trade_res.status_code == 200
    pos_id = trade_res.json()["id"]

    # Close with NO body at all (legacy behavior)
    close_res = client.post(f"/api/paper/close/{pos_id}")
    assert close_res.status_code == 200
    data = close_res.json()
    assert data["status"] == "CLOSED"
    assert data["exit_reason"].startswith("Manual User Exit")
    assert data["exit_slippage"] == 0.0

def test_api_signals_close_alias():
    client = TestClient(app)
    client.post("/api/paper/reset")

    sig = make_test_signal(signal_id="SIG_ALIAS_01", sec_id="66125", opt_entry=150.0)
    trade_res = client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    assert trade_res.status_code == 200
    pos_id = trade_res.json()["id"]

    close_res = client.post(
        f"/api/signals/close/{pos_id}",
        json={"reason": "Signals API Exit", "real_bid_price": 149.0}
    )
    assert close_res.status_code == 200
    data = close_res.json()
    assert data["status"] == "CLOSED"
    assert data["exit_reason"] == "Signals API Exit"
    assert data["current_option_price"] == 149.0

def test_api_signals_close_alias_no_body():
    client = TestClient(app)
    client.post("/api/paper/reset")

    sig = make_test_signal(signal_id="SIG_ALIAS_02", sec_id="66126", opt_entry=150.0)
    trade_res = client.post("/api/paper/trade", json={"signal": sig.model_dump(), "lots": 1})
    assert trade_res.status_code == 200
    pos_id = trade_res.json()["id"]

    close_res = client.post(f"/api/signals/close/{pos_id}")
    assert close_res.status_code == 200
    data = close_res.json()
    assert data["status"] == "CLOSED"
    assert data["exit_reason"].startswith("Manual User Exit")


@pytest.mark.asyncio
async def test_scanner_worker_ws_tick_zero_or_invalid_bid_ignored():
    universe_mgr = UniverseManager()
    worker = ScannerWorker(universe_mgr=universe_mgr)

    sig = make_test_signal(signal_id="SIG_ZERO_BID_01", sec_id="77123", opt_entry=150.0, opt_t2=190.0)
    pos = paper_trader.open_position_from_signal(sig, feed_mode="live")
    assert pos is not None

    # Tick with 0 or negative bid_price
    tick = {
        "response_code": 2,
        "security_id": 77123,
        "ltp": 192.0,
        "bid_price": 0.0,
        "exchange_segment": 2,
    }

    await worker._handle_incoming_ws_tick(tick)

    portfolio = paper_trader.get_portfolio(mode="live")
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    # Without valid bid price, fallback to theoretical target fill
    assert closed.status == "TARGET_2"
    assert closed.theoretical_exit == 190.0


def test_api_signals_state_alias():
    client = TestClient(app)
    resp = client.get("/api/signals/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "paper_portfolio" in data

