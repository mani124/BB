import sqlite3


def _reject_evidence_inserts(path):
    from app.services.dashboard_evidence import save_trade_evidence

    save_trade_evidence("paper", "seed", {"reason": "seed"}, {}, db_path=str(path))
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TRIGGER reject_evidence BEFORE INSERT ON dashboard_trade_evidence
            BEGIN SELECT RAISE(ABORT, 'evidence unavailable'); END""")


def test_evidence_survives_new_reader_and_isolated_by_book(tmp_path, monkeypatch):
    from app.services import dashboard_evidence

    path = str(tmp_path / "trades.db")
    monkeypatch.setattr(dashboard_evidence, "_db_path", lambda _book: path)
    dashboard_evidence.save_trade_evidence(
        "paper", "same-id", {"reason": "SIGNAL_CONFIRMED", "checks": {"rsi": 60}},
        {"option": [
            {"time": 20, "open": 101, "high": 103, "low": 100, "close": 102},
            {"time": 10, "open": 99, "high": 102, "low": 98, "close": 101},
        ]},
    )
    dashboard_evidence.save_trade_evidence("cx", "same-id", {"reason": "SETUP_17"}, {})

    assert dashboard_evidence.get_trade_evidence("paper", "same-id")["decision"]["checks"]["rsi"] == 60
    assert [bar["time"] for bar in dashboard_evidence.get_trade_evidence("paper", "same-id")["bars"]["option"]] == [10, 20]
    assert dashboard_evidence.get_trade_evidence("cx", "same-id")["decision"]["reason"] == "SETUP_17"
    assert dashboard_evidence.get_trade_evidence("earnings", "same-id") is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM dashboard_trade_evidence").fetchone()[0] == 2


def test_old_trade_detail_and_chart_admit_missing_evidence(monkeypatch):
    from app.api import dashboard

    trade = {"id": "cx:old", "book": "cx", "source_id": "old", "status": "CLOSED", "instrument": "CRUDEOIL"}
    monkeypatch.setattr(dashboard, "list_dashboard_trades", lambda **_filters: [trade])
    monkeypatch.setattr(dashboard, "get_trade_evidence", lambda _book, _id: None)

    detail = dashboard.trade_detail("cx", "old")
    chart = dashboard.trade_chart("cx", "old")
    assert detail["reason_state"] == "unavailable"
    assert chart["candle_state"] == "unavailable"
    assert chart["series"] == []


def test_paper_entry_records_original_signal_reason(tmp_path, monkeypatch):
    from app.services import dashboard_evidence
    from app.services.paper_trader import PaperTradingEngine
    from test_paper_trader import create_mock_signal

    engine = PaperTradingEngine(str(tmp_path / "paper.db"))
    position = engine.open_position_from_signal(create_mock_signal(), lots=1)

    assert position is not None
    monkeypatch.setattr(dashboard_evidence, "_db_path", lambda _book: engine.storage.db_path)
    assert dashboard_evidence.get_trade_evidence("paper", position.id)["decision"]["rationale"] == "Test"


def test_paper_entry_rolls_back_position_and_signal_when_evidence_fails(tmp_path):
    from app.services.paper_trader import PaperTradingEngine
    from test_paper_trader import create_mock_signal

    path = tmp_path / "paper.db"
    engine = PaperTradingEngine(str(path))
    _reject_evidence_inserts(path)
    called = []
    engine.on_live_entry = lambda *_args: called.append("routed")

    assert engine.open_position_from_signal(create_mock_signal(), lots=1) is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM processed_signals").fetchone()[0] == 0
    assert called == []


def test_two_paper_engines_cannot_route_the_same_signal_twice(tmp_path):
    from app.services.paper_trader import PaperTradingEngine
    from test_paper_trader import create_mock_signal

    path = tmp_path / "paper.db"
    first = PaperTradingEngine(str(path))
    second = PaperTradingEngine(str(path))  # loaded before the first entry
    routed = []
    first.on_live_entry = lambda *_args: routed.append("first")
    second.on_live_entry = lambda *_args: routed.append("second")

    assert first.open_position_from_signal(create_mock_signal(), lots=1) is not None
    assert second.open_position_from_signal(create_mock_signal(), lots=1) is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM processed_signals").fetchone()[0] == 1
    assert routed == ["first"]


def test_cx_entry_rolls_back_position_when_evidence_fails(tmp_path, monkeypatch):
    from app.services import market_hours
    from app.services.cx_signals import SETUP_17
    from test_cx_book import make, force_signal, run, NOW

    force_signal(monkeypatch)
    engine = make(tmp_path)
    _reject_evidence_inserts(engine.store.db_path)
    with market_hours.override_clock(NOW):
        run(engine, NOW)
    with sqlite3.connect(engine.store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cx_positions").fetchone()[0] == 0
    marker = f"last_bar:CRUDEOIL:{SETUP_17}"
    assert engine.store.get_meta(marker) is None
    with sqlite3.connect(engine.store.db_path) as conn:
        conn.execute("DROP TRIGGER reject_evidence")
    with market_hours.override_clock(NOW):
        run(engine, NOW)
    assert len(engine.positions("OPEN")) == 1


def test_earnings_entry_rolls_back_position_when_evidence_fails(tmp_path):
    from test_earnings import make_engine, add_a_candidate, run, NOW

    engine = make_engine(tmp_path)
    add_a_candidate(engine)
    _reject_evidence_inserts(engine.store.db_path)
    run(engine.run_cycle(NOW))
    with sqlite3.connect(engine.store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM earnings_positions").fetchone()[0] == 0


def test_cx_entry_keeps_recorded_underlying_candles(tmp_path, monkeypatch):
    from app.services import dashboard_evidence, market_hours
    from test_cx_book import make, force_signal, run, NOW

    force_signal(monkeypatch)
    engine = make(tmp_path)
    with market_hours.override_clock(NOW):
        run(engine, NOW)
    position = engine.positions("OPEN")[0]
    monkeypatch.setattr(dashboard_evidence, "_db_path", lambda _book: engine.store.db_path)
    evidence = dashboard_evidence.get_trade_evidence("cx", position["id"])
    assert evidence["decision"]["checks"]["adx"] == 30.0
    assert len(evidence["bars"]["underlying"]) > 0


def test_earnings_entry_keeps_each_actual_leg(tmp_path, monkeypatch):
    from app.services import dashboard_evidence
    from test_earnings import make_engine, add_a_candidate, run, NOW

    engine = make_engine(tmp_path)
    add_a_candidate(engine)
    run(engine.run_cycle(NOW))
    position = engine.positions("OPEN")[0]
    monkeypatch.setattr(dashboard_evidence, "_db_path", lambda _book: engine.store.db_path)
    evidence = dashboard_evidence.get_trade_evidence("earnings", position["id"])
    assert len(evidence["decision"]["legs"]) == len(position["legs"])
    assert evidence["bars"] == {}


def test_cx_chart_uses_trade_times_for_entry_and_exit_markers(monkeypatch):
    from app.api import dashboard

    trade = {"id": "cx:one", "book": "cx", "source_id": "one", "status": "CLOSED",
             "opened_at": "2026-10-19T10:00:00+05:30", "closed_at": "2026-10-19T10:30:00+05:30"}
    monkeypatch.setattr(dashboard, "list_dashboard_trades", lambda **_filters: [trade])
    monkeypatch.setattr(dashboard, "get_trade_evidence", lambda _book, _id: {"decision": {}, "bars": {
        "underlying": [{"time": 1792375200, "open": 1, "high": 2, "low": 1, "close": 2}],
    }})
    chart = dashboard.trade_chart("cx", "one")
    assert chart["candle_state"] == "unavailable"
    assert chart["series"][0]["label"] == "Underlying"
    assert chart["entry_time"] is not None
    assert chart["exit_time"] > chart["entry_time"]


def test_chart_converts_ist_wall_epochs_to_real_instants(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.api import dashboard

    moment = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    fake_wall_epoch = int((moment.replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds())
    trade = {"id": "cx:one", "book": "cx", "source_id": "one", "status": "OPEN", "opened_at": moment.isoformat()}
    monkeypatch.setattr(dashboard, "list_dashboard_trades", lambda **_filters: [trade])
    monkeypatch.setattr(dashboard, "get_trade_evidence", lambda _book, _id: {"decision": {}, "bars": {
        "underlying": [{"time": fake_wall_epoch, "open": 1, "high": 2, "low": 1, "close": 2}],
    }})
    chart = dashboard.trade_chart("cx", "one")
    assert chart["entry_time"] == int(moment.timestamp())
    assert chart["series"][0]["candles"][0]["time"] == int(moment.timestamp())
