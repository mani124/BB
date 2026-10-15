from fastapi.testclient import TestClient

from app.main import app
from app.services.cost_analysis import build_cost_report, premium_bucket
from app.services.paper_trader import PaperTradingEngine
from tests.test_paper_slippage import mock_signal  # noqa: F401


def _trade(**kw):
    from app.services.paper_models import PaperPosition
    base = dict(
        id="p", signal_id="s", symbol="NIFTY 50", option_type="CE", strike_symbol="X", timeframe="5m",
        setup_type="SETUP_1_SQUEEZE", entry_time="09:30:00", underlying_entry=1, underlying_sl=1,
        underlying_target_1=1, underlying_target_2=1, option_entry=150.0, option_sl=1, option_target_1=1,
        option_target_2=1, lot_size=65, lots=1, quantity=65, current_underlying=1, current_option_price=1,
        pnl_points=0, pnl_rupees=0, status="STOPPED_OUT", exit_time="10:00:00",
        exit_datetime="2026-10-15T10:00:00", gross_pnl=1000.0, total_slippage_cost=200.0,
        total_charges=100.0, net_pnl=900.0,
    )
    base.update(kw)
    return PaperPosition(**base)


def test_premium_buckets():
    assert premium_bucket(49.99) == "Under 50"
    assert premium_bucket(50) == "50 - 100"
    assert premium_bucket(399) == "200 - 400"
    assert premium_bucket(1000) == "400 and above"


def test_report_totals_groups_and_quarantine():
    trades = [
        _trade(id="a"),
        _trade(id="b", symbol="RELIANCE", setup_type="Setup 5: Option Chart BB Scalp", option_entry=30.0,
               gross_pnl=-500.0, total_slippage_cost=-50.0, total_charges=80.0, net_pnl=-580.0,
               exit_datetime="2026-10-14T11:00:00"),
        _trade(id="q", quarantine_reason="bad", gross_pnl=99999.0),
    ]
    r = build_cost_report(trades)
    t = r.totals
    assert (t.trades, t.gross_pnl, t.slippage, t.charges, t.net_pnl) == (2, 500.0, 150.0, 180.0, 320.0)
    assert t.net_pnl == round(t.gross_pnl - t.charges, 2)  # slippage is already inside gross
    assert t.gross_before_slippage == 650.0
    assert [d.date for d in r.by_day] == ["2026-10-15", "2026-10-14"]
    assert {g.key for g in r.by_setup} == {"Setup 1", "Setup 5"}
    assert {g.key for g in r.by_symbol} == {"NIFTY 50", "RELIANCE"}
    assert [g.key for g in r.by_premium] == ["Under 50", "100 - 200"]
    assert r.by_setup[0].key == "Setup 1"  # biggest cost first
    assert len(r.trades) == 2 and r.trades[0].id == "a"


def test_empty_report():
    r = build_cost_report([])
    assert r.totals.trades == 0 and r.by_day == []
    assert r.totals.avg_slippage_per_trade == 0.0


def test_real_engine_trade_slippage_matches_gross(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    closed = engine.close_position(pos.id, real_bid_price=140.0, real_opt_price=140.0)
    r = build_cost_report([closed])
    assert r.totals.slippage == closed.total_slippage_cost > 0
    assert r.totals.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)


def test_costs_endpoint():
    res = TestClient(app).get("/api/paper/costs?mode=all")
    assert res.status_code == 200
    body = res.json()
    assert {"totals", "trades", "by_day", "by_setup", "by_symbol", "by_premium"} <= body.keys()
