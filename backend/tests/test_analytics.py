import json
import time
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analytics

client = TestClient(app)


def T(id="t", net=100.0, entry="2026-10-19T09:15:00+05:30", exit_="2026-10-19T09:45:00+05:30", setup="Setup 1", symbol="NIFTY", side="CE",
      feed="demo", q=None, **kw):
    d = dict(id=id, net_pnl=net, total_charges=10.0, pnl_rupees=net + 10, gross_pnl=net + 10, entry_datetime=entry, exit_datetime=exit_,
             setup_type=setup, symbol=symbol, option_type=side, feed_mode=feed, quarantine_reason=q, option_entry=100.0, option_sl=90.0,
             initial_option_sl=90.0, quantity=10, initial_quantity=10, status="CLOSED", exit_reason="STOP", entry_slippage=0.5,
             exit_slippage=0.25, total_slippage_cost=7.5, entry_spread_pct=None, option_volume=None, option_oi=None, entry_delay_s=None,
             entry_bid=None, charges_breakdown=None, booked_pnl_rupees=0.0)
    d.update(kw)
    return SimpleNamespace(**d)


def test_empty_inputs_are_json_safe():
    for out in (analytics.equity_report([]), analytics.attribution_report([], []), analytics.distribution_report([], []),
                analytics.execution_report([]), analytics.risk_snapshot([])):
        json.dumps(out, allow_nan=False)
    assert analytics.equity_report([])["summary"]["max_drawdown"] == 0


def test_equity_golden_and_drawdown():
    ts = [T("a", 100, exit_="2026-10-19T10:00:00+05:30"), T("b", -300, exit_="2026-10-19T11:00:00+05:30"),
          T("c", 50, exit_="2026-10-20T10:00:00+05:30")]
    r = analytics.equity_report(ts)
    assert [p["equity"] for p in r["points"]] == [100, -200, -150]
    assert [p["day_pnl"] for p in r["points"]] == [100, -200, 50]
    s = r["summary"]
    assert s["net"] == -150 and s["max_drawdown"] == 300 and s["current_drawdown"] == 250
    assert s["drawdowns"][0]["end"] is None and s["drawdowns"][0]["depth"] == 300


def test_all_winners_have_zero_drawdown():
    r = analytics.equity_report([T("a", 10, exit_="2026-10-19T10:00:00+05:30"), T("b", 20, exit_="2026-10-19T11:00:00+05:30")])
    assert r["summary"]["max_drawdown"] == 0 and r["summary"]["drawdowns"] == []


def test_attribution_low_sample_boundary_and_cost_drag():
    t19 = [T(f"a{i}") for i in range(19)]
    t20 = [T(f"b{i}", setup="Setup 2") for i in range(20)]
    r = analytics.attribution_report(t19 + t20, [], "setup")
    by = {b["key"]: b for b in r["buckets"]}
    assert by["Setup 1"]["low_sample"] is True and by["Setup 2"]["low_sample"] is False
    assert by["Setup 1"]["cost_drag_pct"] is not None


def test_zero_gross_has_no_cost_drag():
    t = T("z", net=-10.0, gross_pnl=0.0, pnl_rupees=0.0, total_charges=10.0)
    r = analytics.attribution_report([t], [], "setup")
    assert r["buckets"][0]["cost_drag_pct"] is None


def test_hour_and_weekday_groups_use_ist():
    t = T("h", entry="2026-10-19T03:45:00+00:00")  # 09:15 IST Monday
    assert analytics.attribution_report([t], [], "hour")["buckets"][0]["key"] == "09:00"
    assert analytics.attribution_report([t], [], "weekday")["buckets"][0]["key"] == "Monday"
    late = T("l", entry="2026-10-18T20:00:00+00:00")  # 01:30 IST Monday
    assert analytics.attribution_report([late], [], "weekday")["buckets"][0]["key"] == "Monday"


def test_attribution_bad_group_raises():
    with pytest.raises(ValueError):
        analytics.attribution_report([], [], "nope")


def test_distribution_with_excursions():
    ts = [T("a", 100), T("b", -50)]
    r = analytics.distribution_report(ts, [{"position_id": "a", "mfe": 150.0, "mae": -20.0}])
    assert sum(b["count"] for b in r["pnl"]) == 2
    assert r["mfe_mae"] == [{"id": "a", "mfe": 150.0, "mae": -20.0, "final": 100.0}]
    assert r["medians"]["pnl"]["p50"] == 25.0


def test_execution_not_recorded_and_charges():
    ts = [T("a", charges_breakdown={"brokerage": 20, "stt": 5, "exchange_fee": 1, "sebi_fee": 0.1, "stamp_duty": 0.5, "gst": 4}, total_charges=30.6),
          T("b", entry_spread_pct=1.5, option_volume=500)]
    r = analytics.execution_report(ts)
    assert "entry_spread_pct" not in r["not_recorded"] and "option_oi" in r["not_recorded"]
    assert r["charges"]["totals"]["brokerage"] == 20
    assert r["spread"]["buckets"] == [{"label": "1-2%", "trades": 1, "avg_slippage": 0.5}]
    assert analytics.execution_report([T("x")])["not_recorded"].count("option_volume") == 1


def test_filter_range_quarantine_and_book():
    ts = [T("a", exit_="2026-10-19T09:30:00+05:30"), T("b", exit_="2026-10-20T15:29:00+05:30"), T("c", exit_="2026-10-21T10:00:00+05:30"),
          T("q", q="BAD"), T("l", feed="live")]
    kept, ex = analytics.filter_trades(ts, rng=(date(2026, 10, 19), date(2026, 10, 20)), book="demo")
    assert [p.id for p in kept] == ["a", "b"] and ex == 1
    kept, _ = analytics.filter_trades(ts, book="all")
    assert "l" in [p.id for p in kept]
    midnight = T("m", exit_="2026-10-19T18:30:00+00:00")  # 00:00 IST on the 20th
    kept, _ = analytics.filter_trades([midnight], rng=(date(2026, 10, 20), date(2026, 10, 20)))
    assert len(kept) == 1


def test_parse_range_rejects_reversed_and_bad():
    with pytest.raises(ValueError):
        analytics.parse_range("2026-10-20", "2026-10-19")
    with pytest.raises(ValueError):
        analytics.parse_range("nope", None)


def pos(id, sym="NIFTY", side="CE", setup="Setup 1", status="OPEN", qty=10, entry=100.0, sl=90.0, last=105.0):
    return SimpleNamespace(id=id, symbol=sym, strike_symbol=f"{sym} X", option_type=side, setup_type=setup, status=status, quantity=qty,
                           option_entry=entry, option_sl=sl, current_option_price=last, option_target_1=120.0)


def test_risk_totals_match_rows_and_ignore_closed():
    ps = [pos("a"), pos("b", sym="BANKNIFTY", side="PE", qty=20), pos("c", status="CLOSED")]
    r = analytics.risk_snapshot(ps, SimpleNamespace(get=lambda k: 5))
    assert len(r["open"]) == 2
    assert r["totals"]["risk_rupees"] == sum(x["risk_rupees"] for x in r["open"]) == 300
    assert r["totals"]["max_open"] == 5 and r["totals"]["count"] == 2
    assert sum(g["risk_rupees"] for g in r["by_underlying"]) == 300


def test_clean_replaces_non_finite():
    assert analytics.clean({"a": float("nan"), "b": [float("inf"), 1.0]}) == {"a": None, "b": [None, 1.0]}


# ---- API --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["equity", "attribution", "distribution", "execution", "risk"])
def test_api_ok_and_requires_capability(path):
    assert client.get(f"/api/analytics/{path}").status_code == 200
    assert client.get(f"/api/analytics/{path}", headers={"X-Omit-Capability": "1"}).status_code == 401


def test_api_validation():
    assert client.get("/api/analytics/attribution?group=bogus").status_code == 422
    assert client.get("/api/analytics/equity?from=2026-10-20&to=2026-10-19").status_code == 422
    assert client.get("/api/analytics/equity?side=XX").status_code == 422
    assert client.get("/api/analytics/distribution?bins=2").status_code == 422
    assert client.get("/api/analytics/equity?book=all").json()["points"] is not None


def test_large_book_is_fast(monkeypatch):
    from app.services.paper_trader import paper_trader
    base = [T(f"x{i}", net=(i % 7) - 3, setup=f"Setup {i % 5}", exit_=f"2026-10-{1 + i % 28:02d}T10:00:00+05:30",
              entry=f"2026-10-{1 + i % 28:02d}T09:30:00+05:30") for i in range(5000)]
    monkeypatch.setattr(paper_trader._portfolio, "closed_trades", base, raising=False)
    t0 = time.time()
    for path in ("equity", "attribution", "distribution", "execution"):
        r = client.get(f"/api/analytics/{path}?book=all")
        assert r.status_code == 200
    assert time.time() - t0 < 4.0
