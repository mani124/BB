from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services import market_hours
from app.services.market_recorder import MarketRecorder, OPTION, SPOT
from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker


class FakeRuntime:
    def __init__(self, **kw):
        self.values = {"recorder_enabled": True, "recorder_retention_days": 180, **kw}

    def get(self, key):
        return self.values[key]


def bar(ts, o=100.0, h=101.0, l=99.0, c=100.5, v=10):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_record_flush_and_read_back(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    r.record(SPOT, "NIFTY 50", 5, bar(datetime(2026, 10, 14, 9, 15)))
    r.record(SPOT, "NIFTY 50", 5, bar(pd.Timestamp("2026-10-14 09:20")))
    assert r.flush() == 2
    rows = r.bars(SPOT, "NIFTY 50", 5, "2026-10-14")
    assert [x["timestamp"] for x in rows] == ["2026-10-14 09:15:00", "2026-10-14 09:20:00"]
    assert rows[0]["close"] == 100.5 and rows[0]["volume"] == 10


def test_duplicates_are_ignored(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    for _ in range(3):
        r.record(OPTION, "55555", 5, bar(datetime(2026, 10, 14, 9, 15)))
        r.flush()
    assert len(r.bars(OPTION, "55555", 5)) == 1
    assert r.status()["kinds"][OPTION]["bars"] == 1


def test_disabled_records_nothing(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime(recorder_enabled=False))
    r.record(SPOT, "X", 5, bar(datetime(2026, 10, 14, 9, 15)))
    assert r.flush() == 0
    assert r.bars(SPOT, "X") == []


def test_bad_bars_are_skipped_without_raising(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    r.record(SPOT, "X", 5, {"timestamp": None, "open": 1})
    r.record(SPOT, "X", 5, {"timestamp": datetime(2026, 10, 14, 9, 15)})  # missing prices
    assert r.flush() == 0


def test_purge_removes_old_bars_only(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime(recorder_retention_days=30))
    now = market_hours.now_ist_naive()
    r.record(SPOT, "X", 5, bar(now - timedelta(days=40)))
    r.record(SPOT, "X", 5, bar(now - timedelta(days=1)))
    r.flush()
    assert r.purge() == 1
    assert len(r.bars(SPOT, "X")) == 1
    r.runtime = FakeRuntime(recorder_retention_days=0)
    assert r.purge() == 0  # 0 keeps everything


def test_failed_flush_keeps_bars_for_next_try(tmp_path):
    r = MarketRecorder(str(tmp_path / "no" / "m.db"), FakeRuntime())
    r.record(SPOT, "X", 5, bar(datetime(2026, 10, 14, 9, 15)))
    r._init_db = lambda: (_ for _ in ()).throw(RuntimeError("disk full"))
    assert r.flush() == 0
    assert len(r._buf) == 1


def test_status_when_nothing_recorded(tmp_path):
    r = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    s = r.status()
    assert s["kinds"] == {} and s["buffered"] == 0


def test_scanner_records_completed_option_bar(tmp_path, monkeypatch):
    from app.services import scanner_candles
    rec = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    monkeypatch.setattr(scanner_candles, "recorder", rec)
    worker = ScannerWorker(universe_mgr=UniverseManager())
    t0 = datetime(2026, 10, 14, 10, 0, 30, tzinfo=market_hours.IST)
    worker._get_or_update_option_candles("777", 50.0, 100, now=t0)
    worker._get_or_update_option_candles("777", 52.0, 150, now=t0 + timedelta(minutes=2))
    assert rec.flush() == 0  # the 10:00 bar is still forming
    worker._get_or_update_option_candles("777", 51.0, 200, now=t0 + timedelta(minutes=6))
    assert rec.flush() == 1
    row = rec.bars(OPTION, "777", 5)[0]
    assert row["timestamp"] == "2026-10-14 10:00:00"
    assert (row["open"], row["high"], row["close"]) == (50.0, 52.0, 52.0)


def test_scanner_records_completed_spot_bar(tmp_path, monkeypatch):
    from app.services import scanner_candles
    rec = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    monkeypatch.setattr(scanner_candles, "recorder", rec)
    worker = ScannerWorker(universe_mgr=UniverseManager())
    worker._state.active_mode = "live"
    inst = worker.universe_mgr.get_indices()[0]
    market_hours.set_clock(datetime(2026, 10, 14, 10, 1, 0, tzinfo=market_hours.IST))
    worker.get_or_update_live_candles(inst, {"last_price": 100.0})
    market_hours.set_clock(datetime(2026, 10, 14, 10, 3, 0, tzinfo=market_hours.IST))
    worker.get_or_update_live_candles(inst, {"last_price": 103.0})
    market_hours.set_clock(datetime(2026, 10, 14, 10, 6, 0, tzinfo=market_hours.IST))
    worker.get_or_update_live_candles(inst, {"last_price": 101.0})
    assert rec.flush() == 1
    row = rec.bars(SPOT, inst.symbol, 5)[0]
    assert (row["open"], row["high"], row["close"]) == (100.0, 103.0, 103.0)


def test_recorder_api(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from app.main import app
    from app.api import recorder as api
    rec = MarketRecorder(str(tmp_path / "m.db"), FakeRuntime())
    rec.record(SPOT, "NIFTY 50", 5, bar(datetime(2026, 10, 14, 9, 15)))
    rec.flush()
    monkeypatch.setattr(api, "recorder", rec)
    with TestClient(app) as c:
        assert c.get("/api/recorder/status").json()["kinds"][SPOT]["bars"] == 1
        rows = c.get("/api/recorder/bars", params={"key": "NIFTY 50", "day": "2026-10-14"}).json()
        assert len(rows) == 1
        assert c.get("/api/recorder/bars", params={"key": "x", "kind": "bogus"}).status_code == 422
