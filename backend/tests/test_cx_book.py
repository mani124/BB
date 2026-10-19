import asyncio
from datetime import datetime, time

import pandas as pd
import pytest

from app.services import cx_engine as ce
from app.services import cx_signals as sg
from app.services import market_hours
from app.services.cx_engine import CxEngine
from app.services.runtime_settings import RuntimeSettings
from app.services.telemetry import Telemetry

IST = market_hours.IST


def at(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=IST)


# ---------------------------------------------------------------- signals
def frame(rows):
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def test_setup17_breaks_range_with_trend_confirmation():
    n = 5
    rows = [(f"2026-10-19 10:{i * 5:02d}", 100, 101, 99, 100) for i in range(8)] + [("2026-10-19 10:40", 100, 104, 100, 103.5)]
    ind = frame(rows)
    ind["adx"], ind["atr"], ind["plus_di"], ind["minus_di"], ind["ema_50"] = 30.0, 2.0, 30.0, 10.0, 100.0
    cfg = sg.CxSignalConfig(donchian_len=n, adx_min=20)
    s = sg.setup17("CRUDEOIL", ind, cfg)
    assert s and s.side == "CE" and s.invalidate_level == pytest.approx(101 - 1.0)
    ind["adx"] = 10.0
    assert sg.setup17("CRUDEOIL", ind, cfg) is None  # weak trend
    ind["adx"] = 30.0
    ind["ema_50"] = 110.0
    assert sg.setup17("CRUDEOIL", ind, cfg) is None  # wrong side of the 50 EMA


def test_setup17_only_fires_on_the_break_bar():
    rows = [(f"2026-10-19 10:{i * 5:02d}", 100, 101, 99, 100) for i in range(7)] + [("2026-10-19 10:35", 100, 104, 100, 103.5), ("2026-10-19 10:40", 103.5, 106, 103, 105.5)]
    ind = frame(rows)
    ind["adx"], ind["atr"], ind["plus_di"], ind["minus_di"], ind["ema_50"] = 30.0, 2.0, 30.0, 10.0, 100.0
    assert sg.setup17("X", ind, sg.CxSignalConfig(donchian_len=5)) is None  # previous bar already broke out


def test_setup18_fires_once_on_first_close_beyond_opening_range():
    rows = [(f"2026-10-19 09:{m:02d}", 100, 101, 99.5, 100.5) for m in range(0, 30, 5)]
    rows += [("2026-10-19 09:30", 100.5, 100.9, 100, 100.4), ("2026-10-19 09:35", 100.4, 102.5, 100.4, 102.2)]
    ind = frame(rows)
    s = sg.setup18("GOLDM", ind, sg.CxSignalConfig(orb_minutes=30), time(9, 0))
    assert s and s.side == "CE" and s.metrics["orb_high"] == 101
    ind2 = frame(rows + [("2026-10-19 09:40", 102.2, 103, 102, 102.8)])
    assert sg.setup18("GOLDM", ind2, sg.CxSignalConfig(orb_minutes=30), time(9, 0)) is None  # already broke earlier
    assert sg.setup18("GOLDM", frame(rows[:5]), sg.CxSignalConfig(orb_minutes=30), time(9, 0)) is None  # range not finished


def test_setup19_fades_a_stretch_only_in_a_range():
    ind = frame([("2026-10-19 10:00", 100, 100, 99, 99.5), ("2026-10-19 10:05", 99.5, 99.6, 97, 97.5), ("2026-10-19 10:10", 97.5, 98.8, 97.4, 98.6)])
    ind["bb_lower"], ind["bb_upper"], ind["rsi"], ind["adx"], ind["sma_20"] = 98.0, 102.0, [50, 25, 40], 15.0, 100.0
    s = sg.setup19("USDINR", ind, sg.CxSignalConfig())
    assert s and s.side == "CE" and s.invalidate_level == 97
    ind["adx"] = 35.0
    assert sg.setup19("USDINR", ind, sg.CxSignalConfig()) is None
    ind["adx"] = 15.0
    ind["rsi"] = [50, 45, 40]
    assert sg.setup19("USDINR", ind, sg.CxSignalConfig()) is None


# ---------------------------------------------------------------- engine
class FakeProvider:
    def __init__(self, symbol="CRUDEOIL", lot=100, bid=10.0, ask=10.2, price=6500.0, last_bar="2026-10-19 14:50"):
        self.symbol, self.lot, self.bid, self.ask, self.price, self.last_bar = symbol, lot, bid, ask, price, last_bar

    def has_credentials(self):
        return True

    async def contracts(self, symbols, today):
        return {s: [{"symbol": s, "security_id": "11", "expiry": "2026-11-19", "lot_size": self.lot, "lot_size_known": True, "display": s}] for s in symbols}

    async def candles(self, symbol, contract, now):
        end = pd.Timestamp(self.last_bar)
        ts = pd.date_range(end=end, periods=80, freq="5min")
        return pd.DataFrame({"timestamp": ts, "open": self.price, "high": self.price + 1, "low": self.price - 1, "close": self.price, "volume": 0})

    async def chain(self, symbol, contract, now):
        leg = {"top_bid_price": self.bid, "top_ask_price": self.ask, "last_price": (self.bid + self.ask) / 2, "security_id": "777", "greeks": {"delta": 0.5}}
        deep = {"top_bid_price": 99, "top_ask_price": 99.5, "last_price": 99, "security_id": "778"}
        far = {"top_bid_price": 1, "top_ask_price": 1.1, "last_price": 1, "security_id": "779"}
        # parity ATM is 6500 (call and put priced alike); 6400 and 6600 are clearly in / out of the money
        return "2026-10-27", {"6400.000000": {"ce": deep, "pe": far}, "6500.000000": {"ce": leg, "pe": leg}, "6600.000000": {"ce": far, "pe": deep}}


_n = [0]


@pytest.fixture(autouse=True)
def _clock():
    with market_hours.override_clock(at("2026-10-19 15:00")):
        yield


def make(tmp_path, provider=None, kill=False, **settings):
    _n[0] += 1
    db = str(tmp_path / f"cx{_n[0]}.db")
    rt = RuntimeSettings(db)
    provider = provider or FakeProvider()
    base = {"cx_symbols": provider.symbol, "cx_enabled": True, "cx_slippage_pct": 0.0, "cx_cooldown_minutes": 0}
    for k, v in {**base, **settings}.items():
        rt.set(k, v)
    return CxEngine(db, rt, Telemetry(db, rt), provider=provider, kill_switch=lambda: kill)


def force_signal(monkeypatch, side="CE", bar="2026-10-19 14:50", level=6490.0, setup=sg.SETUP_17):
    monkeypatch.setattr(sg, "evaluate", lambda sym, df, cfg, ws=None: [sg.CxSignal(setup, sym, side, bar, 6500.0, level, {"adx": 30.0})])


def run(eng, now):
    return asyncio.run(eng.run_cycle(now))


NOW = at("2026-10-19 15:00")


def test_enters_atm_option_and_sizes_by_lot(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path)
    r = run(eng, NOW)
    pos = eng.positions("OPEN")[0]
    assert r["entered"] == [pos["id"]] and pos["strike"] == 6500.0 and pos["side"] == "CE"
    assert pos["entry_price"] == 10.2 and pos["units"] == 100 and pos["pool"] == "commodity"
    run(eng, at("2026-10-19 15:05"))
    assert len(eng.positions()) == 1  # the same bar does not enter twice


def test_goldm_units_use_the_quote_unit(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path, FakeProvider("GOLDM", lot=100), cx_symbols="GOLDM")
    run(eng, NOW)
    assert eng.positions("OPEN")[0]["units"] == 10


def test_off_by_default_and_pool_switch(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    assert make(tmp_path, cx_enabled=False).positions() == []
    eng = make(tmp_path, cx_enabled=False)
    run(eng, NOW)
    assert eng.positions() == []
    eng = make(tmp_path, cx_commodity_enabled=False)
    run(eng, NOW)
    assert eng.positions() == []


def test_wide_spread_and_missing_lot_are_skipped(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path, FakeProvider(bid=5.0, ask=10.0))
    run(eng, NOW)
    assert eng.positions() == []


def test_exits_stop_target_invalidation_time(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    cases = [(dict(bid=7.0, ask=7.2), "STOP_LOSS"), (dict(bid=15.5, ask=15.7), "TARGET")]
    for chain_px, reason in cases:
        prov = FakeProvider()
        eng = make(tmp_path, prov)
        run(eng, NOW)
        prov.bid, prov.ask = chain_px["bid"], chain_px["ask"]
        monkeypatch.setattr(sg, "evaluate", lambda *a, **k: [])
        run(eng, at("2026-10-19 15:05"))
        p = eng.positions("CLOSED")[0]
        assert p["exit_reason"] == reason and p["charges"] > 0
        assert p["net_pnl"] == pytest.approx(p["gross_pnl"] - p["charges"], abs=0.01)
        force_signal(monkeypatch)
    prov = FakeProvider()
    eng = make(tmp_path, prov)
    run(eng, NOW)
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: [])
    prov.price = 6480.0  # underlying closes through the invalidation level 6490
    run(eng, at("2026-10-19 15:05"))
    assert eng.positions("CLOSED")[0]["exit_reason"] == "INVALIDATED"
    force_signal(monkeypatch)
    prov = FakeProvider()
    eng = make(tmp_path, prov, cx_max_hold_minutes=30)
    run(eng, NOW)
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: [])
    run(eng, at("2026-10-19 15:35"))
    assert eng.positions("CLOSED")[0]["exit_reason"] == "TIME_STOP"


def test_square_off_at_exchange_time(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    prov = FakeProvider(last_bar="2026-10-19 23:10")
    eng = make(tmp_path, prov, cx_mcx_entry_cutoff="23:14")
    run(eng, at("2026-10-19 23:12"))
    assert len(eng.positions("OPEN")) == 1
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: [])
    run(eng, at("2026-10-19 23:16"))
    assert eng.positions("CLOSED")[0]["exit_reason"] == "SQUARE_OFF"


def test_no_entry_after_cutoff_or_when_session_closed(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path, FakeProvider(last_bar="2026-10-19 22:40"))
    run(eng, at("2026-10-19 22:45"))
    assert eng.positions() == []
    eng = make(tmp_path)
    run(eng, at("2026-10-17 12:00"))  # Saturday
    assert eng.positions() == []


def test_kill_switch_blocks_entry_and_closes_open(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path, kill=True)
    run(eng, NOW)
    assert eng.positions() == []
    eng = make(tmp_path)
    run(eng, NOW)
    assert asyncio.run(eng.square_off_all()) == 1
    assert eng.positions("CLOSED")[0]["exit_reason"] == "KILL_SWITCH"


def test_loss_cap_is_per_pool(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    prov = FakeProvider()
    eng = make(tmp_path, prov, cx_loss_cap_commodity=500.0)
    run(eng, NOW)
    prov.bid, prov.ask = 7.0, 7.2
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: [])
    run(eng, at("2026-10-19 15:05"))  # stop-loss: about -320 gross plus charges
    assert eng.pool_day_pnl("commodity") < 0
    eng.runtime.set("cx_loss_cap_commodity", 100.0)
    assert eng.loss_cap_tripped("commodity") and not eng.loss_cap_tripped("currency")
    force_signal(monkeypatch, bar="2026-10-19 15:10")
    prov.last_bar = "2026-10-19 15:10"
    run(eng, at("2026-10-19 15:15"))
    assert len(eng.positions()) == 1  # blocked by the pool cap


def test_summary_reports_pools_and_sessions(tmp_path):
    s = make(tmp_path).summary()
    assert set(s["pools"]) == {"commodity", "currency"} and s["enabled"] is True
    assert s["pools"]["commodity"]["loss_cap"] == 15000.0 and s["pools"]["currency"]["loss_cap"] == 5000.0
    assert set(s["sessions"]) == {"MCX", "CURRENCY"}


def test_pick_leg_uses_parity_atm_and_skips_unquoted_legs():
    q = {"top_bid_price": 4.0, "top_ask_price": 4.2}
    oc = {"100": {"ce": {"last_price": 9.0, **q}, "pe": {"last_price": 1.0, **q}},
          "110": {"ce": {"last_price": 5.0}, "pe": {"last_price": 5.1}},               # parity ATM, but no bid/ask
          "120": {"ce": {"last_price": 2.0, **q}, "pe": {"last_price": 9.0, **q}}}
    assert ce.atm_strike(oc, 500.0) == 110.0   # the candle price (far off) is ignored when parity is available
    assert ce.pick_leg(oc, "CE", 500.0)["strike"] in (100.0, 120.0)  # nearest quoted strike
    assert ce.pick_leg({"100": {"ce": {"last_price": 1.0}}}, "CE", 100.0)["strike"] == 100.0  # none quoted: ATM returned for the skip log
    assert ce.pick_leg({}, "CE", 100.0) is None


def test_missing_oi_is_unknown_not_illiquid(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path, cx_min_oi=100.0)
    run(eng, NOW)  # fake chain legs carry no OI: allowed
    assert len(eng.positions("OPEN")) == 1


def test_known_low_oi_blocks(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    prov = FakeProvider()
    orig = prov.chain

    async def chain(symbol, contract, now):
        expiry, oc = await orig(symbol, contract, now)
        for row in oc.values():
            for leg in row.values():
                leg["oi"] = 5
        return expiry, oc

    prov.chain = chain
    eng = make(tmp_path, prov, cx_min_oi=100.0)
    run(eng, NOW)
    assert eng.positions() == []


def test_candles_come_from_the_future_the_option_expiry_belongs_to(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    asked = []

    class P(FakeProvider):
        async def contracts(self, symbols, today):
            c = lambda sid, exp: {"symbol": "CRUDEOIL", "security_id": sid, "expiry": exp, "lot_size": 1, "lot_size_known": True, "display": sid}
            return {s: [c("oct", "2026-10-19"), c("nov", "2026-11-19"), c("dec", "2026-12-18")][1:] for s in symbols}

        async def candles(self, symbol, contract, now):
            asked.append(contract["security_id"])
            return await super().candles(symbol, contract, now)

        async def chain(self, symbol, contract, now):
            expiry, oc = await super().chain(symbol, contract, now)
            return "2026-12-15", oc  # options expiring mid-December are written on the DEC future

    eng = make(tmp_path, P())
    run(eng, NOW)
    assert asked == ["nov", "dec"]
    assert eng.positions("OPEN")[0]["future_security_id"] == "dec"


def test_completed_bars_drops_the_forming_bar():
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2026-10-19 14:50", "2026-10-19 14:55"]), "close": [1, 2]})
    assert len(ce.completed_bars(df, at("2026-10-19 14:58"))) == 1
    assert len(ce.completed_bars(df, at("2026-10-19 15:00"))) == 2


def test_overview_lists_open_closed_and_decisions(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    eng = make(tmp_path)
    run(eng, NOW)
    o = eng.overview()
    assert len(o["open_positions"]) == 1 and o["closed_today"] == [] and o["settings"]["symbols"] == ["CRUDEOIL"]
    assert o["summary"]["open_positions"] == 1


def test_currency_is_parked_everywhere(tmp_path, monkeypatch):
    force_signal(monkeypatch)
    prov = FakeProvider("USDINR", lot=1000)
    eng = make(tmp_path, prov, cx_symbols="USDINR,CRUDEOIL", cx_currency_enabled=True)
    assert eng.symbols() == ["CRUDEOIL"] and not eng.pool_enabled("currency")
    u = ce.ci.UNDERLYINGS["USDINR"]
    assert eng.entry_block(u, NOW, [])[0] == "PARKED"
    run(eng, NOW)
    assert all(p["symbol"] != "USDINR" for p in eng.positions())
    assert eng.summary()["pools"]["currency"]["parked"] is True
    assert RuntimeSettings(str(tmp_path / "d.db")).get("cx_symbols") == "CRUDEOIL,GOLDM"
