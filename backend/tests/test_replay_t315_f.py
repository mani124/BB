import pandas as pd

from scripts.replay_t315_f import Params, simulate, stop_distance

P = Params()


def _df(rows, start="2026-10-15 11:00"):
    idx = pd.date_range(start, periods=len(rows), freq="3min")
    return pd.DataFrame({"timestamp": idx, "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows], "volume": 1})


def _slow(df, value):
    return pd.Series([value] * len(df))


ENTRY = (100, 101, 99, 100)


def test_stop_is_the_swing_extreme_clamped_to_25_30_points():
    near = _df([(100, 100.2, 99.9, 100)] * 5)
    assert stop_distance(near, 4, "CE", P) == 25.0           # a 0.1 swing is raised to the 25-point floor
    far = _df([(100, 100, 40, 100)] * 5)
    assert stop_distance(far, 4, "CE", P) == 30.0            # a 60-point swing is cut to the 30-point cap
    mid = _df([(100, 100, 73, 100)] * 5)
    assert stop_distance(mid, 4, "CE", P) == 27.0            # in between it is the swing itself
    assert stop_distance(_df([(100, 128, 99, 100)] * 5), 4, "PE", P) == 28.0


def test_stop_loss_before_t1_costs_the_stop_distance():
    df = _df([ENTRY, (100, 101, 70, 72)])
    pts, how = simulate(df, _slow(df, 90), 0, "CE", P)
    assert how == "stopped" and pts == -25.0


def test_t1_books_sixty_percent_and_the_runner_trails_the_15_ema():
    df = _df([ENTRY, (100, 146, 99, 145), (145, 160, 144, 158), (158, 159, 150, 151)])
    slow = pd.Series([90, 90, 90, 155.0])                     # the last candle closes under the 15 EMA
    pts, how = simulate(df, slow, 0, "CE", P)
    assert how == "T1 then 15 EMA trail"
    assert round(pts, 2) == round(0.6 * 45 + 0.4 * (151 - 100), 2)


def test_runner_stopped_at_cost_after_t1_keeps_only_the_booked_part():
    df = _df([ENTRY, (100, 146, 99, 145), (145, 146, 99, 100)])
    pts, how = simulate(df, _slow(df, 50), 0, "CE", P)
    assert how == "T1 then back to cost" and pts == 0.6 * 45


def test_open_trade_is_closed_at_the_315_cutoff():
    df = _df([ENTRY, (100, 110, 95, 105), (105, 112, 96, 108), (108, 111, 97, 109)], start="2026-10-15 15:06")
    pts, how = simulate(df, _slow(df, 50), 0, "CE", P)
    assert how == "cutoff" and pts == 8.0                     # the 15:15 bar is not traded; the last close before it is 108


def test_pe_is_the_mirror():
    df = _df([ENTRY, (100, 101, 54, 55), (55, 58, 54, 56)])
    pts, how = simulate(df, _slow(df, 50), 0, "PE", P)         # T1 hit (down 45), then a close above the 15 EMA
    assert how == "T1 then 15 EMA trail"
    assert round(pts, 2) == round(0.6 * 45 + 0.4 * (100 - 56), 2)
