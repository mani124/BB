import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_trader import paper_trader, PaperPosition

client = TestClient(app)


def _closed(pid, day="2026-10-15", net=500.0, **kw) -> PaperPosition:
    d = dict(
        id=pid, signal_id="s-" + pid, symbol="NIFTY 50", option_type="CE", strike_symbol="NIFTY 25000 CE",
        timeframe="5m", setup_type="Setup 2: Walking the Bands (9 EMA)", entry_time="10:00:00",
        underlying_entry=25000, underlying_sl=24950, underlying_target_1=25050, underlying_target_2=25100,
        option_entry=120, option_sl=100, option_target_1=140, option_target_2=160, lot_size=50, lots=1,
        quantity=50, current_underlying=25010, current_option_price=125, pnl_points=5, pnl_rupees=net + 40,
        status="CLOSED", exit_time="11:30:00", exit_reason="Target 1", gross_pnl=net + 40, total_charges=40.0,
        net_pnl=net, feed_mode="demo", entry_datetime=f"{day}T10:00:00+05:30", exit_datetime=f"{day}T11:30:00+05:30",
    )
    d.update(kw)
    return PaperPosition(**d)


@pytest.fixture(autouse=True)
def book(monkeypatch):
    trades = [
        _closed("j1", net=500.0),
        _closed("j2", net=-200.0, strike_symbol="NIFTY 25100 PE", option_type="PE"),
        _closed("j3", net=100.0, quarantine_reason="bad data"),
        _closed("j4", day="2026-10-14", net=900.0),
        _closed("j5", net=50.0, feed_mode="live"),
    ]
    monkeypatch.setattr(paper_trader._portfolio, "closed_trades", trades)
    yield


Q = {"start": "2026-10-15", "mode": "demo"}


def test_save_and_list_note_and_tag():
    r = client.put("/api/journal/trades/j1", json={"note": "Waited for the retest", "tag": "disciplined"})
    assert r.status_code == 200
    rows = client.get("/api/journal/trades", params=Q).json()
    j1 = next(t for t in rows if t["id"] == "j1")
    assert j1["note"] == "Waited for the retest" and j1["tag"] == "disciplined"
    # clearing both removes the entry
    client.put("/api/journal/trades/j1", json={"note": " ", "tag": ""})
    rows = client.get("/api/journal/trades", params=Q).json()
    assert next(t for t in rows if t["id"] == "j1")["note"] == ""


def test_unknown_or_quarantined_trade_is_404_and_length_capped():
    assert client.put("/api/journal/trades/nope", json={"note": "x"}).status_code == 404
    assert client.put("/api/journal/trades/j3", json={"note": "x"}).status_code == 404
    assert client.put("/api/journal/trades/j1", json={"note": "x" * 1001}).status_code == 422


def test_mutation_needs_dashboard_key():
    r = client.put("/api/journal/trades/j1", json={"note": "x"}, headers={"X-Omit-Capability": "1"})
    assert r.status_code == 401
    assert client.get("/api/journal/export.csv", params=Q, headers={"X-Omit-Capability": "1"}).status_code == 401


def test_list_excludes_quarantined_other_days_and_other_feed():
    ids = {t["id"] for t in client.get("/api/journal/trades", params=Q).json()}
    assert ids == {"j1", "j2"}


def test_csv_range_rows_and_notes():
    client.put("/api/journal/trades/j2", json={"note": "=HYPERLINK(\"x\")", "tag": "fomo"})
    r = client.get("/api/journal/export.csv", params={"start": "2026-10-14", "end": "2026-10-15", "mode": "demo"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("date,symbol,option")
    assert len(lines) == 1 + 3  # j1, j2, j4; quarantined j3 and live j5 excluded
    assert "'=HYPERLINK" in r.text  # formula neutralised
    assert "fomo" in r.text
    client.put("/api/journal/trades/j2", json={"note": "", "tag": ""})


def test_range_validation():
    r = client.get("/api/journal/export.csv", params={"start": "2026-10-15", "end": "2026-10-14"})
    assert r.status_code == 422
    r = client.get("/api/journal/export.csv", params={"start": "2020-01-01", "end": "2026-10-14"})
    assert r.status_code == 422


def test_summary_figures():
    client.put("/api/journal/trades/j1", json={"note": "good", "tag": "a"})
    s = client.get("/api/journal/summary", params={"day": "2026-10-15", "mode": "demo"}).json()
    assert s["trades"] == 2 and s["wins"] == 1 and s["losses"] == 1
    assert s["win_rate"] == 50.0 and s["net_pnl"] == 300.0
    assert s["best"]["id"] == "j1" and s["worst"]["id"] == "j2"
    assert [n["id"] for n in s["notes"]] == ["j1"]
    client.put("/api/journal/trades/j1", json={"note": "", "tag": ""})


def test_summary_html_escapes_and_handles_empty_day():
    client.put("/api/journal/trades/j1", json={"note": "<script>alert(1)</script>", "tag": ""})
    r = client.get("/api/journal/summary.html", params={"day": "2026-10-15", "mode": "demo"})
    assert r.status_code == 200 and "<script>alert" not in r.text and "&lt;script&gt;" in r.text
    client.put("/api/journal/trades/j1", json={"note": "", "tag": ""})
    empty = client.get("/api/journal/summary.html", params={"day": "2026-01-02", "mode": "demo"})
    assert empty.status_code == 200 and "No closed trades" in empty.text
