from datetime import datetime

import pytest
from starlette.testclient import TestClient

from app.services import market_hours
from app.services.paper_trader import PaperTradingEngine
from app.services.performance_report import build_report
from tests.test_paper_reentry_gate import make_test_signal

IST = market_hours.IST
MORNING = datetime(2026, 10, 14, 10, 30, tzinfo=IST)


@pytest.fixture(autouse=True)
def _clock():
    with market_hours.override_clock(MORNING):
        yield


def _engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "t.db"))


def _trade(e, sig_id, symbol="FINNIFTY", points=0.0, **kw):
    pos = e.open_position_from_signal(make_test_signal(sig_id, symbol=symbol, **kw))
    if pos is not None and points is not None:
        e.close_position(pos.id, reason="x", exit_price=pos.option_entry + points)
    return pos


# ---------------------------------------------------------------- RMS caps are dynamic
def test_max_lots_per_trade_caps_entry_and_changes_live(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("default_lots", 6)
    e.runtime.set("max_risk_per_trade", 1_000_000)
    e.runtime.set("max_lots_per_trade", 3)
    p = e.open_position_from_signal(make_test_signal("A"))
    assert p.lots == 3
    e.runtime.set("max_lots_per_trade", 5)
    p2 = e.open_position_from_signal(make_test_signal("B", symbol="NIFTY"))
    assert p2.lots == 5
    e.runtime.set("max_lots_per_trade", 0)  # disabled
    p3 = e.open_position_from_signal(make_test_signal("C", symbol="BANKNIFTY"))
    assert p3.lots == 6


def test_max_open_positions_follows_the_setting(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("max_open_positions", 1)
    assert _trade(e, "A", points=None) is not None
    assert e.open_position_from_signal(make_test_signal("B", symbol="NIFTY")) is None
    e.runtime.set("max_open_positions", 2)
    assert e.open_position_from_signal(make_test_signal("C", symbol="BANKNIFTY")) is not None


def test_max_entries_per_day_across_symbols(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("reentry_cooldown_seconds", 0)
    e.runtime.set("max_entries_per_day", 2)
    assert _trade(e, "A", "FINNIFTY") is not None
    assert _trade(e, "B", "NIFTY") is not None
    assert _trade(e, "C", "BANKNIFTY") is None
    assert "max entries per day" in " ".join(
        d["metrics"]["detail"] for d in e.telemetry.decisions(decision="SKIPPED"))


def test_consecutive_loss_pause(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("daily_loss_limit", 0)
    e.runtime.set("reentry_cooldown_seconds", 0)
    e.runtime.set("max_consecutive_losses", 2)
    _trade(e, "A", "FINNIFTY", points=-5)
    assert e.consecutive_losses_today("demo") == 1
    _trade(e, "B", "NIFTY", points=-5)
    assert e.consecutive_losses_today("demo") == 2
    assert e.open_position_from_signal(make_test_signal("C", symbol="BANKNIFTY")) is None
    assert "consecutive losses" in e.risk_block_reason("demo")
    e.runtime.set("max_consecutive_losses", 0)
    assert e.risk_block_reason("demo") is None


# ---------------------------------------------------------------- telemetry
def test_entry_and_exit_decisions_are_recorded(tmp_path):
    e = _engine(tmp_path)
    pos = _trade(e, "A", points=10)
    dec = {d["decision"]: d for d in e.telemetry.decisions()}
    assert dec["ENTERED"]["position_id"] == pos.id
    assert dec["ENTERED"]["metrics"]["lots"] == pos.lots
    assert dec["EXITED"]["metrics"]["net_pnl"] == e.get_portfolio().closed_trades[0].net_pnl


def test_skip_reason_codes_and_insights(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("max_open_positions", 1)
    _trade(e, "A", points=None)
    e.open_position_from_signal(make_test_signal("B", symbol="NIFTY"))
    ins = e.telemetry.insights(24)
    assert ins["decisions"]["ENTERED"] == 1 and ins["decisions"]["SKIPPED"] == 1
    assert ins["top_skip_reasons"][0]["reason"] == "MAX_OPEN_POSITIONS"


def test_skip_logging_and_master_switch_can_be_turned_off(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("max_open_positions", 1)
    _trade(e, "A", points=None)
    e.runtime.set("telemetry_skip_logging", False)
    e.open_position_from_signal(make_test_signal("B", symbol="NIFTY"))
    assert e.telemetry.decisions(decision="SKIPPED") == []
    e.runtime.set("telemetry_enabled", False)
    e.runtime.set("max_open_positions", 5)
    _trade(e, "C", "BANKNIFTY", points=3)
    assert len(e.telemetry.decisions()) == 1  # only the first entry from before the switch


def test_mfe_mae_follow_the_trade(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("telemetry_excursion_flush_seconds", 1)
    pos = e.open_position_from_signal(make_test_signal("A"))
    entry, qty = pos.option_entry, pos.quantity
    for px in (entry + 4, entry - 3, entry + 1):
        pos.current_option_price = px
        pos.pnl_points = round(px - entry, 2)
        e.telemetry.track(pos)
    e.close_position(pos.id, reason="x", exit_price=entry + 1)
    row = e.telemetry.excursions()[0]
    assert row["closed"] == 1
    assert row["mfe"] == pytest.approx(4 * qty, abs=1)
    assert row["mae"] == pytest.approx(-3 * qty, abs=1)


def test_jsonl_mirror_respects_setting(tmp_path):
    e = _engine(tmp_path)
    _trade(e, "A", points=1)
    f = tmp_path / "logs" / "strategy_decisions.jsonl"
    assert f.exists() and f.read_text().count("\n") == 2
    e.runtime.set("telemetry_jsonl_enabled", False)
    _trade(e, "B", "NIFTY", points=1)
    assert f.read_text().count("\n") == 2


def test_error_handler_classifies_and_dedupes(tmp_path):
    import logging
    from app.services.telemetry import TelemetryLogHandler
    e = _engine(tmp_path)
    h = TelemetryLogHandler(e.telemetry)
    lg = logging.getLogger("app.services.scanner_worker")
    rec = lg.makeRecord(lg.name, logging.WARNING, "x.py", 1, "DATA_QUALITY entry_blocked symbol=X", (), None)
    h.emit(rec)
    h.emit(rec)
    rec2 = lg.makeRecord(lg.name, logging.ERROR, "x.py", 1, "Dhan rate limit (429) hit", (), None)
    h.emit(rec2)
    codes = sorted(r["code"] for r in e.telemetry.errors())
    assert codes == ["DATA_QUALITY_ENTRY_BLOCKED", "RATE_LIMIT"]


def test_purge_honours_retention(tmp_path):
    e = _engine(tmp_path)
    _trade(e, "A", points=1)
    e.runtime.set("telemetry_retention_days", 1)
    with market_hours.override_clock(datetime(2026, 11, 20, 10, 0, tzinfo=IST)):
        res = e.telemetry.purge()
    assert res["decisions"] == 2
    assert e.telemetry.decisions(hours=24 * 400) == []


# ---------------------------------------------------------------- performance report
def test_performance_report_numbers(tmp_path):
    e = _engine(tmp_path)
    e.runtime.set("reentry_cooldown_seconds", 0)
    e.runtime.set("daily_loss_limit", 0)
    _trade(e, "A", "FINNIFTY", points=10)
    _trade(e, "B", "NIFTY", points=-4)
    _trade(e, "C", "BANKNIFTY", points=6)
    rep = build_report(e.get_portfolio().closed_trades, e.telemetry.excursions(), book="demo")
    o = rep["overall"]
    assert o["trades"] == 3 and o["wins"] == 2 and o["losses"] == 1
    assert o["net_pnl"] == pytest.approx(sum(p.net_pnl for p in e.get_portfolio().closed_trades), abs=0.01)
    assert o["profit_factor"] > 1 and o["max_consecutive_losses"] == 1
    assert rep["by_setup"][0]["trades"] == 3 and len(rep["equity_curve"]) == 3


def test_api_endpoints_respond():
    from app.main import app
    client = TestClient(app)
    assert "decisions" in client.get("/api/telemetry/insights?hours=1").json()
    assert isinstance(client.get("/api/telemetry/decisions").json(), list)
    assert isinstance(client.get("/api/telemetry/errors").json(), list)
    assert isinstance(client.get("/api/telemetry/excursions").json(), list)
    assert "overall" in client.get("/api/telemetry/performance?mode=all").json()
    assert client.get("/api/telemetry/insights?hours=0").status_code == 422
