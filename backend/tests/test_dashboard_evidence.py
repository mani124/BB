import sqlite3


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


def test_paper_entry_records_original_signal_reason(monkeypatch, tmp_path):
    from app.services import dashboard_evidence
    from app.services.paper_trader import PaperTradingEngine
    from test_paper_trader import create_mock_signal

    captured = []
    monkeypatch.setattr(dashboard_evidence, "save_trade_evidence", lambda *args, **kwargs: captured.append((args, kwargs)))
    engine = PaperTradingEngine(str(tmp_path / "paper.db"))
    position = engine.open_position_from_signal(create_mock_signal(), lots=1)

    assert position is not None
    assert len(captured) == 1
    assert captured[0][0][0:2] == ("paper", position.id)
    assert captured[0][0][2]["rationale"] == "Test"


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
