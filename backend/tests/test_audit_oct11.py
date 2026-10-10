import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_direct_client_capability_required():
    """F1: Direct client mutations (no Origin/Referer) require a valid capability token."""
    # 1. Missing capability on direct mutation -> 401
    res_no_cap = client.post("/api/paper/reset", headers={"X-Omit-Capability": "1"})
    assert res_no_cap.status_code == 401
    assert "capability required" in res_no_cap.json()["detail"].lower()

    # 2. Invalid capability token on direct mutation -> 401
    res_bad_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": "wrong-secret-token"})
    assert res_bad_cap.status_code == 401
    assert "capability" in res_bad_cap.json()["detail"].lower()

    # 3. Valid X-Dashboard-Capability header -> 200
    res_good_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY})
    assert res_good_cap.status_code == 200

    # 4. Valid Authorization Bearer header -> 200
    res_auth = client.post("/api/paper/reset", headers={"Authorization": f"Bearer {settings.DASHBOARD_CAPABILITY}"})
    assert res_auth.status_code == 200

    # 5. Browser request with valid origin does not require capability header -> 200
    res_origin = client.post("/api/paper/reset", headers={"Origin": "http://localhost:5174", "X-Omit-Capability": "1"})
    assert res_origin.status_code == 200

    # 6. Browser request with untrusted origin -> 403 Forbidden
    res_evil = client.post("/api/paper/reset", headers={"Origin": "https://evil.sslip.io", "X-Omit-Capability": "1"})
    assert res_evil.status_code == 403

    # 7. Direct GET request with no capability -> 200 (read routes not blocked)
    res_get = client.get("/api/health", headers={"X-Omit-Capability": "1"})
    assert res_get.status_code == 200


def test_server_owned_exit_pricing():
    """F2, F4: Both close routes use server-owned OptionQuote records and reject caller-supplied fill prices."""
    from datetime import datetime
    from app.services.paper_trader import paper_trader
    from app.services.strategy_engine import Signal, SetupType
    from app.services.strike_selector import OptionStrikeRecommendation
    from app.main import worker

    paper_trader.reset()
    sec_id = "99881"

    rec1 = OptionStrikeRecommendation(
        symbol="NIFTY 50", underlying_price=22500.0, option_type="CE",
        atm_strike=22500, recommended_strike=22500, strike_symbol="NIFTY 22500 CE",
        lot_size=50, risk=20.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        estimated_option_entry=100.0, option_sl_pts=20.0, option_target_1_pts=30.0, option_target_2_pts=60.0,
        option_sl_price=80.0, option_target_1_price=130.0, option_target_2_price=160.0,
        option_security_id=sec_id, is_live_quote=True, real_ask_price=100.0, real_bid_price=99.5, real_ltp=100.0
    )
    sig1 = Signal(
        id="SIG_F2_TEST_1", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec1, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )

    pos = paper_trader.open_position_from_signal(sig1, feed_mode="live")
    assert pos is not None

    # Clear quotes on worker initially
    worker._latest_option_quotes.clear()
    worker._option_last_quote_time.clear()

    # 1. Attacker submits forged bid of 10,000. Server has NO quote in store.
    # Must NOT fill at 10,000. Must be labeled "(Modeled: Unquoted)".
    res_forged = client.post(
        f"/api/paper/close/{pos.id}",
        json={"reason": "User Closed", "real_bid_price": 10000.0, "real_opt_price": 10000.0}
    )
    assert res_forged.status_code == 200
    closed_data = res_forged.json()
    assert "(Modeled: Unquoted)" in closed_data["exit_reason"]
    assert closed_data["current_option_price"] < 1000.0, "Attacker inflated fill price!"

    # 2. Test server-owned quote lookup (fresh OptionQuote)
    sig2 = Signal(
        id="SIG_F2_TEST_2", symbol="NIFTY 50", timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE, option_type="CE",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry_price=22500.0, stop_loss=22480.0, target_1=22530.0, target_2=22560.0,
        strike_recommendation=rec1, is_confirmed=True, indicators_snapshot={}, rationale="test"
    )
    pos2 = paper_trader.open_position_from_signal(sig2, feed_mode="live")
    assert pos2 is not None

    # Record legitimate server-side OptionQuote
    worker.record_option_quote(sec_id, ltp=120.0, bid=119.5, source="chain")

    res_fresh = client.post(
        f"/api/signals/close/{pos2.id}",
        json={"reason": "Manual Close"}
    )
    assert res_fresh.status_code == 200
    closed2 = res_fresh.json()
    assert "(Modeled" not in closed2["exit_reason"]
    assert closed2["current_option_price"] == 119.5
    assert closed2["exit_slippage"] == 0.5  # 120.0 theoretical - 119.5 real_bid
