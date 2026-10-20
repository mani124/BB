import pandas as pd

from scripts.fetch_dhan_index_candles import to_3m


def _minutes(start, n, base=100.0):
    idx = pd.date_range(start, periods=n, freq="1min")
    return pd.DataFrame({"timestamp": idx, "open": [base + i for i in range(n)], "high": [base + i + 0.5 for i in range(n)],
                         "low": [base + i - 0.5 for i in range(n)], "close": [base + i + 0.25 for i in range(n)], "volume": [10] * n})


def test_three_minute_bars_start_at_0915_and_aggregate_ohlcv():
    out = to_3m(_minutes("2026-10-15 09:15", 6))
    assert [t.strftime("%H:%M") for t in out.timestamp] == ["09:15", "09:18"]
    first = out.iloc[0]
    assert first.open == 100.0 and first.close == 102.25 and first.high == 102.5 and first.low == 99.5 and first.volume == 30


def test_bars_outside_the_session_are_dropped_and_duplicates_ignored():
    df = pd.concat([_minutes("2026-10-15 09:10", 8), _minutes("2026-10-15 09:15", 3)])
    out = to_3m(df)
    assert out.timestamp.min().strftime("%H:%M") == "09:15"
    assert len(out) == 1 and out.iloc[0].volume == 30
