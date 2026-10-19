from types import SimpleNamespace

import pandas as pd

from app.api import setup16 as api
from app.services.paper_trader import paper_trader
from tests.test_setup16 import _opt, _eval


def _diag(df, **kw):
    d = {}
    from app.services.setup16 import evaluate_option_squeeze_breakout
    evaluate_option_squeeze_breakout("NIFTY 50", "NIFTY 22500 CE", "CE", df, 22500.0, 22500.0, "2026-10-29", 75, "1",
                                     diag=d, window_start="00:00", window_end="23:59", **kw)
    return d


def test_diag_reports_stage_and_numbers():
    d = _diag(_opt())
    assert d["stage"] == "SIGNAL" and d["stop"] < d["close"]
    assert d["in_squeeze"] is True and d["pct_to_upper"] < 0

    d = _diag(_opt(last_close=100.2))
    assert d["stage"] == "NO_BREAKOUT" and d["pct_to_upper"] > 0 and "upper_bb" in d

    assert _diag(_opt(n=30, wide_early=True, last_close=140.0))["stage"] == "NO_SQUEEZE"
    assert _diag(_opt(last_volume=100))["stage"] == "LOW_VOLUME"
    assert _diag(_opt(n=8))["stage"] == "WARMUP"
    d = {}
    from app.services.setup16 import evaluate_option_squeeze_breakout
    evaluate_option_squeeze_breakout("N", "N 1 CE", "CE", _opt(), 1.0, 1.0, diag=d, window_start="00:00", window_end="00:01")
    assert d["stage"] == "OUT_OF_WINDOW"


def test_overview_ranks_contracts_and_counts_funnel():
    worker = SimpleNamespace(_s16_status={
        "A": {"stage": "NO_BREAKOUT", "in_squeeze": True, "pct_to_upper": 1.2, "updated_ts": 9e12, "strike_symbol": "A"},
        "B": {"stage": "NO_BREAKOUT", "in_squeeze": False, "pct_to_upper": 0.3, "updated_ts": 9e12, "strike_symbol": "B"},
        "C": {"stage": "SIGNAL", "in_squeeze": True, "pct_to_upper": -2.0, "updated_ts": 9e12, "strike_symbol": "C"},
        "D": {"stage": "WARMUP", "updated_ts": 0, "strike_symbol": "D"},
    })
    from app.services import watchlist_registry
    from app.services.watchlist import WatchlistService, WatchlistStore
    watchlist_registry.set_service(WatchlistService(WatchlistStore(None), paper_trader.runtime))
    o = api.build_overview(worker)
    assert o["mode"] in ("off", "index", "stocks", "all")
    assert [c["strike_symbol"] for c in o["contracts"]] == ["C", "A", "B", "D"]
    assert o["funnel"]["NO_BREAKOUT"] == 2 and o["funnel"]["SIGNAL"] == 1 and o["funnel"]["WARMUP"] == 1
    assert o["contracts"][-1]["stale"] is True and o["contracts"][0]["stale"] is False
    assert o["settings"]["stop_pct"] == 12.0
    assert o["open_positions"] == [] and o["stats_all_time"] is None
