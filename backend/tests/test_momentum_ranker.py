import pytest
from app.services.momentum_ranker import MomentumRanker, StockMomentumProfile

def test_momentum_ranker_bullish_and_bearish_categorization():
    ranker = MomentumRanker()

    # Sample live quotes from Dhan marketfeed
    quotes = {
        # Strong Bullish Leader (+2.0%, above VWAP, near day high)
        "RELIANCE": {
            "last_price": 3060.0,
            "ohlc": {"open": 3000.0, "high": 3070.0, "low": 2990.0, "close": 3000.0},
            "average_price": 3030.0,
            "volume": 2500000
        },
        # Strong Bearish Laggard (-2.5%, below VWAP, near day low)
        "TATASTEEL": {
            "last_price": 140.0,
            "ohlc": {"open": 145.0, "high": 146.0, "low": 139.5, "close": 143.6},
            "average_price": 142.5,
            "volume": 8000000
        },
        # Choppy Sideways Stock (+0.1%, at VWAP, middle of range)
        "INFY": {
            "last_price": 1902.0,
            "ohlc": {"open": 1900.0, "high": 1910.0, "low": 1895.0, "close": 1900.0},
            "average_price": 1901.0,
            "volume": 500000
        },
        # Counter-trend / Weak (+0.3%, but below VWAP and rejected from high)
        "HDFCBANK": {
            "last_price": 1655.0,
            "ohlc": {"open": 1660.0, "high": 1675.0, "low": 1650.0, "close": 1650.0},
            "average_price": 1665.0,
            "volume": 1200000
        }
    }

    rankings = ranker.rank_stocks(quotes)

    assert "RELIANCE" in rankings.top_bullish
    assert "TATASTEEL" in rankings.top_bearish
    assert "INFY" not in rankings.top_bullish
    assert "INFY" not in rankings.top_bearish
    assert rankings.get_bias("RELIANCE") == "BULLISH"
    assert rankings.get_bias("TATASTEEL") == "BEARISH"
    assert rankings.get_bias("INFY") == "NEUTRAL"
    assert rankings.get_bias("HDFCBANK") == "NEUTRAL"

def test_momentum_ranker_limits_to_top_n():
    ranker = MomentumRanker(top_n=2)
    quotes = {}
    for i in range(10):
        # Create 10 bullish stocks with varying change_pct
        pct = (i + 1) * 0.5
        ltp = 100.0 * (1.0 + pct / 100.0)
        quotes[f"STOCK_{i}"] = {
            "last_price": ltp,
            "ohlc": {"open": 100.0, "high": ltp + 1.0, "low": 99.0, "close": 100.0},
            "average_price": (100.0 + ltp) / 2.0,
            "volume": 100000
        }

    rankings = ranker.rank_stocks(quotes)
    # Only top 2 highest momentum stocks should be in top_bullish
    assert len(rankings.top_bullish) == 2
    assert "STOCK_9" in rankings.top_bullish
    assert "STOCK_8" in rankings.top_bullish
    assert "STOCK_0" not in rankings.top_bullish
