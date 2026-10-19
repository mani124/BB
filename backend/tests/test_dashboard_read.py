from types import SimpleNamespace


def test_trades_include_each_book_once_and_keep_legacy_rows(monkeypatch):
    from app.services import dashboard_read

    paper = SimpleNamespace(
        active_positions=[SimpleNamespace(
            id="p-open", setup_type="Setup 16: Option Squeeze Breakout", symbol="NIFTY",
            strike_symbol="NIFTY CE", status="OPEN", entry_datetime="2026-10-19T09:30:00+05:30",
            exit_datetime=None, feed_mode="demo", est_net_pnl=120.0, net_pnl=0.0,
        )],
        closed_trades=[SimpleNamespace(
            id="p-old", setup_type="Setup 1", symbol="BANKNIFTY", strike_symbol="BANKNIFTY PE",
            status="CLOSED", entry_datetime=None, entry_time="10:05", exit_datetime=None,
            exit_time="10:20", feed_mode="demo", net_pnl=-45.0,
        )],
    )
    monkeypatch.setattr(dashboard_read.paper_trader, "get_portfolio", lambda _mode: paper)
    monkeypatch.setattr(dashboard_read, "get_cx_engine", lambda: SimpleNamespace(positions=lambda: [
        {"id": "cx-1", "symbol": "CRUDEOIL", "setup": "Setup 17", "status": "CLOSED",
         "opened_at": "2026-10-19T10:00:00+05:30", "closed_at": "2026-10-19T11:00:00+05:30", "net_pnl": 25.0},
    ]))
    monkeypatch.setattr(dashboard_read, "get_earnings_engine", lambda: SimpleNamespace(positions=lambda: [
        {"id": "earn-1", "symbol": "INFY", "mode": "MODE_A", "status": "OPEN",
         "opened_at": "2026-10-19T10:30:00+05:30", "unrealized_net": 12.0,
         "legs": [{"opt": "CE", "strike": 1500}]},
    ]))

    rows = dashboard_read.list_dashboard_trades()

    assert len(rows) == 4
    assert len({row["id"] for row in rows}) == 4
    assert rows[0]["id"] == "earnings:earn-1"
    assert next(row for row in rows if row["id"] == "paper:p-open")["display_book"] == "Setup 16"
    assert next(row for row in rows if row["id"] == "paper:p-open")["net_kind"] == "estimated"
    assert next(row for row in rows if row["id"] == "cx:cx-1")["net_kind"] == "realized"
    old = next(row for row in rows if row["id"] == "paper:p-old")
    assert old["opened_at"] is None
    assert old["evidence_state"] == "unavailable"


def test_trade_filters_match_book_status_and_entry_day(monkeypatch):
    from app.services import dashboard_read

    rows = [
        {"id": "paper:1", "book": "paper", "status": "OPEN", "opened_at": "2026-10-19T09:00:00+05:30"},
        {"id": "cx:2", "book": "cx", "status": "CLOSED", "opened_at": "2026-10-18T20:00:00+05:30"},
    ]
    monkeypatch.setattr(dashboard_read, "_all_trade_rows", lambda: rows)
    assert [r["id"] for r in dashboard_read.list_dashboard_trades(book="paper", status="OPEN", day="2026-10-19")] == ["paper:1"]
