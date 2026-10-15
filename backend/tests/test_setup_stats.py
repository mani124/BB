from app.services.paper_models import PaperPosition
from app.services.setup_stats import compute_setup_stats


def pos(pid, setup, net, exit_dt, quarantine=None, sl=90.0, charges=10.0, slip=5.0):
    return PaperPosition(
        id=pid, signal_id=pid, symbol="NIFTY 50", option_type="CE", strike_symbol="X", timeframe="5m",
        setup_type=setup, entry_time="09:30:00", underlying_entry=1, underlying_sl=1, underlying_target_1=1,
        underlying_target_2=1, option_entry=100.0, option_sl=sl, option_target_1=1, option_target_2=1,
        lot_size=10, lots=1, quantity=10, current_underlying=1, current_option_price=1, pnl_points=0,
        pnl_rupees=net + charges, status="CLOSED", gross_pnl=net + charges, total_charges=charges,
        net_pnl=net, total_slippage_cost=slip, exit_datetime=exit_dt, quarantine_reason=quarantine,
    )


def test_groups_by_setup_and_day_with_totals_and_r():
    rows = compute_setup_stats([
        pos("a", "S1", 100.0, "2026-10-14T10:00:00+05:30"),   # risk 100 -> +1R
        pos("b", "S1", -50.0, "2026-10-14T11:00:00+05:30"),   # -0.5R
        pos("c", "S1", 200.0, "2026-10-15T11:00:00+05:30"),   # +2R
    ])
    by = {(r.setup_type, r.date): r for r in rows}
    d14 = by[("S1", "2026-10-14")]
    assert (d14.trades, d14.wins, d14.win_rate, d14.avg_r) == (2, 1, 50.0, 0.25)
    assert d14.net_pnl == 50.0 and d14.gross_pnl == 70.0
    assert d14.total_charges == 20.0 and d14.total_slippage_cost == 10.0
    total = by[("S1", "ALL")]
    assert total.trades == 3 and total.r_trades == 3 and total.avg_r == 0.83 and total.net_pnl == 250.0
    assert [r.date for r in rows] == ["ALL", "2026-10-15", "2026-10-14"]


def test_quarantined_excluded_and_unmeasurable_r_is_none():
    rows = compute_setup_stats([
        pos("a", "S2", 999.0, "2026-10-14T10:00:00+05:30", quarantine="bad"),
        pos("b", "S2", 10.0, "2026-10-14T10:00:00+05:30", sl=100.0),  # no stop distance
    ])
    tot = [r for r in rows if r.date == "ALL"][0]
    assert tot.trades == 1 and tot.avg_r is None and tot.r_trades == 0


def test_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/paper/setup-stats?mode=all")
    assert r.status_code == 200 and isinstance(r.json(), list)
