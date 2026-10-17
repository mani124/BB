"""Regression tests for the 17 October review (REVIEW_FINDINGS_2026-10-17)."""
import asyncio
from datetime import date, timedelta

from app.core import security
from app.services import earnings_engine as ee
from app.services import earnings_strategy as es
from app.services.runtime_settings import DEFINITIONS, SettingError, coerce


def _pos(pid="P1", status="OPEN"):
    return {"id": pid, "symbol": "ABC", "mode": "A", "status": status, "earnings_date": "2026-11-01", "opened_at": "2026-10-17T10:00:00"}


def test_save_position_never_reopens_a_closed_row():  # C1
    store = ee.EarningsStore(None)
    store.save_position(_pos(status="CLOSED"))
    store.save_position(_pos(status="OPEN"))  # a stale copy held by a running cycle
    assert store.position_status("P1") == "CLOSED"


def test_nse_empty_answer_keeps_calendar_and_backs_off():  # I6
    calls = []

    async def empty():
        calls.append(1)
        return []

    eng = ee.EarningsEngine.__new__(ee.EarningsEngine)  # only sync_calendar is exercised
    eng.events_fetcher = empty
    eng.store = ee.EarningsStore(None)
    eng.store.upsert_calendar("ABC", (date.today() + timedelta(days=5)).isoformat(), source="NSE")
    eng._last_sync_failure = None
    eng._universe = lambda: {"ABC"}

    class RT:
        def get(self, k):
            return {"earnings_auto_sync": True, "earnings_sync_horizon_days": 30}[k]
    eng.runtime = RT()
    r1 = asyncio.run(eng.sync_calendar(date.today()))
    r2 = asyncio.run(eng.sync_calendar(date.today()))
    assert r1["status"] == "error" and r2["status"] == "skipped"
    assert len(calls) == 1 and len(eng.store.calendar()) == 1


def test_bought_leg_with_no_bid_is_worth_nothing():  # M4
    legs = [{"side": "BUY", "current_bid": 0.0, "current_ask": 0.5, "current_ltp": 3.0, "entry_price": 2.0}]
    assert es.close_value_per_unit(legs) == 0.0


def test_non_ascii_capability_header_is_not_a_500():  # M1
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get("/api/paper/portfolio", headers={"X-Dashboard-Capability": "k\u00e9y".encode("latin-1")})
    assert r.status_code in (401, 403)


def test_infinite_int_setting_is_a_validation_error():  # M2
    defn = next(d for d in DEFINITIONS if d.type == "int")
    try:
        coerce(defn, "inf")
    except SettingError:
        return
    raise AssertionError("expected SettingError")
