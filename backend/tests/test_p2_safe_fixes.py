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
