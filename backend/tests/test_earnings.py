import asyncio
from datetime import date, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from app.services import earnings_strategy as es
from app.services import market_hours
from app.services.earnings_engine import EarningsEngine
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry

IST = market_hours.IST
NOW = datetime(2026, 10, 14, 11, 0, tzinfo=IST)  # Wednesday, pinned by conftest
TODAY = NOW.date()


def trading_days_after(d, n):
    cur = d
    for _ in range(n):
        cur = es.next_trading_day(cur)
    return cur


# ---------------------------------------------------------------- fake market
class FakeProvider:
    def __init__(self, spot=1000.0, iv=30.0, spread=1.0):
        self.spot_value, self.iv, self.spread = spot, iv, spread
        self.drop_chain = False
        self.tv = 25.0
        self.expiry_list = [TODAY + timedelta(days=45), TODAY + timedelta(days=75)]

    def has_credentials(self): return True
    def instrument(self, symbol): return {"security_id": "1", "lot_size": 100, "exchange_segment": "NSE_EQ"} if symbol != "NOPE" else None
    async def spot(self, symbol): return self.spot_value
    async def expiries(self, symbol): return list(self.expiry_list)
    async def chain(self, symbol, expiry):
        if self.drop_chain:
            return {}
        oc = {}
        for i in range(-10, 11):
            k = 1000 + i * 10
            def side(kind):
                intrinsic = max(0.0, (self.spot_value - k) if kind == "ce" else (k - self.spot_value))
                mid = intrinsic + self.tv * max(0.2, 1 - abs(self.spot_value - k) / 200)
                return {"security_id": f"{kind}{k}", "last_price": round(mid, 2), "top_bid_price": round(mid - self.spread / 2, 2),
                        "top_ask_price": round(mid + self.spread / 2, 2), "implied_volatility": self.iv,
                        "greeks": {"delta": 0.5}, "volume": 1000, "oi": 5000}
            oc[f"{k:.6f}"] = {"ce": side("ce"), "pe": side("pe")}
        return oc


def make_engine(tmp_path, provider=None, kill=False):
    db = str(tmp_path / "e.db")
    rt = RuntimeSettings(db)
    eng = EarningsEngine(db, rt, Telemetry(db, rt), provider or FakeProvider(), kill_switch=lambda: kill)
    rt.set("earnings_enabled", True)
    rt.set("earnings_entry_time", "09:30")
    rt.set("daily_loss_limit", 0)
    return eng


def run(coro):
    return asyncio.run(coro)


def add_a_candidate(eng, symbol="ABC", days=10, session="AMC", sector="Tech"):
    edate = (TODAY + timedelta(days=days)).isoformat()
    eng.store.upsert_calendar(symbol, edate, session, sector)
    return edate


# ---------------------------------------------------------------- calendar maths
def test_session_timing_bmo_vs_amc():
    wed = date(2026, 10, 14)
    assert es.reaction_day(wed, "BMO") == wed
    assert es.reaction_day(wed, "AMC") == es.next_trading_day(wed)
    assert es.last_safe_close(wed, "BMO") == es.prev_trading_day(wed)
    assert es.last_safe_close(wed, "AMC") == wed
    sat = date(2026, 10, 17)
    assert es.reaction_day(sat, "BMO") == es.next_trading_day(sat)
    assert es.last_safe_close(sat, "AMC") == es.prev_trading_day(es.next_trading_day(sat))


def test_mode_a_exit_days_before_steps_back_by_trading_days():
    wed = date(2026, 10, 14)
    one = es.mode_a_exit_date(wed, "BMO", 1)
    two = es.mode_a_exit_date(wed, "BMO", 2)
    assert one == es.prev_trading_day(wed) and two == es.prev_trading_day(one)


def test_choose_expiry_rolls_when_too_close():
    exits = date(2026, 10, 20)
    near, far = exits + timedelta(days=3), exits + timedelta(days=30)
    assert es.choose_expiry([near, far], exits, 7) == far
    assert es.choose_expiry([near, far], exits, 2) == near
    assert es.choose_expiry([near], exits, 7) is None


def test_session_resolution_policy():
    assert es.resolve_session("amc", "SKIP") == "AMC"
    assert es.resolve_session("", "BMO") == "BMO"
    assert es.resolve_session("", "SKIP") is None


def test_iv_statistics():
    h = [10, 20, 30, 40]
    assert es.percentile_rank(30, h) == 75.0
    assert es.iv_rank(25, h) == 50.0
    assert es.iv_rank(5, h) == 0.0 and es.iv_rank(5, [3, 3]) is None


def test_exit_reason_priority_and_rules():
    base = dict(mode=es.MODE_A, today=TODAY, now_minutes=600, exit_date=TODAY + timedelta(days=3), exit_minutes=915,
                pnl=0.0, premium_paid=10000.0, max_loss_pct=40.0, spot=1000.0, short_pe=None, short_ce=None,
                expiry=TODAY + timedelta(days=40), min_days_to_expiry=7)
    assert es.exit_reason(**base) is None
    assert es.exit_reason(**{**base, "pnl": -4000.0}) == "STOP_LOSS"
    assert es.exit_reason(**{**base, "pnl": -3999.0}) is None
    assert es.exit_reason(**{**base, "max_loss_pct": 0, "pnl": -9999.0}) is None  # disabled
    assert es.exit_reason(**{**base, "exit_date": TODAY, "now_minutes": 914}) is None
    assert es.exit_reason(**{**base, "exit_date": TODAY, "now_minutes": 915}) == "SCHEDULED_EXIT"
    assert es.exit_reason(**{**base, "expiry": TODAY + timedelta(days=3)}) == "EXPIRY_TOO_CLOSE"
    b = {**base, "mode": es.MODE_B, "short_pe": 950.0, "short_ce": 1050.0}
    assert es.exit_reason(**{**b, "spot": 949.0}) == "SHORT_STRIKE_BREACHED"
    assert es.exit_reason(**{**b, "spot": 1000.0}) is None


# ---------------------------------------------------------------- engine: mode A
def test_mode_a_opens_once_and_is_idempotent(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng)
    r1 = run(eng.run_cycle(NOW))
    assert len(r1["opened"]) == 1
    pos = eng.positions("OPEN")[0]
    assert pos["mode"] == es.MODE_A and len(pos["legs"]) == 2 and {l["side"] for l in pos["legs"]} == {"BUY"}
    assert pos["qty"] == 100 and pos["max_risk"] == pytest.approx(pos["net_unit"] * 100, abs=0.01)
    assert len(run(eng.run_cycle(NOW))["opened"]) == 0


def test_disabled_strategy_opens_nothing(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng)
    eng.runtime.set("earnings_enabled", False)
    assert run(eng.run_cycle(NOW))["opened"] == []
    assert run(eng.preview(NOW))[0]["ready"] is True  # preview still shows the signal


def test_window_follows_settings(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng, days=20)
    assert run(eng.run_cycle(NOW))["opened"] == []
    eng.runtime.set("earnings_mode_a_far_days", 25)
    assert len(run(eng.run_cycle(NOW))["opened"]) == 1


def test_session_unknown_is_skipped_until_policy_changes(tmp_path):
    eng = make_engine(tmp_path)
    eng.runtime.set("earnings_default_session", "SKIP")
    add_a_candidate(eng, session="")
    assert run(eng.run_cycle(NOW))["opened"] == []
    assert eng.telemetry.decisions(book="earnings", decision="SKIPPED")[0]["reason"] == "SESSION_UNKNOWN"
    eng.runtime.set("earnings_default_session", "AMC")
    assert len(run(eng.run_cycle(NOW))["opened"]) == 1


def test_not_in_universe_and_before_entry_time(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng, symbol="NOPE")
    run(eng.run_cycle(NOW))
    assert eng.telemetry.decisions(book="earnings")[0]["reason"] == "NOT_IN_FNO_UNIVERSE"
    d2 = tmp_path / "x"
    d2.mkdir()
    eng2 = make_engine(d2)
    add_a_candidate(eng2)
    eng2.runtime.set("earnings_entry_time", "15:00")
    assert run(eng2.run_cycle(NOW))["entries"] == "before_entry_time"


def test_rms_gates(tmp_path):
    # kill switch
    assert run(make_engine(tmp_path, kill=True).run_cycle(NOW))["opened"] == []
    # max positions + sector
    d = tmp_path / "b"; d.mkdir()
    eng = make_engine(d)
    add_a_candidate(eng, "AAA", sector="Tech")
    add_a_candidate(eng, "BBB", sector="Tech")
    add_a_candidate(eng, "CCC", sector="Banks")
    r = run(eng.run_cycle(NOW))
    assert len(r["opened"]) == 2  # BBB blocked by sector
    codes = {x["symbol"]: x["reason"] for x in eng.telemetry.decisions(book="earnings", decision="SKIPPED")}
    assert codes["BBB"] == "SECTOR_CONCENTRATION"
    eng.runtime.set("earnings_one_per_sector", False)
    eng.runtime.set("earnings_max_positions", 2)
    assert len(run(eng.run_cycle(NOW))["opened"]) == 0
    assert any(x["reason"] == "MAX_OPEN_POSITIONS" for x in eng.telemetry.decisions(book="earnings", decision="SKIPPED"))


def test_capital_cap_and_lot_cap(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng)
    eng.runtime.set("earnings_max_capital_per_trade", 100)
    assert run(eng.run_cycle(NOW))["opened"] == []
    eng.runtime.set("earnings_max_capital_per_trade", 0)
    eng.runtime.set("earnings_lots", 5)
    eng.runtime.set("max_lots_per_trade", 2)
    run(eng.run_cycle(NOW))
    assert eng.positions("OPEN")[0]["lots"] == 2


def test_spread_filter(tmp_path):
    eng = make_engine(tmp_path, FakeProvider(spread=40.0))
    add_a_candidate(eng)
    assert run(eng.run_cycle(NOW))["opened"] == []
    assert eng.telemetry.decisions(book="earnings", decision="SKIPPED")[0]["reason"] == "SPREAD_TOO_WIDE"


def test_ivp_filter_uses_history_and_policy(tmp_path):
    eng = make_engine(tmp_path, FakeProvider(iv=50.0))
    eng.runtime.set("earnings_iv_min_history", 5)
    add_a_candidate(eng)
    for i in range(1, 8):  # history all lower than today's 50 => 100th percentile
        eng.store.record_iv("ABC", TODAY - timedelta(days=i), 20.0 + i)
    # the cycle records today's IV itself, which is excluded from the comparison history
    assert run(eng.run_cycle(NOW))["opened"] == []
    assert eng.telemetry.decisions(book="earnings", decision="SKIPPED")[0]["reason"] == "IV_PERCENTILE_TOO_HIGH"
    eng.runtime.set("earnings_mode_a_max_ivp", 0)
    assert len(run(eng.run_cycle(NOW))["opened"]) == 1


def test_short_history_policy_skip(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng)
    eng.runtime.set("earnings_iv_missing_policy", "skip")
    assert run(eng.run_cycle(NOW))["opened"] == []
    assert eng.telemetry.decisions(book="earnings", decision="SKIPPED")[0]["reason"] == "IV_HISTORY_TOO_SHORT"


def test_iv_history_is_recorded_daily(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng)
    run(eng.run_cycle(NOW))
    assert eng.store.has_iv("ABC", TODAY)


def test_stop_loss_exit_and_pnl_math(tmp_path):
    prov = FakeProvider()
    eng = make_engine(tmp_path, prov)
    add_a_candidate(eng)
    run(eng.run_cycle(NOW))
    pos = eng.positions("OPEN")[0]
    entry_debit = pos["net_unit"]
    prov.tv = 5.0  # option premiums collapse: the straddle loses most of its value
    later = NOW + timedelta(minutes=5)
    r = run(eng.run_cycle(later))
    closed = eng.positions("CLOSED")
    assert len(closed) == 1 and closed[0]["exit_reason"] in ("STOP_LOSS", "SCHEDULED_EXIT")
    c = closed[0]
    legs_exit = sum(l["current_bid"] for l in c["legs"])
    assert c["gross_pnl"] == pytest.approx((legs_exit - entry_debit) * 100, abs=0.5)
    assert c["net_pnl"] == pytest.approx(c["gross_pnl"] - c["charges"], abs=0.01) and c["charges"] > 0
    assert any(d["decision"] == "EXITED" for d in eng.telemetry.decisions(book="earnings"))


def test_scheduled_exit_and_reschedule(tmp_path):
    eng = make_engine(tmp_path)
    eng.runtime.set("earnings_mode_a_max_loss_pct", 0)
    edate = add_a_candidate(eng, days=10, session="AMC")
    run(eng.run_cycle(NOW))
    pos = eng.positions("OPEN")[0]
    exit_day = datetime.combine(date.fromisoformat(pos["exit_date"]), datetime.min.time(), tzinfo=IST)
    # before the exit time: stays open; at the exit time: closes
    run(eng.run_cycle(exit_day.replace(hour=14, minute=0)))
    assert len(eng.positions("OPEN")) == 1
    run(eng.run_cycle(exit_day.replace(hour=15, minute=15)))
    assert eng.positions("CLOSED")[0]["exit_reason"] == "SCHEDULED_EXIT"


def test_changed_announcement_session_moves_exit_date(tmp_path):
    eng = make_engine(tmp_path)
    edate = add_a_candidate(eng, days=9, session="AMC")
    run(eng.run_cycle(NOW))
    before = eng.positions("OPEN")[0]["exit_date"]
    eng.store.upsert_calendar("ABC", edate, "BMO", "Tech")  # company moved the result to before the open
    run(eng.run_cycle(NOW + timedelta(minutes=1)))
    after = eng.positions("OPEN")[0]["exit_date"]
    assert after == es.mode_a_exit_date(date.fromisoformat(edate), "BMO", 1).isoformat() and after < before
    assert any(d["reason"] == "EXIT_DATE_RESCHEDULED" for d in eng.telemetry.decisions(book="earnings"))


def test_no_quote_never_exits_on_stale_price(tmp_path):
    prov = FakeProvider()
    eng = make_engine(tmp_path, prov)
    eng.runtime.set("earnings_mode_a_max_loss_pct", 1)
    add_a_candidate(eng)
    run(eng.run_cycle(NOW))
    prov.drop_chain = True
    run(eng.run_cycle(NOW + timedelta(minutes=5)))
    assert len(eng.positions("OPEN")) == 1


def test_square_off_all_and_summary(tmp_path):
    eng = make_engine(tmp_path)
    add_a_candidate(eng, "AAA", sector="X")
    add_a_candidate(eng, "BBB", sector="Y")
    run(eng.run_cycle(NOW))
    s = eng.summary()
    assert s["open_positions"] == 2 and s["equity"] == pytest.approx(s["starting_capital"] + s["unrealized_net_pnl"], abs=0.01)
    assert run(eng.square_off_all("TEST")) == 2
    s2 = eng.summary()
    assert s2["open_positions"] == 0 and s2["closed_trades"] == 2 and s2["total_charges"] > 0


def test_daily_loss_cap_blocks_new_entries(tmp_path):
    eng = make_engine(tmp_path)
    eng.runtime.set("daily_loss_limit", 1)  # any realised loss trips it
    add_a_candidate(eng, "AAA", sector="X")
    run(eng.run_cycle(NOW))
    run(eng.square_off_all("TEST"))  # pays spread + charges => a loss
    assert eng.day_pnl(TODAY) <= -1
    add_a_candidate(eng, "BBB", sector="Y")
    run(eng.run_cycle(NOW))
    assert any(d["reason"] == "LOSS_CAP" for d in eng.telemetry.decisions(book="earnings", decision="SKIPPED"))


# ---------------------------------------------------------------- engine: mode B
def test_mode_b_condor_on_entry_day(tmp_path):
    eng = make_engine(tmp_path, FakeProvider(iv=45.0))
    eng.runtime.set("earnings_mode_a_enabled", False)
    edate = TODAY + timedelta(days=1)  # announced before the open tomorrow, so today's close is the last safe one
    assert es.last_safe_close(edate, "BMO") == TODAY
    eng.store.upsert_calendar("ABC", edate.isoformat(), "BMO", "Tech")
    run(eng.run_cycle(NOW))
    pos = eng.positions("OPEN")[0]
    sides = sorted((l["opt"], l["side"], l["strike"]) for l in pos["legs"])
    assert sides == [("CE", "BUY", 1040.0), ("CE", "SELL", 1020.0), ("PE", "BUY", 960.0), ("PE", "SELL", 980.0)]
    assert pos["short_pe"] == 980.0 and pos["short_ce"] == 1020.0
    assert pos["max_risk"] == pytest.approx((20 - pos["net_unit"]) * 100, abs=0.01)
    assert pos["exit_date"] == es.reaction_day(edate, "BMO").isoformat()


def test_mode_b_short_strike_breach_exits(tmp_path):
    prov = FakeProvider(iv=45.0)
    eng = make_engine(tmp_path, prov)
    eng.runtime.set("earnings_mode_a_enabled", False)
    eng.store.upsert_calendar("ABC", (TODAY + timedelta(days=1)).isoformat(), "BMO", "Tech")
    run(eng.run_cycle(NOW))
    prov.spot_value = 970.0
    run(eng.run_cycle(NOW + timedelta(minutes=5)))
    assert eng.positions("CLOSED")[0]["exit_reason"] == "SHORT_STRIKE_BREACHED"


def test_condor_strikes_follow_settings(tmp_path):
    eng = make_engine(tmp_path, FakeProvider(iv=45.0))
    eng.runtime.set("earnings_mode_a_enabled", False)
    eng.runtime.set("earnings_condor_short_steps", 3)
    eng.runtime.set("earnings_condor_wing_steps", 1)
    eng.store.upsert_calendar("ABC", (TODAY + timedelta(days=1)).isoformat(), "BMO", "Tech")
    run(eng.run_cycle(NOW))
    assert eng.positions("OPEN")[0]["short_pe"] == 970.0


# ---------------------------------------------------------------- API
def test_api_calendar_and_summary():
    from app.main import app
    client = TestClient(app)
    from app.services.earnings_registry import get_engine

    async def no_events():
        return [{"symbol": "NOSUCH", "purpose": "Dividend", "date": "01-Jan-2027"}]  # non-empty, matches nothing
    get_engine().events_fetcher = no_events  # never reach NSE from tests
    d = (TODAY + timedelta(days=30)).isoformat()
    try:
        r = client.post("/api/earnings/calendar", json={"rows": [{"symbol": "zzz", "earnings_date": d, "session": "bmo"}]})
        assert r.status_code == 200 and any(x["symbol"] == "ZZZ" and x["session"] == "BMO" for x in r.json())
        assert client.post("/api/earnings/calendar", json={"rows": [{"symbol": "zzz", "earnings_date": d, "session": "xx"}]}).status_code == 422
        assert client.post("/api/earnings/calendar", json={"rows": [{"symbol": "zzz", "earnings_date": "not-a-date"}]}).status_code == 422
        assert client.post("/api/earnings/iv-history", json={"points": [{"symbol": "zzz", "day": "2026-10-01", "iv": 31.5}]}).json() == {"imported": 1}
        s = client.get("/api/earnings/summary").json()
        assert s["enabled"] is False and s["open_positions"] == 0
        assert client.get("/api/earnings/candidates").json() == []  # no Dhan session in tests
        assert client.post("/api/earnings/run-cycle").json()["status"] == "no_credentials"
        assert client.post("/api/earnings/calendar/sync").json()["status"] == "ok"
    finally:
        client.delete(f"/api/earnings/calendar/ZZZ/{d}")
    assert client.delete(f"/api/earnings/calendar/ZZZ/{d}").status_code == 404


# ---------------------------------------------------------------- NSE calendar sync
EVENTS = [
    {"symbol": "ABC", "purpose": "Financial Results", "date": (TODAY + timedelta(days=9)).strftime("%d-%b-%Y"), "bm_desc": "x"},
    {"symbol": "ABC", "purpose": "Dividend", "date": (TODAY + timedelta(days=3)).strftime("%d-%b-%Y")},
    {"symbol": "OUT", "purpose": "Financial Results", "date": (TODAY + timedelta(days=9)).strftime("%d-%b-%Y")},   # not F&O
    {"symbol": "DEF", "purpose": "Financial Results/Dividend", "date": (TODAY + timedelta(days=100)).strftime("%d-%b-%Y")},  # too far
    {"symbol": "GHI", "purpose": "Financial Results", "date": (TODAY - timedelta(days=2)).strftime("%d-%b-%Y")},   # past
    {"symbol": "JKL", "purpose": "Financial Results/Other business matters", "date": "bad-date"},
]


def sync_engine(tmp_path, events):
    eng = make_engine(tmp_path)
    box = {"events": events}

    async def fetch():
        if isinstance(box["events"], Exception):
            raise box["events"]
        return box["events"]
    eng.events_fetcher = fetch
    eng._universe = lambda: {"ABC", "DEF", "GHI", "JKL"}
    return eng, box


def test_sync_adds_only_future_fno_result_dates(tmp_path):
    eng, _ = sync_engine(tmp_path, EVENTS)
    res = run(eng.sync_calendar(TODAY, force=True))
    assert res == {"status": "ok", "added": 1, "removed": 0, "listed": 1}
    row = eng.store.calendar()[0]
    assert row["symbol"] == "ABC" and row["session"] == "" and row["source"] == "NSE"


def test_default_session_is_amc_so_unset_rows_trade(tmp_path):
    eng = make_engine(tmp_path)
    assert eng.runtime.get("earnings_default_session") == "AMC"
    add_a_candidate(eng, session="")
    assert len(run(eng.run_cycle(NOW))["opened"]) == 1


def test_infer_session_from_nse_event_text():
    from app.services.earnings_calendar_sync import infer_session as inf
    assert inf({"bm_desc": "Results to be announced before market hours"}) == "BMO"
    assert inf({"bm_desc": "Meeting held post market"}) == "AMC"
    assert inf({"bm_timestamp": "2026-10-21 08:30:00"}) == "BMO"
    assert inf({"bm_timestamp": "21-Oct-2026 16:45:00"}) == "AMC"
    assert inf({"time": "2 pm"}) == "AMC"
    assert inf({"time": "8:00 AM"}) == "BMO"
    assert inf({"purpose": "Financial Results/Dividend Rs. 2.50 per share"}) == ""
    assert inf({"purpose": "Financial Results"}) == ""


def test_sync_infers_session_and_manual_wins(tmp_path):
    ev = [{**EVENTS[0], "bm_desc": "Outcome before market hours"}]
    eng, box = sync_engine(tmp_path, ev)
    run(eng.sync_calendar(TODAY, force=True))
    row = eng.calendar_view()[0]
    assert row["session"] == "BMO" and row["session_origin"] == "inferred" and row["effective_session"] == "BMO"
    # NSE text changes: an inferred session follows it
    box["events"] = [{**EVENTS[0], "bm_desc": "after market"}]
    run(eng.sync_calendar(TODAY, force=True))
    assert eng.calendar_view()[0]["session"] == "AMC"
    # a hand-set session is never replaced by a later inference
    r = eng.store.calendar()[0]
    eng.store.upsert_calendar(r["symbol"], r["earnings_date"], "BMO", r["sector"], r["note"], source="NSE")
    run(eng.sync_calendar(TODAY, force=True))
    v = eng.calendar_view()[0]
    assert v["session"] == "BMO" and v["session_origin"] == "manual"


def test_calendar_view_reports_default_and_skip(tmp_path):
    eng, _ = sync_engine(tmp_path, EVENTS)
    run(eng.sync_calendar(TODAY, force=True))
    v = eng.calendar_view()[0]
    assert v["session"] == "" and v["session_origin"] == "default" and v["effective_session"] == "AMC"
    eng.runtime.set("earnings_default_session", "SKIP")
    assert eng.calendar_view()[0]["session_origin"] == "skip"


def test_sync_runs_once_a_day_and_respects_switch(tmp_path):
    eng, _ = sync_engine(tmp_path, EVENTS)
    assert run(eng.sync_calendar(TODAY))["status"] == "ok"
    assert run(eng.sync_calendar(TODAY))["status"] == "skipped"
    assert run(eng.sync_calendar(TODAY + timedelta(days=1)))["status"] == "ok"
    eng.runtime.set("earnings_auto_sync", False)
    assert run(eng.sync_calendar(TODAY + timedelta(days=2)))["status"] == "skipped"


def test_sync_never_overwrites_manual_rows_and_drops_moved_nse_rows(tmp_path):
    eng, box = sync_engine(tmp_path, EVENTS)
    d = (TODAY + timedelta(days=9)).isoformat()
    eng.store.upsert_calendar("ABC", d, "BMO", "Tech")  # user's own row for the same date
    assert run(eng.sync_calendar(TODAY, force=True))["added"] == 0
    assert eng.store.calendar()[0]["session"] == "BMO"
    eng.store.delete_calendar("ABC", d)
    run(eng.sync_calendar(TODAY, force=True))
    box["events"] = [{**EVENTS[0], "date": (TODAY + timedelta(days=11)).strftime("%d-%b-%Y")}]  # NSE moved the meeting
    res = run(eng.sync_calendar(TODAY, force=True))
    assert res["added"] == 1 and res["removed"] == 1
    assert [r["earnings_date"] for r in eng.store.calendar()] == [(TODAY + timedelta(days=11)).isoformat()]


def test_sync_failure_is_reported_not_raised(tmp_path):
    eng, _ = sync_engine(tmp_path, RuntimeError("blocked"))
    res = run(eng.sync_calendar(TODAY, force=True))
    assert res["status"] == "error" and "blocked" in res["error"]


def test_cycle_syncs_even_without_broker_session(tmp_path):
    eng, _ = sync_engine(tmp_path, EVENTS)
    eng.provider = None
    r = run(eng.run_cycle(NOW))
    assert r["status"] == "no_credentials" and r["calendar_sync"]["added"] == 1


def test_parse_handles_real_nse_shape():
    from app.services.earnings_calendar_sync import parse_results_rows
    ev = [{"symbol": "BAJFINANCE", "company": "Bajaj Finance Limited", "purpose": "Financial Results",
           "bm_desc": "To consider ...", "date": "19-Oct-2026"}]
    rows = parse_results_rows(ev, {"BAJFINANCE"}, date(2026, 10, 17), 45)
    assert rows == [{"symbol": "BAJFINANCE", "earnings_date": "2026-10-19", "note": "Financial Results", "session": ""}]


def test_bulk_calendar_import_is_all_or_nothing():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.earnings_registry import get_engine
    c = TestClient(app)
    c.cookies.set("dashboard_session", __import__("app.core.security", fromlist=["x"]).issue_session_token())
    before = len(get_engine().store.calendar())
    r = c.post("/api/earnings/calendar", json={"rows": [
        {"symbol": "OKCO", "earnings_date": "2030-01-15"},
        {"symbol": "BADCO", "earnings_date": "not-a-date"}]})
    assert r.status_code == 422
    assert len(get_engine().store.calendar()) == before


# ---------------------------------------------------------------- polling previews must not pile up Dhan calls
class SlowProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.spot_calls = 0
        self.cooling = False

    async def spot(self, symbol):
        self.spot_calls += 1
        await asyncio.sleep(0.3)
        return self.spot_value

    def cooling_down(self): return self.cooling


def test_cached_preview_runs_one_evaluation_for_many_polls(tmp_path):
    prov = SlowProvider()
    eng = make_engine(tmp_path, prov)
    add_a_candidate(eng)

    async def poll():
        with market_hours.override_clock(NOW):
            first = await asyncio.gather(*[eng.preview_cached(wait_s=2.0) for _ in range(5)])   # five screens polling at once
            calls_after_first = prov.spot_calls
            again = await eng.preview_cached(wait_s=2.0)                                       # within the TTL
        return first, calls_after_first, again

    first, calls, again = run(poll())
    assert calls == 1 and prov.spot_calls == 1
    assert all(rows == first[0] for rows in first) and again == first[0]


def test_slow_preview_returns_last_rows_instead_of_blocking(tmp_path):
    prov = SlowProvider()
    eng = make_engine(tmp_path, prov)
    add_a_candidate(eng)

    async def poll():
        with market_hours.override_clock(NOW):
            return await eng.preview_cached(wait_s=0.01)      # shorter than the evaluation: nothing cached yet
    assert run(poll()) == []


def test_preview_is_not_refreshed_while_dhan_is_cooling_down(tmp_path):
    prov = SlowProvider()
    prov.cooling = True
    eng = make_engine(tmp_path, prov)
    add_a_candidate(eng)

    async def poll():
        with market_hours.override_clock(NOW):
            return await eng.preview_cached(wait_s=1.0)
    assert run(poll()) == [] and prov.spot_calls == 0


def test_rate_limited_skip_is_labelled_when_dhan_is_cooling(tmp_path):
    class NoData(SlowProvider):
        async def spot(self, symbol): return None
    prov = NoData()
    prov.cooling = True
    eng = make_engine(tmp_path, prov)
    add_a_candidate(eng)

    async def rows():
        with market_hours.override_clock(NOW):
            return await eng.preview()
    codes = {r["code"] for r in run(rows())}
    assert codes == {"RATE_LIMITED"}
