import pytest
from datetime import timedelta
from app.services import market_hours
from app.services.momentum_ranker import MomentumRanker
from app.services.strike_selector import is_lot_size_known, recommend_strike
from app.services.paper_trader import PaperTradingEngine
from app.services.option_chart_strategy import evaluate_option_chart_signal
from app.services.indicators import calculate_indicators
from tests.test_option_chart_strategy import create_option_candles, _now


def test_unknown_lot_size_flagged_and_blocked():
    assert not is_lot_size_known("ZZZNOTREAL")
    rec = recommend_strike("ZZZNOTREAL", 500.0, "CE")
    assert rec.lot_size_known is False
    assert "lot size unknown" in PaperTradingEngine._quote_block_reason(rec)
    assert is_lot_size_known("NIFTY 50") or is_lot_size_known("RELIANCE")


def test_expiry_day_cutoff_blocks_late_setup5():
    today = market_hours.now_ist().date().isoformat()
    df = create_option_candles(n=30, base_premium=100.0)
    late = market_hours.now_ist().replace(hour=14, minute=45, second=0, microsecond=0, tzinfo=None)
    df.loc[29] = {"timestamp": late, "open": 101.0, "high": 115.0, "low": 100.5, "close": 114.0, "volume": 45000}
    ind = calculate_indicators(df)
    kw = dict(symbol="RELIANCE", strike_symbol="RELIANCE 3000 CE", option_type="CE", option_df=ind,
              underlying_price=2985.0, strike_price=3000.0, lot_size=500, option_security_id="1")
    assert evaluate_option_chart_signal(expiry_date=today, **kw) is None
    assert evaluate_option_chart_signal(expiry_date="2026-10-29", **kw) is not None


def _quote(ltp, prev_close, net_change=None):
    q = {"last_price": ltp, "ohlc": {"open": ltp, "high": ltp, "low": ltp, "close": prev_close},
         "average_price": ltp, "volume": 1000}
    if net_change is not None:
        q["net_change"] = net_change
    return q


def test_ranker_prefers_net_change_when_prev_close_stale_and_skips_implausible():
    r = MomentumRanker()
    ranks = r.rank_stocks({
        "AAA": _quote(110.0, 50.0, net_change=10.0),   # stale close would say +120%
        "BBB": _quote(300.0, 100.0),                    # +200% with no cross-check: implausible
    })
    dump = str(ranks.model_dump())
    assert "BBB" not in dump
    assert "AAA" in dump   # +10% once prev close is corrected to 100


def test_strike_step_is_derived_from_the_chain():
    from app.services.strike_selector import derive_strike_step_from_chain, resolve_live_strike_from_chain
    oc = {f"{k}.000000": {"ce": {"security_id": i, "last_price": 10.0, "top_ask_price": 10.0},
                          "pe": {"security_id": i + 100, "last_price": 10.0, "top_ask_price": 10.0}}
          for i, k in enumerate(range(2400, 2600, 25))}
    assert derive_strike_step_from_chain(oc) == 25
    assert derive_strike_step_from_chain({}) is None
    assert derive_strike_step_from_chain({"2500": {}}) is None
    assert derive_strike_step_from_chain({"2400": {}, "2500": {}}) is None   # sparse: one gap only
    # a symbol whose static step differs: ATM must follow the chain's 25 interval
    rec = resolve_live_strike_from_chain("RELIANCE", 2512.0, "CE", oc, strike_preference="ATM")
    assert rec.recommended_strike == 2500
    rec = resolve_live_strike_from_chain("RELIANCE", 2514.0, "CE", oc, strike_preference="ATM")
    assert rec.recommended_strike == 2525


def _index_bars(n=30):
    import pandas as pd
    from datetime import datetime, timedelta
    rows = []
    for i in range(n):
        p = 22000.0 + 10.0 * i                      # steady drift, no volume (Dhan index candles)
        rows.append({"timestamp": datetime(2026, 10, 14, 9, 15) + timedelta(minutes=5 * i),
                     "open": p - 2, "high": p + 3, "low": p - 3, "close": p, "volume": 0})
    return pd.DataFrame(rows)


def test_volumeless_index_vwap_is_session_running_mean_not_current_bar():
    from app.services.indicators import calculate_indicators
    df = calculate_indicators(_index_bars())
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    assert df["vwap"].iloc[-1] == pytest.approx(tp.mean())
    assert df["vwap"].iloc[-1] < tp.iloc[-1]        # lags a rising market (old value == tp.iloc[-1])


def test_squeeze_is_relative_not_a_fixed_5_percent():
    from app.services.strategy_engine import _in_squeeze
    # 5m index bandwidth is typically ~0.5%: old rule called 0.9% (vs a 0.3% minimum) a squeeze
    assert not _in_squeeze(0.9, 0.3)
    assert _in_squeeze(0.35, 0.3)
    assert _in_squeeze(0.0, 0.0)
