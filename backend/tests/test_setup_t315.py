"""Setup 20: T315 (EMA 3 / EMA 15 cross on the index chart) and its 3:15 PM cutoff."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.services import market_hours
from app.services.indicators import calculate_indicators
from app.services.paper_models import T315_CUTOFF
from app.services.paper_trader import EOD_SQUARE_OFF, PaperTradingEngine
from app.services.setup_switches import DEFAULT_MODES, block_reason
from app.services.setup_t315 import evaluate_t315
from app.services.strategy_engine import SetupType
from tests.test_p0_session_guard import at, make_signal

LAST_BAR = datetime(2026, 10, 15, 11, 0)


def _df(closes, last_bar=LAST_BAR):
    start = last_bar - timedelta(minutes=5 * (len(closes) - 1))
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        rows.append({"timestamp": start + timedelta(minutes=5 * i), "open": prev,
                     "high": max(prev, c) + 0.3, "low": min(prev, c) - 0.3, "close": c, "volume": 1000})
        prev = c
    return calculate_indicators(pd.DataFrame(rows))


def _up_cross(**kw):
    """A steady climb, a six-bar pullback that drops the 3 EMA under the 15 EMA, then one strong bar back up."""
    base = [100 + 0.5 * i for i in range(60)]
    last = base[-1]
    return _df(base + [last - d for d in (1, 2, 3, 4, 5, 6)] + [last - 6 + 9], **kw)


def _down_cross(**kw):
    base = [200 - 0.5 * i for i in range(60)]
    last = base[-1]
    return _df(base + [last + d for d in (1, 2, 3, 4, 5, 6)] + [last + 6 - 9], **kw)


def _ema(df, span):
    return df["close"].ewm(span=span, adjust=False).mean()


def test_ce_fires_when_3_ema_crosses_above_15_ema_above_the_50_ema():
    df = _up_cross()
    e3, e15, e50 = _ema(df, 3), _ema(df, 15), _ema(df, 50)
    assert e3.iloc[-2] <= e15.iloc[-2] and e3.iloc[-1] > e15.iloc[-1] and df["close"].iloc[-1] > e50.iloc[-1]
    sigs = evaluate_t315("NIFTY 50", df)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_type == SetupType.SETUP_20_T315 and s.option_type == "CE" and s.is_confirmed
    assert s.timeframe == "5m"
    assert s.entry_price == round(float(df["close"].iloc[-1]), 2)
    assert s.target_1 > s.entry_price
    assert {"ema_3", "ema_15", "ema_50", "close"} <= set(s.indicators_snapshot)


def test_ce_stop_is_below_the_candle_low_and_the_15_ema():
    df = _up_cross()
    s = evaluate_t315("NIFTY 50", df)[0]
    assert s.stop_loss < float(df["low"].iloc[-1])
    assert s.stop_loss < float(_ema(df, 15).iloc[-1])


def test_pe_is_the_mirror_image():
    df = _down_cross()
    sigs = evaluate_t315("NIFTY 50", df)
    assert len(sigs) == 1 and sigs[0].option_type == "PE"
    assert sigs[0].stop_loss > float(df["high"].iloc[-1])
    assert sigs[0].stop_loss > float(_ema(df, 15).iloc[-1])


def test_the_50_ema_filter_blocks_a_cross_against_the_trend():
    # a long slide, then a bounce whose 3 EMA crosses the 15 EMA while price is still under the 50 EMA
    base = [200 - 0.5 * i for i in range(60)]
    last = base[-1]
    df = _df(base + [last - 0.3 * i for i in range(1, 7)] + [last - 1.8 + 10])
    e3, e15, e50 = _ema(df, 3), _ema(df, 15), _ema(df, 50)
    assert e3.iloc[-2] <= e15.iloc[-2] and e3.iloc[-1] > e15.iloc[-1]   # a genuine 3/15 cross...
    assert df["close"].iloc[-1] < e50.iloc[-1]                          # ...against the 50 EMA
    assert evaluate_t315("NIFTY 50", df) == []


def test_no_cross_no_signal():
    df = _df([100 + 0.5 * i for i in range(70)])
    assert evaluate_t315("NIFTY 50", df) == []


def test_signal_is_not_repeated_on_the_bar_after_the_cross():
    base = [100 + 0.5 * i for i in range(60)]
    last = base[-1]
    df = _df(base + [last - d for d in (1, 2, 3, 4, 5, 6)] + [last + 3, last + 4])
    assert evaluate_t315("NIFTY 50", df) == []


def test_indices_only():
    assert evaluate_t315("RELIANCE", _up_cross()) == []


def test_five_minute_chart_only():
    assert evaluate_t315("NIFTY 50", _up_cross(), timeframe="15m") == []


def test_needs_enough_history_for_the_50_ema():
    base = [100 + 0.5 * i for i in range(30)]
    last = base[-1]
    df = _df(base + [last - d for d in (1, 2, 3, 4, 5, 6)] + [last - 6 + 9])
    assert len(df) < 50
    assert evaluate_t315("NIFTY 50", df) == []


@pytest.mark.parametrize("hh,mm,expected", [(9, 20, 0), (9, 25, 0), (9, 30, 1), (15, 5, 1), (15, 10, 0)])
def test_entry_window_uses_the_bar_start_time(hh, mm, expected):
    df = _up_cross(last_bar=datetime(2026, 10, 15, hh, mm))
    assert len(evaluate_t315("NIFTY 50", df)) == expected


def test_default_switch_is_off_and_indices_only_when_on():
    assert DEFAULT_MODES["20"] == "off"           # switched off by default: it lost money on the 51-day replay
    on = {**DEFAULT_MODES, "20": "index"}
    assert block_reason(on, SetupType.SETUP_20_T315, "RELIANCE")
    assert block_reason(on, SetupType.SETUP_20_T315, "NIFTY 50") is None


# ---------------------------------------------------------------- the 3:15 PM cutoff

@pytest.fixture
def engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "t315.db"))


def _open(engine, sig_id, sec_id, setup, symbol):
    with market_hours.override_clock(at(13, 0)):
        return engine.open_position_from_signal(
            make_signal(sig_id, symbol=symbol, sec_id=sec_id, setup=setup), lots=1, feed_mode="live")


def test_t315_positions_close_at_1515_and_others_wait_for_the_normal_square_off(engine):
    t = _open(engine, "T", "1", SetupType.SETUP_20_T315, "NIFTY 50")
    o = _open(engine, "O", "2", SetupType.SETUP_5_OPTION_BB, "BANKNIFTY")
    assert t and o
    with market_hours.override_clock(at(15, 14, 59)):
        assert engine.square_off_if_due() == []
    with market_hours.override_clock(at(15, 15, 1)):
        closed = engine.square_off_if_due()
    assert [c.id for c in closed] == [t.id]
    assert closed[0].exit_reason.startswith(T315_CUTOFF)
    assert [p.id for p in engine.get_portfolio().active_positions] == [o.id]
    with market_hours.override_clock(at(15, 20)):
        later = engine.square_off_if_due()
    assert [c.id for c in later] == [o.id]
    assert later[0].exit_reason.startswith(EOD_SQUARE_OFF)
