from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo


def test_session_orders_cross_book_events_and_links_observation(monkeypatch):
    from app.services import dashboard_read
    monkeypatch.setattr(dashboard_read, "now_ist", lambda: datetime(2026, 10, 19, 12, tzinfo=ZoneInfo("Asia/Kolkata")))

    decisions = [
        {"id": 1, "ts": "2026-10-19 09:01:00", "book": "paper", "strategy": "Setup 5", "symbol": "NIFTY", "decision": "SKIPPED", "reason": "SPREAD", "metrics": {"spread": 9}, "position_id": None},
        {"id": 2, "ts": "2026-10-19 09:02:00", "book": "paper", "strategy": "Setup 5", "symbol": "NIFTY", "decision": "SKIPPED", "reason": "SPREAD", "metrics": {"spread": 8}, "position_id": None},
        {"id": 3, "ts": "2026-10-19 09:05:00", "book": "earnings", "strategy": "MODE_A_RUNUP", "symbol": "INFY", "decision": "ENTERED", "reason": "READY", "metrics": {}, "position_id": "c1"},
    ]
    errors = [{"id": 4, "ts": "2026-10-19 09:03:00", "code": "FEED_STALE", "component": "scanner", "severity": "ERROR", "message": "Feed stale", "payload": {}}]
    monkeypatch.setattr(dashboard_read.paper_trader.telemetry, "day_events", lambda day: {"decisions": decisions, "errors": errors})
    monkeypatch.setattr(dashboard_read.paper_trader.runtime, "audit_day", lambda day: [])
    monkeypatch.setattr(dashboard_read, "list_dashboard_trades", lambda: [
        {"id": "earnings:c1", "book": "earnings", "display_book": "Earnings", "source_id": "c1", "instrument": "INFY", "setup": "MODE_A_RUNUP", "opened_at": "2026-10-19T09:05:30+05:30", "closed_at": "2026-10-19T10:00:00+05:30", "status": "CLOSED", "net_pnl": 200, "net_kind": "realized", "evidence_state": "recorded"},
        {"id": "paper:p1", "book": "paper", "display_book": "Main scanner", "source_id": "p1", "instrument": "NIFTY CE", "setup": "Setup 5", "opened_at": "2026-10-19T09:10:00+05:30", "closed_at": None, "status": "OPEN", "net_pnl": 30, "net_kind": "estimated", "evidence_state": "unavailable"},
    ])
    result = dashboard_read.get_dashboard_session("2026-10-19")
    assert [e["type"] for e in result["events"]] == ["decision", "decision", "error", "decision", "entry", "entry", "exit"]
    assert result["events"][0]["at"].startswith("2026-10-19T09:01")
    assert result["events"][0]["evidence_state"] == "recorded"
    assert next(e for e in result["events"] if e["id"] == "entry:paper:p1")["evidence_state"] == "unavailable"
    assert result["observations"][0]["event_ids"] == ["decision:1", "decision:2"]
    assert result["by_book"][0]["realized_net"] is None
    assert result["by_book"][0]["estimated_net"] == 30
    assert result["by_book"][0]["open_positions"] == 1
    assert result["by_book"][1]["display_book"].endswith("live")
    assert result["by_book"][2]["realized_net"] == 200


def test_session_separates_paper_modes_and_excludes_quarantined_financials(monkeypatch):
    from app.services import dashboard_read
    monkeypatch.setattr(dashboard_read.paper_trader.telemetry, "day_events", lambda day: {"decisions": [], "errors": []})
    monkeypatch.setattr(dashboard_read.paper_trader.runtime, "audit_day", lambda day: [])
    monkeypatch.setattr(dashboard_read, "list_dashboard_trades", lambda: [
        {"id": f"paper:{i}", "book": "paper", "mode": mode, "instrument": "NIFTY", "status": "CLOSED",
         "opened_at": "2026-10-19T09:30:00+05:30", "closed_at": "2026-10-19T10:00:00+05:30",
         "net_kind": "realized", "net_pnl": pnl, "quarantine_reason": quarantine, "evidence_state": "unavailable"}
        for i, mode, pnl, quarantine in ((1, "demo", 10, None), (2, "live", 20, None), (3, "live", 900, "BAD_FILL"))
    ])
    result = dashboard_read.get_dashboard_session("2026-10-19")
    demo, live = result["by_book"][:2]
    assert demo["realized_net"] == 10
    assert live["realized_net"] == 20
    assert live["exits"] == 2
    assert len([event for event in result["events"] if event["type"] == "exit"]) == 3


def test_session_uses_selected_ist_day_and_does_not_invent_decisions(monkeypatch):
    from app.services import dashboard_read

    monkeypatch.setattr(dashboard_read.paper_trader.telemetry, "day_events", lambda day: {"decisions": [], "errors": []})
    monkeypatch.setattr(dashboard_read.paper_trader.runtime, "audit_day", lambda day: [])
    monkeypatch.setattr(dashboard_read, "list_dashboard_trades", lambda: [
        {"id": "paper:a", "book": "paper", "display_book": "Main scanner", "source_id": "a", "instrument": "NIFTY", "setup": "S1", "opened_at": "2026-10-18T23:59:00+05:30", "closed_at": "2026-10-19T00:01:00+05:30", "status": "CLOSED", "net_pnl": 10, "net_kind": "realized", "evidence_state": "unavailable"},
    ])
    result = dashboard_read.get_dashboard_session("2026-10-19")
    assert [e["type"] for e in result["events"]] == ["exit"]
    assert result["events"][0]["trade_id"] == "paper:a"
    assert result["observations"] == []


def test_telemetry_day_range_read_handles_historical_days(tmp_path):
    from app.services.telemetry import Telemetry
    telemetry = Telemetry(str(tmp_path / "test.db"), SimpleNamespace(get=lambda _: True))
    with telemetry._conn() as conn:
        conn.execute("INSERT INTO strategy_decisions (ts, book, strategy, symbol, decision, reason, metrics) VALUES (?,?,?,?,?,?,?)",
                     ("2026-10-18 23:59:00", "paper", "S1", "NIFTY", "SKIPPED", "OLD", "{}"))
        conn.execute("INSERT INTO strategy_decisions (ts, book, strategy, symbol, decision, reason, metrics) VALUES (?,?,?,?,?,?,?)",
                     ("2026-10-19 00:01:00", "paper", "S1", "NIFTY", "ENTERED", "NEW", '{"x":1}'))
    rows = telemetry.day_events("2026-10-19")
    assert [row["reason"] for row in rows["decisions"]] == ["NEW"]
    assert rows["decisions"][0]["metrics"] == {"x": 1}


def test_paper_telemetry_mode_links_to_paper_trade_and_old_estimate_is_not_replayed(monkeypatch):
    from app.services import dashboard_read
    monkeypatch.setattr(dashboard_read.paper_trader.telemetry, "day_events", lambda day: {"decisions": [
        {"id": 10, "ts": "2026-10-18 09:30:00", "book": "demo", "strategy": "S1", "symbol": "NIFTY", "decision": "ENTERED", "reason": "READY", "metrics": {}, "position_id": "p1"},
    ], "errors": []})
    monkeypatch.setattr(dashboard_read.paper_trader.runtime, "audit_day", lambda day: [])
    monkeypatch.setattr(dashboard_read, "list_dashboard_trades", lambda: [
        {"id": "paper:p1", "book": "paper", "display_book": "Main scanner", "source_id": "p1", "instrument": "NIFTY CE", "setup": "S1", "opened_at": "2026-10-18T09:30:00+05:30", "closed_at": None, "status": "OPEN", "net_pnl": 800, "net_kind": "estimated", "evidence_state": "recorded"},
    ])
    result = dashboard_read.get_dashboard_session("2026-10-18")
    assert result["events"][0]["trade_id"] == "paper:p1"
    assert result["by_book"][0]["estimated_net"] is None


def test_session_includes_recorded_setting_changes_and_repeated_errors(monkeypatch):
    from app.services import dashboard_read
    monkeypatch.setattr(dashboard_read.paper_trader.telemetry, "day_events", lambda day: {"decisions": [], "errors": [
        {"id": 1, "ts": "2026-10-19 09:00:00", "code": "FEED_STALE", "component": "feed", "message": "Gap", "payload": {}},
        {"id": 2, "ts": "2026-10-19 09:05:00", "code": "FEED_STALE", "component": "feed", "message": "Gap", "payload": {}},
    ]})
    monkeypatch.setattr(dashboard_read.paper_trader.runtime, "audit_day", lambda day: [
        {"id": 7, "changed_at": "2026-10-19 09:02:00", "key": "max_open_positions", "old_value": "3", "new_value": "2", "actor": "dashboard"},
    ])
    monkeypatch.setattr(dashboard_read, "list_dashboard_trades", lambda: [])
    result = dashboard_read.get_dashboard_session("2026-10-19")
    assert [event["type"] for event in result["events"]] == ["error", "control", "error"]
    assert result["events"][1]["metrics"] == {"from": "3", "to": "2", "by": "dashboard"}
    assert result["observations"][0]["event_ids"] == ["error:1", "error:2"]


def test_runtime_audit_day_reads_date_range(tmp_path):
    from app.services.runtime_settings import RuntimeSettings
    runtime = RuntimeSettings(str(tmp_path / "settings.db"))
    with runtime._conn() as conn:
        conn.execute("INSERT INTO settings_audit (changed_at, key, old_value, new_value, actor) VALUES (?,?,?,?,?)",
                     ("2026-10-18 23:59:00", "x", "1", "2", "test"))
        conn.execute("INSERT INTO settings_audit (changed_at, key, old_value, new_value, actor) VALUES (?,?,?,?,?)",
                     ("2026-10-19 00:01:00", "x", "2", "3", "test"))
    assert [row["new_value"] for row in runtime.audit_day("2026-10-19")] == ["3"]
