import asyncio
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from app.services import market_hours
from app.services import swing_signals as sg
from app.services.charges_calculator import calculate_equity_delivery_charges
from app.services.runtime_settings import RuntimeSettings
from app.services.swing_engine import SwingEngine, SwingStore
from app.services.swing_report import bootstrap_mean_ci, max_drawdown, summarise, wilson_interval
from app.services.telemetry import Telemetry

IST = market_hours.IST


def make_bars(closes, start="2026-01-01", volume=1_000_000.0, gaps=None):
    """Daily bars where each open is the previous close; ``gaps`` maps index -> open override."""
    closes = list(map(float, closes))
    dates = pd.bdate_range(start, periods=len(closes)).strftime("%Y-%m-%d")
    rows = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        if gaps and i in gaps:
            o = gaps[i]
        rows.append((dates[i], o, max(o, c) + 0.5, min(o, c) - 0.5, c, volume))
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def v_shape(down=70, up=15):
    """Falls from 200 for ``down`` bars, then rallies: the Supertrend flips up inside the rally."""
    return [200 - i * 1.0 for i in range(down)] + [200 - down + 1 + i * 2.0 for i in range(up)]


def flip_index(df, cfg):
    st = sg.supertrend(df, cfg.atr_period, cfg.atr_mult)
    t = st["trend"].tolist()
    for i in range(1, len(t)):
        if t[i] == 1 and t[i - 1] == -1:
            return i
    raise AssertionError("no flip in fixture")


_n = [0]


def engine(tmp_path, **settings):
    _n[0] += 1  # a fresh database per engine: settings and positions never leak between engines in one test
    db = str(tmp_path / f"s{_n[0]}.db")
    rt = RuntimeSettings(db)
    base = {"swing_enabled": True, "swing_sma_filter_days": 0, "swing_min_avg_volume": 0, "swing_min_price": 0,
            "swing_slippage_bps": 10, "swing_earnings_blackout_days": 0, "swing_max_hold_days": 20}
    for k, v in {**base, **settings}.items():
        rt.set(k, v)
    return SwingEngine(db, rt, Telemetry(db, rt))


def run_days(eng, bars_by_symbol, upto_index, start_index=0, scan=True):
    dates = sorted({d for df in bars_by_symbol.values() for d in df["date"]})
    out = []
    for d in dates[start_index:upto_index + 1]:
        out.append(eng.process_day(datetime.strptime(d, "%Y-%m-%d").date(), bars_by_symbol, scan=scan))
    return out


CFG = sg.Setup15Config(atr_period=3, atr_mult=1.0, sma_filter_days=0, min_price=0, min_avg_volume=0)


# ---------------------------------------------------------------- signal
def test_supertrend_flips_up_in_a_rally_and_stays_down_in_a_fall():
    df = make_bars(v_shape())
    st = sg.supertrend(df, 3, 1.0)
    assert (st["trend"].iloc[10:60] == -1).all()
    assert st["trend"].iloc[-1] == 1
    assert st["line"].iloc[-1] < df["close"].iloc[-1]  # the stop sits under price in an uptrend


def test_supertrend_has_no_lookahead():
    df = make_bars(v_shape())
    full = sg.supertrend(df, 3, 1.0)["trend"].tolist()
    for i in range(20, len(df)):
        assert sg.supertrend(df.iloc[: i + 1], 3, 1.0)["trend"].iloc[-1] == full[i]


def test_signal_only_on_the_flip_bar():
    df = make_bars(v_shape())
    i = flip_index(df, CFG)
    assert sg.evaluate_setup15("X", df.iloc[: i + 1], CFG) is not None
    assert sg.evaluate_setup15("X", df.iloc[:i], CFG) is None          # the bar before
    assert sg.evaluate_setup15("X", df.iloc[: i + 2], CFG) is None     # the bar after: already up


def test_filters_block_the_signal():
    df = make_bars(v_shape())
    sub = df.iloc[: flip_index(df, CFG) + 1]
    sig = sg.evaluate_setup15("X", sub, CFG)
    assert 0 < sig.stop < sig.close
    assert sg.evaluate_setup15("X", sub, sg.Setup15Config(3, 1.0, 0, 0, 5_000_000)) is None   # volume
    assert sg.evaluate_setup15("X", sub, sg.Setup15Config(3, 1.0, 0, 1000, 0)) is None        # price
    assert sg.evaluate_setup15("X", sub, sg.Setup15Config(3, 1.0, 60, 0, 0)) is None          # still below the 60-bar average


def test_too_short_history_gives_no_signal():
    assert sg.evaluate_setup15("X", make_bars([100, 101, 102]), CFG) is None


# ---------------------------------------------------------------- costs
def test_equity_delivery_charges_match_the_schedule():
    c = calculate_equity_delivery_charges(1000, 1000, 100)
    assert c.stt == 200.0 and c.stamp_duty == 15.0 and c.exchange_fee == 6.14
    assert c.total_charges == pytest.approx(200 + 15 + 6.14 + 0.2 + 1.14 + 15.34, abs=0.02)
    assert 0.2 < c.total_charges / 100000 * 100 < 0.3  # about 0.24% of the position value
    assert calculate_equity_delivery_charges(0, 10, 5).total_charges == 0.0
    assert calculate_equity_delivery_charges(10, 10, 0).total_charges == 0.0


# ---------------------------------------------------------------- engine
def fixture_with_flip(extra_after=()):
    base = v_shape()
    df = make_bars(base)
    i = flip_index(df, CFG)
    return base, i


def test_signal_queues_then_fills_at_next_open_plus_slippage(tmp_path):
    base, i = fixture_with_flip()
    closes = base + [base[-1] + 2.0] * 3
    bars = {"AAA": make_bars(closes)}
    eng = engine(tmp_path)
    run_days(eng, bars, i)
    pend = eng.positions("PENDING")
    assert len(pend) == 1 and pend[0]["signal_day"] == bars["AAA"]["date"].iloc[i]
    assert pend[0]["stop"] < bars["AAA"]["close"].iloc[i]
    run_days(eng, bars, i + 1, start_index=i + 1, scan=False)
    pos = eng.positions("OPEN")[0]
    expected = round(bars["AAA"]["open"].iloc[i + 1] * 1.001, 2)
    assert pos["entry_price"] == expected and pos["opened_day"] == bars["AAA"]["date"].iloc[i + 1]
    risk = pos["entry_price"] - pos["initial_stop"]
    assert pos["qty"] == min(int(5000 // risk), int(100000 // pos["entry_price"]))


def test_gap_below_stop_cancels_the_entry(tmp_path):
    base, i = fixture_with_flip()
    bars = {"AAA": make_bars(base + [base[-1]] * 3)}
    eng = engine(tmp_path)
    run_days(eng, bars, i)
    stop = eng.positions("PENDING")[0]["stop"]
    bars["AAA"].loc[i + 1, "open"] = stop - 1
    run_days(eng, bars, i + 1, start_index=i + 1, scan=False)
    assert eng.positions("OPEN") == [] and eng.positions("CANCELLED")[0]["exit_reason"] == "GAP_THROUGH_STOP"


def test_stop_hit_inside_the_bar_fills_at_the_stop(tmp_path):
    base, i = fixture_with_flip()
    closes = base + [base[-1] + 2.0, base[-1] + 4.0, base[-1] + 6.0]
    bars = {"AAA": make_bars(closes)}
    eng = engine(tmp_path)
    run_days(eng, bars, i + 1)           # signal, then fill
    pos = eng.positions("OPEN")[0]
    stop = pos["stop"]
    df = bars["AAA"]
    df.loc[i + 2, ["open", "high", "low", "close"]] = [stop + 1.0, stop + 2.0, stop - 3.0, stop - 2.0]
    run_days(eng, bars, i + 2, start_index=i + 2, scan=False)
    closed = eng.positions("CLOSED")[0]
    assert closed["exit_reason"] == "STOP" and closed["exit_price"] == round(stop * 0.999, 2)
    assert closed["net_pnl"] < 0 and closed["charges"] > 0


def test_stop_gapped_through_fills_at_the_open(tmp_path):
    base, i = fixture_with_flip()
    bars = {"AAA": make_bars(base + [base[-1] + 2.0, base[-1] + 4.0, base[-1] + 6.0])}
    eng = engine(tmp_path)
    run_days(eng, bars, i + 1)
    stop = eng.positions("OPEN")[0]["stop"]
    bars["AAA"].loc[i + 2, ["open", "high", "low", "close"]] = [stop - 5.0, stop - 4.0, stop - 8.0, stop - 6.0]
    run_days(eng, bars, i + 2, start_index=i + 2, scan=False)
    closed = eng.positions("CLOSED")[0]
    assert closed["exit_reason"] == "STOP_GAP" and closed["exit_price"] == round((stop - 5.0) * 0.999, 2)


def test_stop_trails_up_with_the_supertrend_and_never_down(tmp_path):
    base, i = fixture_with_flip()
    closes = base + [base[-1] + 2.0 * k for k in range(1, 12)]
    bars = {"AAA": make_bars(closes)}
    eng = engine(tmp_path)
    stops = []
    for k in range(i, len(closes)):
        run_days(eng, bars, k, start_index=k)
        op = eng.positions("OPEN")
        if op:
            stops.append(op[0]["stop"])
    assert len(stops) >= 5 and stops == sorted(stops) and stops[-1] > stops[0]


def test_close_below_the_trailing_line_exits_on_the_stop_in_the_same_bar(tmp_path):
    # the stop is the Supertrend line, so the close that flips the trend has already traded through the stop that day
    base, i = fixture_with_flip()
    closes = base + [base[-1] + 2.0 * k for k in range(1, 6)]
    bars = {"AAA": make_bars(closes)}
    eng = engine(tmp_path)
    run_days(eng, bars, len(closes) - 1)
    stop = eng.positions("OPEN")[0]["stop"]
    last = len(closes)
    bars["AAA"] = pd.concat([bars["AAA"], make_bars([stop - 3.0], start="2027-01-04")], ignore_index=True)
    bars["AAA"].loc[last, "open"] = closes[-1]
    run_days(eng, bars, last, start_index=last, scan=False)
    assert eng.positions("CLOSED")[0]["exit_reason"] == "STOP"


def test_time_stop_flags_an_exit_after_max_hold_days(tmp_path):
    base = [200 - i for i in range(70)] + [131 + 2 * i for i in range(60)]  # a long steady rally: never stops out
    bars = {"AAA": make_bars(base)}
    eng = engine(tmp_path, swing_max_hold_days=5)
    for k in range(len(base)):
        run_days(eng, bars, k, start_index=k)
        if eng.positions("CLOSED"):
            break
    closed = eng.positions("CLOSED")
    assert closed and closed[0]["exit_reason"] == "TIME_STOP" and closed[0]["hold_days"] == 5


def test_kill_switch_and_switches_block_entries(tmp_path):
    base, i = fixture_with_flip()
    bars = {"AAA": make_bars(base)}
    for kwargs, code in (({"swing_enabled": False}, "SWING_DISABLED"), ({"swing_setup15_enabled": False}, "SETUP_OFF")):
        eng = engine(tmp_path, **kwargs)
        run_days(eng, bars, i)
        assert eng.positions() == []
    eng = engine(tmp_path)
    eng.kill_switch = lambda: True
    assert eng.entry_block("AAA", date(2026, 1, 1), [], 0)[0] == "KILL_SWITCH"


def test_position_limits_and_one_per_symbol(tmp_path):
    base, i = fixture_with_flip()
    bars = {s: make_bars(base) for s in ("AAA", "BBB", "CCC")}
    eng = engine(tmp_path, swing_max_positions=2)
    run_days(eng, bars, i)
    assert len(eng.positions("PENDING")) == 2
    eng2 = engine(tmp_path, swing_max_positions=5, swing_max_new_per_day=1)
    live = [{"symbol": "AAA", "status": "OPEN"}]
    assert eng2.entry_block("AAA", date(2026, 1, 1), live, 0)[0] == "ALREADY_HELD"
    assert eng2.entry_block("ZZZ", date(2026, 1, 1), live, 1)[0] == "MAX_NEW_PER_DAY"


def test_earnings_blackout_blocks_entry(tmp_path):
    eng = engine(tmp_path, swing_earnings_blackout_days=5)
    eng.earnings_dates = lambda sym: ["2026-03-04"]
    assert eng.entry_block("AAA", date(2026, 3, 1), [], 0)[0] == "EARNINGS_BLACKOUT"
    assert eng.entry_block("AAA", date(2026, 2, 20), [], 0) is None
    assert eng.entry_block("AAA", date(2026, 3, 6), [], 0) is None  # results already out


def test_square_off_all_closes_open_and_cancels_pending(tmp_path):
    base, i = fixture_with_flip()
    bars = {"AAA": make_bars(base + [base[-1] + 2.0, base[-1] + 4.0])}
    eng = engine(tmp_path)
    run_days(eng, bars, i + 1)
    assert eng.positions("OPEN")
    n = asyncio.run(eng.square_off_all("KILL_SWITCH"))
    assert n >= 1 and not eng.positions("OPEN") and not eng.positions("PENDING")
    assert eng.positions("CLOSED")[0]["exit_reason"] == "KILL_SWITCH"


def test_results_do_not_depend_on_bars_after_the_replayed_day(tmp_path):
    base, i = fixture_with_flip()
    full = make_bars(base + [base[-1] + 2.0] * 10)
    cut = full.iloc[: i + 3].reset_index(drop=True)
    a = engine(tmp_path)
    run_days(a, {"AAA": full}, i + 2)
    ids_a = [(p["symbol"], p["status"], p.get("entry_price"), p.get("stop")) for p in a.positions()]
    b = engine(tmp_path)
    run_days(b, {"AAA": cut}, i + 2)
    ids_b = [(p["symbol"], p["status"], p.get("entry_price"), p.get("stop")) for p in b.positions()]
    assert ids_a == ids_b


# ---------------------------------------------------------------- cycle
class FakeProvider:
    def __init__(self, store, bars, creds=True):
        self.store, self._bars, self.creds, self.calls = store, bars, creds, 0

    def has_credentials(self): return self.creds
    def symbols(self): return sorted(self._bars)

    async def bars(self, symbols, today):
        self.calls += 1
        return {s: self._bars[s] for s in symbols}


def cycle_engine(tmp_path, bars):
    db = str(tmp_path / "c.db")
    rt = RuntimeSettings(db)
    for k, v in {"swing_enabled": True, "swing_sma_filter_days": 0, "swing_min_avg_volume": 0, "swing_min_price": 0}.items():
        rt.set(k, v)
    store = SwingStore(db)
    return SwingEngine(db, rt, Telemetry(db, rt), provider=FakeProvider(store, bars))


def test_cycle_waits_for_scan_time_then_runs_once(tmp_path):
    base, i = fixture_with_flip()
    df = make_bars(base)
    day = datetime.strptime(df["date"].iloc[i], "%Y-%m-%d").date()
    eng = cycle_engine(tmp_path, {"AAA": df.iloc[: i + 1].reset_index(drop=True)})
    early = asyncio.run(eng.run_cycle(datetime(day.year, day.month, day.day, 14, 0, tzinfo=IST)))
    assert early["status"] == "before_scan_time"
    with market_hours.override_clock(datetime(day.year, day.month, day.day, 16, 30, tzinfo=IST)):
        res = asyncio.run(eng.run_cycle(datetime(day.year, day.month, day.day, 16, 30, tzinfo=IST)))
        assert res["status"] == "ok" and len(res["days"][0]["queued"]) == 1
        again = asyncio.run(eng.run_cycle(datetime(day.year, day.month, day.day, 17, 0, tzinfo=IST)))
    assert again["status"] == "up_to_date" and eng.store.get_meta("last_processed_day") == day.isoformat()


def test_cycle_without_credentials_reports_it(tmp_path):
    eng = cycle_engine(tmp_path, {"AAA": make_bars([100] * 40)})
    eng.provider.creds = False
    res = asyncio.run(eng.run_cycle(datetime(2026, 10, 14, 17, 0, tzinfo=IST)))
    assert res["status"] == "no_credentials"


# ---------------------------------------------------------------- store / report
def test_store_round_trips_bars_and_positions(tmp_path):
    s = SwingStore(str(tmp_path / "x.db"))
    df = make_bars([100, 101, 102])
    s.upsert_bars("AAA", df)
    s.upsert_bars("AAA", df.iloc[1:])  # overlap is replaced, not duplicated
    assert len(s.bars("AAA")) == 3 and s.last_bar_day("AAA") == df["date"].iloc[-1]
    s.save_position({"id": "p1", "symbol": "AAA", "status": "OPEN", "signal_day": "2026-01-01"})
    assert s.positions()[0]["id"] == "p1"
    mem = SwingStore(None)
    mem.upsert_bars("AAA", df)
    assert len(mem.bars("AAA")) == 3


def test_report_statistics():
    lo, hi = wilson_interval(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert max_drawdown([100, -300, 50], 1000) == pytest.approx(300 / 1100, rel=1e-3)
    lo, hi = bootstrap_mean_ci([1.0] * 10)
    assert lo == hi == 1.0
    trades = [{"status": "CLOSED", "id": str(i), "closed_day": f"2026-02-{i + 1:02d}", "net_pnl": 100.0 if i % 2 else -50.0,
               "r_multiple": 1.0 if i % 2 else -0.5, "return_pct": 2.0 if i % 2 else -1.0, "hold_days": 5, "exit_reason": "STOP", "charges": 10}
              for i in range(10)]
    s = summarise(trades)
    assert s["trades"] == 10 and s["win_rate_pct"] == 50.0 and not s["enough_trades"] and "hypothesis" in s["verdict_note"]
    assert s["profit_factor"] == 2.0 and s["expectancy_r"] == 0.25
    assert summarise([]) == {"trades": 0, "enough_trades": False}


# ---------------------------------------------------------------- close exit mode
def _held_position(tmp_path, **settings):
    base, i = fixture_with_flip()
    closes = base + [base[-1] + 2.0 * k for k in range(1, 6)]
    bars = {"AAA": make_bars(closes)}
    eng = engine(tmp_path, **settings)
    run_days(eng, bars, len(closes) - 1)
    return eng, bars, closes


def test_close_mode_ignores_a_wick_through_the_line(tmp_path):
    eng, bars, closes = _held_position(tmp_path, swing_exit_mode="close")
    stop = eng.positions("OPEN")[0]["stop"]
    n = len(closes)
    nxt = closes[-1] + 1.0
    bars["AAA"] = pd.concat([bars["AAA"], make_bars([nxt], start="2027-01-04")], ignore_index=True)
    bars["AAA"].loc[n, ["open", "high", "low", "close"]] = [closes[-1], nxt + 1, stop - 1.0, nxt]  # wick below the line, close above
    run_days(eng, bars, n, start_index=n, scan=False)
    assert eng.positions("OPEN") and not eng.positions("CLOSED")
    eng2, bars2, _ = _held_position(tmp_path, swing_exit_mode="stop")
    bars2["AAA"] = bars["AAA"]
    run_days(eng2, bars2, n, start_index=n, scan=False)
    assert eng2.positions("CLOSED")[0]["exit_reason"] == "STOP"


def test_close_mode_exits_at_the_next_open_after_a_close_below_the_line(tmp_path):
    eng, bars, closes = _held_position(tmp_path, swing_exit_mode="close")
    stop = eng.positions("OPEN")[0]["stop"]
    n = len(closes)
    rows = make_bars([stop - 1.0, stop - 2.0], start="2027-01-04")
    rows.loc[0, ["open", "high", "low", "close"]] = [closes[-1], closes[-1], stop - 1.5, stop - 1.0]
    rows.loc[1, "open"] = stop - 1.2
    bars["AAA"] = pd.concat([bars["AAA"], rows], ignore_index=True)
    run_days(eng, bars, n, start_index=n, scan=False)
    pos = eng.positions("OPEN")[0]
    assert pos["exit_pending"] == "TREND_FLIP"
    run_days(eng, bars, n + 1, start_index=n + 1, scan=False)
    closed = eng.positions("CLOSED")[0]
    assert closed["exit_reason"] == "TREND_FLIP" and closed["exit_price"] == round((stop - 1.2) * 0.999, 2)


def test_close_mode_max_loss_stop_caps_a_bad_day(tmp_path):
    eng, bars, closes = _held_position(tmp_path, swing_exit_mode="close", swing_close_mode_max_loss_pct=5)
    pos = eng.positions("OPEN")[0]
    n = len(closes)
    bars["AAA"] = pd.concat([bars["AAA"], make_bars([pos["entry_price"] * 0.8], start="2027-01-04")], ignore_index=True)
    bars["AAA"].loc[n, ["open", "high", "low", "close"]] = [closes[-1], closes[-1], pos["entry_price"] * 0.8, pos["entry_price"] * 0.8]
    run_days(eng, bars, n, start_index=n, scan=False)
    closed = eng.positions("CLOSED")[0]
    assert closed["exit_reason"] == "STOP" and closed["exit_price"] == round(pos["hard_stop"] * 0.999, 2)


# ---------------------------------------------------------------- Dhan daily candles
@pytest.mark.asyncio
async def test_fetch_daily_candles_parses_dhan_response():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.dhan_client import DhanClient

    client = DhanClient()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"open": [10, 11], "high": [12, 13], "low": [9, 10], "close": [11, 12], "volume": [100, 200],
                              "start_Time": [1760639400, 1760725800]}  # 2025-10-16 / 17 18:30 UTC = IST midnight the next day
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = resp
        df = await client.fetch_daily_candles("cid", "tok", "13061", "NSE_EQ", "EQUITY", "2025-10-01", "2025-10-17")
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"] and len(df) == 2
    body = post.call_args.kwargs["json"]
    assert post.call_args.args[0] == "/charts/historical" and body["expiryCode"] == 0 and body["fromDate"] == "2025-10-01"
    assert df["close"].tolist() == [11, 12]
    resp.status_code = 500
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = resp
        assert (await client.fetch_daily_candles("cid", "tok", "1", "NSE_EQ")).empty
    await client.close()
