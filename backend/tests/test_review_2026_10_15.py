"""Regression tests for the 2026-10-15 full code review (notes/full_code_review_2026-10-15.md)."""
import inspect
import os
import sqlite3
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, resolve_dashboard_capability, settings
from app.services import market_hours
from app.services.paper_storage import PaperStorage
from app.services.paper_trader import PaperTradingEngine
from app.services.strike_selector import estimate_option_entry, is_lot_size_known
from tests.test_p0_session_guard import make_signal


@pytest.fixture(autouse=True)
def _no_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)


# ------------------------------------------------------------------ C1: dashboard key

def test_public_default_key_is_never_used(tmp_path):
    cfg = Settings(DATA_DIR=str(tmp_path), DASHBOARD_CAPABILITY=Settings().DEFAULT_DASHBOARD_CAPABILITY)
    key = resolve_dashboard_capability(cfg)
    assert key and key != cfg.DEFAULT_DASHBOARD_CAPABILITY
    key_file = tmp_path / "dashboard_key"
    assert key_file.read_text().strip() == key
    assert oct(os.stat(key_file).st_mode & 0o777) == "0o600"
    # Stable across restarts
    assert resolve_dashboard_capability(Settings(DATA_DIR=str(tmp_path), DASHBOARD_CAPABILITY="")) == key


def test_env_key_wins(tmp_path):
    cfg = Settings(DATA_DIR=str(tmp_path), DASHBOARD_CAPABILITY="my-private-key")
    assert resolve_dashboard_capability(cfg) == "my-private-key"
    assert not (tmp_path / "dashboard_key").exists()


def _raw_client():
    from app.main import app
    return TestClient(app)


def test_default_key_is_rejected():
    res = _raw_client().post("/api/auth/session", json={"secret": "bb-options-local-capability"})
    assert res.status_code == 401


def test_session_cookie_is_not_the_master_key():
    c = _raw_client()
    res = c.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY})
    assert res.status_code == 200
    assert "token" not in res.json()
    cookie = c.cookies.get("dashboard_session")
    assert cookie and cookie != settings.DASHBOARD_CAPABILITY
    # The issued session cookie authorises private reads...
    assert c.get("/api/paper/portfolio", headers={"X-Omit-Capability": "1"}).status_code == 200
    # ...but the master key placed in a cookie does not.
    c2 = _raw_client()
    c2.cookies.set("dashboard_session", settings.DASHBOARD_CAPABILITY)
    assert c2.get("/api/paper/portfolio", headers={"X-Omit-Capability": "1"}).status_code == 401


def test_auth_status_and_docs_need_the_key():
    c = _raw_client()
    assert c.get("/api/auth/status", headers={"X-Omit-Capability": "1"}).status_code == 401
    assert c.get("/openapi.json", headers={"X-Omit-Capability": "1"}).status_code == 401
    assert c.get("/api/health", headers={"X-Omit-Capability": "1"}).status_code == 200


def test_cors_preflight_is_answered():
    res = _raw_client().options(
        "/api/paper/trade",
        headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "POST", "X-Omit-Capability": "1"},
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5174"


# ------------------------------------------------------------------ C2/C3: journal safety

def test_tests_never_use_the_real_database():
    real_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    assert not os.path.abspath(settings.DB_PATH).startswith(os.path.abspath(real_data_dir))


def test_reset_archives_and_backs_up_instead_of_deleting(tmp_path):
    db = str(tmp_path / "r.db")
    eng = PaperTradingEngine(db_path=db)
    assert eng.open_position_from_signal(make_signal("R_1"), feed_mode="demo") is not None
    eng.reset_sync()

    assert eng.get_portfolio().active_positions == []
    assert PaperStorage(db).load_all_positions() == ([], [])
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM positions WHERE archived_at IS NOT NULL").fetchone()[0] == 1
    backups = os.listdir(tmp_path / "backups")
    assert len(backups) == 1 and backups[0].startswith("trades-before-reset-")
    assert sqlite3.connect(str(tmp_path / "backups" / backups[0])).execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1


# ------------------------------------------------------------------ C4: no thread race

def test_mutating_paper_endpoints_run_on_the_event_loop():
    from app.api import paper, signals
    for fn in (paper.open_manual_trade, paper.close_trade, paper.update_settings, paper.reset_portfolio,
               signals.close_trade_signal):
        assert inspect.iscoroutinefunction(fn), fn.__name__


# ------------------------------------------------------------------ C5: books are separate

def test_demo_positions_do_not_count_against_live_caps(monkeypatch):
    eng = PaperTradingEngine()
    monkeypatch.setattr(settings, "MAX_OPEN_POSITIONS", 1)
    assert eng.open_position_from_signal(make_signal("D_1", symbol="IRFC"), feed_mode="demo") is not None
    live_sig = make_signal("L_1", symbol="IRFC", sec_id="55001")
    assert eng._exposure_block_reason(live_sig, feed_mode="live") is None
    assert eng._exposure_block_reason(live_sig, feed_mode="demo") is not None


# ------------------------------------------------------------------ C6: holidays fail closed

def test_unlisted_year_is_not_a_trading_day():
    assert market_hours.is_trading_day(date(2026, 10, 14))
    assert not market_hours.is_trading_day(date(2099, 1, 5))  # a Monday, but no holiday list
    assert not market_hours.is_market_open(datetime(2099, 1, 5, 11, 0, tzinfo=market_hours.IST))


def test_holiday_list_missing_soon():
    assert not market_hours.holiday_list_missing_soon(date(2026, 10, 15))
    assert market_hours.holiday_list_missing_soon(date(2026, 12, 15))


# ------------------------------------------------------------------ C7: small broadcast

def test_portfolio_summary_has_no_closed_list():
    eng = PaperTradingEngine()
    pos = eng.open_position_from_signal(make_signal("S_1"), feed_mode="demo")
    eng.close_position(pos.id, reason="test")
    summary = eng.get_portfolio_summary("demo")
    assert summary.closed_trades == [] and summary.closed_trades_count == 1
    assert len(eng.get_portfolio("demo").closed_trades) == 1  # the full view is unchanged


# ------------------------------------------------------------------ quick fixes

def test_bank_stocks_are_not_indices():
    assert estimate_option_entry("AUBANK", 700.0, 10) == round(max(5.0, 10 + 700 * 0.015), 1)
    assert estimate_option_entry("NIFTY BANK", 50000.0, 100) == round(100 + 50000 * 0.005, 1)


def test_setup5_reports_unknown_lot_size():
    import pandas as pd
    from app.services.indicators import calculate_indicators
    from app.services.option_chart_strategy import evaluate_option_chart_signal

    assert not is_lot_size_known("ZZZNOTREAL")
    ts = pd.date_range("2026-10-14 09:15", periods=30, freq="5min")
    closes = [50.0] * 29 + [60.0]
    df = pd.DataFrame({"timestamp": ts, "open": closes, "high": [c + 0.5 for c in closes],
                       "low": [c - 0.5 for c in closes], "close": closes,
                       "volume": [1000] * 29 + [5000]})
    with market_hours.override_clock(datetime(2026, 10, 14, 11, 46, tzinfo=market_hours.IST)):
        sig = evaluate_option_chart_signal(
            symbol="ZZZNOTREAL", strike_symbol="ZZZNOTREAL 100 CE", option_type="CE",
            option_df=calculate_indicators(df), underlying_price=100.0, strike_price=100.0,
            lot_size=100, option_security_id="1",
        )
    assert sig is not None
    assert sig.strike_recommendation.lot_size_known is False
