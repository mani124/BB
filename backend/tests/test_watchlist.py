import asyncio
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.services import watchlist as wl
from app.services.runtime_settings import RuntimeSettings


def _bars(n=120, squeeze=False, nr7=False, volume=2_000_000, price=500.0):
    rng = np.random.default_rng(7)
    close = price + np.cumsum(rng.normal(0, 6.0, n))
    if squeeze:
        close[-25:] = close[-25] + rng.normal(0, 0.4, 25)
    else:
        close[-25:] = close[-25] + np.cumsum(rng.normal(0, 25.0, 25))  # volatile finish: wide bands
    high, low = close + 5, close - 5
    if not nr7:
        high[-1], low[-1] = close[-1] + 12, close[-1] - 12
    if nr7:
        high[-1], low[-1] = close[-1] + 0.5, close[-1] - 0.5
    dates = pd.date_range(end="2026-10-19", periods=n, freq="B")
    return pd.DataFrame({"date": dates, "open": close, "high": high, "low": low, "close": close,
                         "volume": volume})


def test_squeezed_stock_qualifies_and_loose_one_does_not():
    assert wl.screen_symbol("TIGHT", _bars(squeeze=True)) is not None
    assert wl.screen_symbol("LOOSE", _bars(), use_nr7=False) is None


def test_nr7_counts_only_when_enabled():
    b = _bars(nr7=True)
    c = wl.screen_symbol("NR", b, bw_percentile_max=1.0)
    assert c is not None and c.nr7 and any("NR7" in r for r in c.reasons)
    assert wl.screen_symbol("NR", b, bw_percentile_max=1.0, use_nr7=False) is None


def test_illiquid_and_short_history_are_skipped():
    assert wl.screen_symbol("THIN", _bars(squeeze=True, volume=1_000), min_avg_value_cr=50.0) is None
    assert wl.screen_symbol("NEW", _bars(n=40, squeeze=True)) is None


def test_screen_ranks_tightest_first_and_caps_size():
    data = {f"S{i}": _bars(squeeze=True) for i in range(5)}
    out = wl.screen(data, size=3)
    assert len(out) == 3
    assert [c.bw_percentile for c in out] == sorted(c.bw_percentile for c in out)


def test_next_trading_day_skips_weekend():
    assert wl.next_trading_day(date(2026, 10, 16)).weekday() == 0  # Friday -> Monday


class _Provider:
    def __init__(self, data, creds=True):
        self.data, self.creds = data, creds

    def has_credentials(self):
        return self.creds

    def symbols(self):
        return sorted(self.data)

    async def bars(self, symbols, today):
        return {s: self.data[s] for s in symbols}


def _service(tmp_path, data, creds=True):
    rt = RuntimeSettings(None)
    return wl.WatchlistService(wl.WatchlistStore(str(tmp_path / "watchlist.json")), rt, _Provider(data, creds)), rt


def test_build_saves_list_for_next_trading_day_and_only_that_day(tmp_path):
    svc, _ = _service(tmp_path, {"AAA": _bars(squeeze=True), "BBB": _bars()})
    now = datetime(2026, 10, 19, 16, 30)
    res = asyncio.run(svc.run_cycle(now))
    assert res["status"] == "built"
    target = wl.next_trading_day(date(2026, 10, 19))  # 2026-10-20 is a market holiday, so this is the 21st
    assert target == date(2026, 10, 21)
    assert svc.symbols_for(target) == ["AAA"]
    assert svc.symbols_for(date(2026, 10, 19)) == []  # a list is only valid for the day it was built for
    assert svc.symbols_for(date(2026, 10, 22)) == []  # never reused when stale
    assert asyncio.run(svc.run_cycle(now))["status"] == "up_to_date"


def test_cycle_waits_for_final_bar_and_respects_switch(tmp_path):
    svc, rt = _service(tmp_path, {"AAA": _bars(squeeze=True)})
    assert asyncio.run(svc.run_cycle(datetime(2026, 10, 19, 15, 45)))["status"] == "before_build_time"  # closed, bar not final
    rt.set("watchlist_enabled", False)
    assert asyncio.run(svc.run_cycle(datetime(2026, 10, 19, 17, 0)))["status"] == "disabled"
    assert svc.symbols_for(date(2026, 10, 21)) == []


def test_late_login_still_gets_a_list_and_no_exact_time_is_needed(tmp_path):
    data = {"AAA": _bars(squeeze=True)}
    svc = wl.WatchlistService(wl.WatchlistStore(str(tmp_path / "w.json")), RuntimeSettings(None), _Provider(data, creds=False))
    evening = datetime(2026, 10, 19, 16, 30)
    assert asyncio.run(svc.run_cycle(evening))["status"] == "no_credentials"   # not logged in at the build time
    svc.provider.creds = True
    late = datetime(2026, 10, 19, 22, 40)                                       # logs in hours later
    assert asyncio.run(svc.run_cycle(late))["status"] == "built"
    assert svc.symbols_for(date(2026, 10, 21)) == ["AAA"]


def test_morning_login_before_close_builds_for_today_and_is_not_rebuilt(tmp_path):
    svc, _ = _service(tmp_path, {"AAA": _bars(squeeze=True)})
    morning = datetime(2026, 10, 21, 8, 30)                                     # trading day, no list yet
    assert svc.target_day(morning) == date(2026, 10, 21)
    assert asyncio.run(svc.run_cycle(morning))["status"] == "built"
    assert svc.symbols_for(date(2026, 10, 21)) == ["AAA"]
    assert asyncio.run(svc.run_cycle(datetime(2026, 10, 21, 11, 0)))["status"] == "up_to_date"
    assert svc.target_day(datetime(2026, 10, 21, 16, 20)) == date(2026, 10, 22)  # after the build time: next day


def test_weekend_targets_next_trading_day(tmp_path):
    svc, _ = _service(tmp_path, {"AAA": _bars(squeeze=True)})
    assert svc.target_day(datetime(2026, 10, 17, 11, 0)) == date(2026, 10, 19)    # Saturday
    assert asyncio.run(svc.run_cycle(datetime(2026, 10, 17, 11, 0)))["status"] == "built"
    assert svc.symbols_for(date(2026, 10, 19)) == ["AAA"]


def test_no_credentials_status(tmp_path):
    svc, _ = _service(tmp_path, {"AAA": _bars(squeeze=True)}, creds=False)
    assert asyncio.run(svc.run_cycle(datetime(2026, 10, 19, 17, 0)))["status"] == "no_credentials"


def test_scanner_checks_watchlist_stocks_for_setup16_only():
    """Wiring check on the scanner source: watchlist-only stocks get no spot seeding and only Setup 16 signals survive."""
    import inspect
    from app.services import scanner_worker
    src = inspect.getsource(scanner_worker.ScannerWorker)
    assert "only_setup16=inst.symbol in s16_only" in src
    assert "detected = [s for s in detected if s.setup_type == SetupType.SETUP_16_OPTION_SQUEEZE_BREAK]" in src
    assert "inst.symbol not in s16_only" in src
