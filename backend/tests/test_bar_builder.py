from datetime import datetime

from app.services.bar_builder import BarBuilder, slot_start


def _min(h, m, o, hi, lo, c, v=1):
    return {"timestamp": datetime(2026, 10, 15, h, m), "open": o, "high": hi, "low": lo, "close": c, "volume": v}


def test_slots_sit_on_the_0915_grid():
    assert slot_start(datetime(2026, 10, 15, 9, 15, 40), 3) == datetime(2026, 10, 15, 9, 15)
    assert slot_start(datetime(2026, 10, 15, 9, 17, 59), 3) == datetime(2026, 10, 15, 9, 15)
    assert slot_start(datetime(2026, 10, 15, 9, 18), 3) == datetime(2026, 10, 15, 9, 18)
    assert slot_start(datetime(2026, 10, 15, 15, 29), 3) == datetime(2026, 10, 15, 15, 27)


def test_seed_aggregates_one_minute_bars_and_keeps_the_unfinished_slot_as_forming():
    b = BarBuilder(3)
    rows = [_min(9, 15, 100, 102, 99, 101), _min(9, 16, 101, 105, 100, 104), _min(9, 17, 104, 104, 98, 99), _min(9, 18, 99, 100, 97, 98)]
    n = b.seed(rows, now=datetime(2026, 10, 15, 9, 19, 30))
    assert n == 1
    first = b.bars[0]
    assert first["timestamp"] == datetime(2026, 10, 15, 9, 15)
    assert (first["open"], first["high"], first["low"], first["close"]) == (100, 105, 98, 99)
    assert b.forming["timestamp"] == datetime(2026, 10, 15, 9, 18) and b.forming["close"] == 98


def test_seed_drops_bars_outside_the_session():
    b = BarBuilder(3)
    n = b.seed([_min(9, 10, 1, 1, 1, 1), _min(9, 15, 100, 101, 99, 100), _min(15, 31, 1, 1, 1, 1)], now=datetime(2026, 10, 15, 16, 0))
    assert n == 1 and b.bars[0]["timestamp"] == datetime(2026, 10, 15, 9, 15)


def test_live_prices_build_bars_and_report_completion_once():
    b = BarBuilder(3)
    assert b.update(100.0, now=datetime(2026, 10, 15, 10, 0, 5)) is False
    assert b.update(103.0, now=datetime(2026, 10, 15, 10, 1, 30)) is False
    assert b.update(99.0, now=datetime(2026, 10, 15, 10, 2, 59)) is False
    assert b.update(101.0, now=datetime(2026, 10, 15, 10, 3, 1)) is True      # a new slot began: the 10:00 bar is complete
    assert b.update(102.0, now=datetime(2026, 10, 15, 10, 3, 40)) is False
    done = b.bars[0]
    assert (done["open"], done["high"], done["low"], done["close"]) == (100.0, 103.0, 99.0, 99.0)
    assert b.forming["timestamp"] == datetime(2026, 10, 15, 10, 3) and b.forming["open"] == 101.0


def test_nothing_is_built_outside_market_hours_or_from_bad_prices():
    b = BarBuilder(3)
    assert b.update(100.0, now=datetime(2026, 10, 15, 8, 0)) is False and b.forming is None
    assert b.update(100.0, now=datetime(2026, 10, 15, 16, 0)) is False and b.forming is None
    assert b.update(0.0, now=datetime(2026, 10, 15, 10, 0)) is False and b.forming is None
    assert b.update(100.0, now=datetime(2026, 10, 17, 10, 0)) is False       # Saturday
