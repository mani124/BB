"""Liquidity filter: shadow mode by default, blocks only when enabled."""
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import liquidity_filter as lf
from app.services.paper_trader import PaperTradingEngine
from tests.test_p0_session_guard import make_signal


def cfg(**kw):
    base = dict(LIQ_FILTER_ENABLED=False, LIQ_MAX_SPREAD_PCT=10, LIQ_MIN_VOLUME=100, LIQ_MIN_OI=1000, LIQ_MIN_PREMIUM=0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_evaluate_each_check():
    c = cfg(LIQ_MIN_PREMIUM=5)
    assert lf.evaluate(bid=80, ask=100, cfg=c)[0].startswith("spread 20.0%")
    assert lf.evaluate(volume=50, cfg=c)[0].startswith("volume")
    assert lf.evaluate(oi=10, cfg=c)[0].startswith("OI")
    assert lf.evaluate(premium=2, cfg=c)[0].startswith("premium")
    assert lf.evaluate(bid=98, ask=100, volume=500, oi=5000, premium=100, cfg=c) == []


def test_missing_data_never_skips_and_zero_disables():
    assert lf.evaluate(cfg=cfg()) == []
    assert lf.evaluate(bid=1, ask=100, volume=1, oi=1, cfg=cfg(LIQ_MAX_SPREAD_PCT=0, LIQ_MIN_VOLUME=0, LIQ_MIN_OI=0)) == []


def test_shadow_mode_logs_but_does_not_block(caplog):
    rec = SimpleNamespace(real_bid_price=50, real_ask_price=100, real_volume=1, real_oi=1, estimated_option_entry=100)
    with caplog.at_level("WARNING"):
        assert lf.check_recommendation(rec, "X", "CE", cfg=cfg()) is None
    assert "would_skip" in caplog.text
    assert lf.check_recommendation(rec, "X", "CE", cfg=cfg(LIQ_FILTER_ENABLED=True))


def _engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "t.db"))


def test_engine_blocks_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "LIQ_MIN_VOLUME", 100)
    sig = make_signal("LQ_1", symbol="IRFC")
    sig.strike_recommendation.real_volume = 5
    eng = _engine(tmp_path)
    monkeypatch.setattr(settings, "LIQ_FILTER_ENABLED", False)
    eng.on_signals_cycle([sig], feed_mode="demo")
    assert len(eng.get_portfolio().active_positions) == 1

    sig2 = make_signal("LQ_2", symbol="TCS", sec_id="9001")
    sig2.strike_recommendation.real_volume = 5
    eng2 = PaperTradingEngine(db_path=str(tmp_path / "t2.db"))
    monkeypatch.setattr(settings, "LIQ_FILTER_ENABLED", True)
    eng2.on_signals_cycle([sig2], feed_mode="demo")
    assert eng2.get_portfolio().active_positions == []


def test_analysis_script_runs(tmp_path):
    db = tmp_path / "a.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE positions (status TEXT, quarantine_reason TEXT, entry_spread_pct REAL, "
                 "option_volume REAL, option_oi REAL, net_pnl REAL, option_entry REAL)")
    conn.executemany("INSERT INTO positions VALUES ('CLOSED', NULL, ?, ?, ?, ?, ?)",
                     [(20, 10, 100, -500, 3), (2, 900, 9000, 300, 40), (None, None, None, 100, 10)])
    conn.commit()
    conn.close()
    out = subprocess.run([sys.executable, "scripts/liquidity_analysis.py", str(db)], capture_output=True, text=True, check=True).stdout
    assert "3 closed trades" in out and "Skip if spread" in out
