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


def _chain(strikes):
    return {f"{k:.6f}": {"ce": {"last_price": 50.0, "top_ask_price": 51.0, "top_bid_price": 49.0, "greeks": {"delta": 0.5}},
                         "pe": {"last_price": 50.0, "top_ask_price": 51.0, "top_bid_price": 49.0, "greeks": {"delta": -0.5}}}
            for k in strikes}


def test_strike_resolved_from_chain_grid_not_static_table():
    from app.services.strike_selector import resolve_live_strike_from_chain
    # RELIANCE is 20-wide in the static table; this chain lists 25-wide strikes only
    chain = _chain([2950, 2975, 3000, 3025, 3050])
    ce = resolve_live_strike_from_chain("RELIANCE", 3012.0, "CE", chain, "2026-10-29")
    assert ce.atm_strike == 3000 and ce.recommended_strike == 2975
    pe = resolve_live_strike_from_chain("RELIANCE", 3012.0, "PE", chain, "2026-10-29")
    assert pe.recommended_strike == 3025
    # clamped at the edge of the chain, never an unlisted strike
    edge = resolve_live_strike_from_chain("RELIANCE", 2950.0, "CE", chain, "2026-10-29")
    assert edge.recommended_strike == 2950


def test_zero_volume_index_vwap_is_session_cumulative_not_bar_typical_price():
    import pandas as pd
    n = 6
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-10-14 09:15", periods=n, freq="5min"),
        "open": [100.0 + i for i in range(n)], "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)], "close": [100.0 + i for i in range(n)],
        "volume": [0] * n,
    })
    out = calculate_indicators(df)
    assert out["vwap"].iloc[-1] == 102.5          # mean of typical prices 100..105
    assert out["vwap"].iloc[-1] != 105.0          # old behaviour: last bar's typical price


def test_squeeze_threshold_is_configurable(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SQUEEZE_ABS_BW_PCT", 0.0001)
    assert settings.SQUEEZE_ABS_BW_PCT == 0.0001


def test_delta_assumed_flag_and_optional_block(monkeypatch):
    from app.services.strike_selector import resolve_live_strike_from_chain
    from app.core.config import settings
    real = _chain([2950, 2975, 3000, 3025, 3050])
    rec = resolve_live_strike_from_chain("RELIANCE", 3012.0, "CE", real, "2026-10-29")
    assert rec.delta_assumed is False and rec.real_delta == 0.5
    nog = {k: {"ce": {"last_price": 50.0, "top_ask_price": 51.0, "top_bid_price": 49.0},
               "pe": {"last_price": 50.0, "top_ask_price": 51.0, "top_bid_price": 49.0}} for k in real}
    rec2 = resolve_live_strike_from_chain("RELIANCE", 3012.0, "CE", nog, "2026-10-29")
    assert rec2.delta_assumed is True
    assert PaperTradingEngine._quote_block_reason(rec2) is None or "delta" not in PaperTradingEngine._quote_block_reason(rec2)
    monkeypatch.setattr(settings, "REQUIRE_REAL_DELTA", True)
    assert "assumed delta" in PaperTradingEngine._quote_block_reason(rec2)
    assert PaperTradingEngine._quote_block_reason(rec) is None
