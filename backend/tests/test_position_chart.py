from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app, worker
from app.services.paper_trader import paper_trader, PaperPosition

client = TestClient(app, headers={"X-Dashboard-Capability": "bb-options-local-capability"})


def _bars(n=30, base=100.0):
    start = datetime(2026, 10, 15, 9, 15)
    return [
        {"timestamp": start + timedelta(minutes=5 * i), "open": base + i, "high": base + i + 2,
         "low": base + i - 2, "close": base + i + 1, "volume": 1000 + i}
        for i in range(n)
    ]


def _pos(**kw) -> PaperPosition:
    d = dict(
        id="chart-pos-1", signal_id="s", symbol="NIFTY 50", option_type="CE", strike_symbol="NIFTY 25000 CE",
        timeframe="5m", setup_type="Setup 2: Walking the Bands (9 EMA)", entry_time="10:00:00",
        underlying_entry=25000, underlying_sl=24950, underlying_target_1=25050, underlying_target_2=25100,
        option_entry=120, option_sl=100, option_target_1=140, option_target_2=160, lot_size=50, lots=1,
        quantity=50, current_underlying=25010, current_option_price=125, pnl_points=5, pnl_rupees=250,
        status="OPEN", option_security_id="99001", feed_mode="demo", entry_datetime="2026-10-15T10:00:00+05:30",
    )
    d.update(kw)
    return PaperPosition(**d)


def test_chart_payload_for_open_position():
    pos = _pos()
    paper_trader._portfolio.active_positions.append(pos)
    worker._option_candle_history["99001"] = _bars()
    worker._candle_history["NIFTY 50"] = _bars(base=25000)
    try:
        r = client.get("/api/paper/positions/chart-pos-1/chart")
        assert r.status_code == 200
        body = r.json()
        assert len(body["option"]["candles"]) == 30
        assert body["option"]["levels"]["stop"] == 100
        assert body["underlying"]["levels"]["target_2"] == 25100
        assert "bb_upper" in body["option"]["indicators"] and "ema_9" in body["underlying"]["indicators"]
        assert body["entry_time"] is not None
    finally:
        paper_trader._portfolio.active_positions.remove(pos)
        worker._option_candle_history.pop("99001", None)
        worker._candle_history.pop("NIFTY 50", None)


def test_chart_empty_when_no_candles_and_404_for_unknown():
    pos = _pos(id="chart-pos-2", option_security_id="99002")
    paper_trader._portfolio.active_positions.append(pos)
    try:
        body = client.get("/api/paper/positions/chart-pos-2/chart").json()
        assert body["option"]["candles"] == []
    finally:
        paper_trader._portfolio.active_positions.remove(pos)
    assert client.get("/api/paper/positions/nope/chart").status_code == 404


def test_bands_warm_up_on_prior_session_but_only_entry_day_is_shown():
    prev_day = [dict(b, timestamp=b["timestamp"] - timedelta(days=1)) for b in _bars(30, base=24900)]
    pos = _pos(id="chart-pos-3", option_security_id=None)
    paper_trader._portfolio.closed_trades.append(pos)
    worker._candle_history["NIFTY 50"] = prev_day + _bars(10, base=25000)
    try:
        body = client.get("/api/paper/positions/chart-pos-3/chart").json()
        und = body["underlying"]
        assert len(und["candles"]) == 10  # entry day only
        first_bar = und["candles"][0]["time"]
        # the 09:15 bar already has a 20-period band because history before it was used
        assert und["indicators"]["bb_upper"][0]["time"] == first_bar
        assert und["opening_range"] == {"high": 25004.0, "low": 24998.0}  # 09:15-09:25 bars of the entry day
    finally:
        paper_trader._portfolio.closed_trades.remove(pos)
        worker._candle_history.pop("NIFTY 50", None)


def test_candles_are_saved_and_chart_survives_restart_and_close(tmp_path):
    from app.services.paper_storage import PaperStorage
    storage = PaperStorage(str(tmp_path / "t.db"))
    old = paper_trader.storage
    paper_trader.storage = storage
    pos = _pos(id="chart-pos-4")
    paper_trader._portfolio.active_positions.append(pos)
    worker._option_candle_history["99001"] = _bars()
    worker._candle_history["NIFTY 50"] = _bars(base=25000)
    worker._trade_candle_saved_at.clear()
    try:
        worker.persist_trade_candles()
        assert len(storage.load_trade_candles("chart-pos-4", "option")) == 30
        # trade closes, scanner memory is gone (restart / new day)
        paper_trader._portfolio.active_positions.remove(pos)
        pos.status = "CLOSED"
        paper_trader._portfolio.closed_trades.append(pos)
        worker._option_candle_history.pop("99001")
        worker._candle_history.pop("NIFTY 50")
        body = client.get("/api/paper/positions/chart-pos-4/chart").json()
        assert len(body["option"]["candles"]) == 30
        assert len(body["underlying"]["candles"]) == 30
        assert "bb_upper" in body["option"]["indicators"]
    finally:
        paper_trader._portfolio.closed_trades.remove(pos)
        paper_trader.storage = old
        worker._trade_candle_saved_at.clear()


def test_trade_candles_cap_and_prune(tmp_path):
    from app.services.paper_storage import PaperStorage
    s = PaperStorage(str(tmp_path / "t.db"))
    s.save_trade_candles("orphan", "option", _bars(400))
    assert len(s.load_trade_candles("orphan", "option")) == s.TRADE_CANDLE_CAP
    assert s.prune_trade_candles() == 1  # no matching trade
    assert s.load_trade_candles("orphan", "option") == []


def test_quick_open_close_gets_final_snapshot_and_failed_save_retries(tmp_path):
    from app.services.paper_storage import PaperStorage
    storage = PaperStorage(str(tmp_path / "t.db"))
    old = paper_trader.storage
    paper_trader.storage = storage
    pos = _pos(id="chart-pos-5", status="CLOSED")
    paper_trader._portfolio.closed_trades.append(pos)  # opened and closed between two calls
    worker._option_candle_history["99001"] = _bars()
    worker._candle_history["NIFTY 50"] = _bars(base=25000)
    worker._trade_candle_saved_at.clear()
    real = storage.save_trade_candles
    try:
        def boom(*a, **k):
            raise RuntimeError("db busy")
        storage.save_trade_candles = boom
        worker.persist_trade_candles()
        assert worker._trade_candle_saved_at.get("chart-pos-5", 0) >= 0  # not marked done
        storage.save_trade_candles = real
        worker.persist_trade_candles()
        assert len(storage.load_trade_candles("chart-pos-5", "option")) == 30
        assert worker._trade_candle_saved_at["chart-pos-5"] == -1.0
    finally:
        storage.save_trade_candles = real
        paper_trader._portfolio.closed_trades.remove(pos)
        paper_trader.storage = old
        worker._option_candle_history.pop("99001", None)
        worker._candle_history.pop("NIFTY 50", None)
        worker._trade_candle_saved_at.clear()
