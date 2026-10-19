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


def _gate_engine(tmp_path):
    return PaperTradingEngine(db_path=str(tmp_path / "g.db"))


def _liq_signal(sig_id, bid, ask, oi, volume=5000, symbol="IRFC", sec_id="55001"):
    sig = make_signal(sig_id, symbol=symbol, sec_id=sec_id, entry=ask)
    rec = sig.strike_recommendation
    rec.real_ask_price, rec.real_bid_price, rec.real_oi, rec.real_volume = ask, bid, oi, volume
    return sig


def test_gate_defaults_on_with_3pct_and_5000_oi(tmp_path):
    eng = _gate_engine(tmp_path)
    assert eng.runtime.get("liquidity_gate_enabled") is True
    assert eng.runtime.get("liquidity_max_spread_pct") == 3
    assert eng.runtime.get("liquidity_min_oi") == 5000


def test_gate_skips_wide_spread_and_thin_oi_with_liquidity_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    eng = _gate_engine(tmp_path)
    logged = []
    monkeypatch.setattr(eng, "_log_skip", lambda sig, mode, code, detail="": logged.append((code, detail)))
    wide = _liq_signal("G_1", bid=525, ask=690, oi=90000)
    thin = _liq_signal("G_2", bid=99, ask=100, oi=1200, symbol="TCS", sec_id="9001")
    good = _liq_signal("G_3", bid=99, ask=100, oi=90000, symbol="SBIN", sec_id="9002")
    assert eng.open_position_from_signal(wide, feed_mode="demo") is None
    assert eng.open_position_from_signal(thin, feed_mode="demo") is None
    assert eng.open_position_from_signal(good, feed_mode="demo") is not None
    assert [c for c, _ in logged] == ["LIQUIDITY_SKIP", "LIQUIDITY_SKIP"]
    assert "spread" in logged[0][1] and "OI" in logged[1][1]


def test_gate_toggle_and_thresholds_are_runtime_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    eng = _gate_engine(tmp_path)
    wide = _liq_signal("G_4", bid=90, ask=100, oi=90000)
    eng.runtime.set("liquidity_max_spread_pct", 15)
    assert eng.open_position_from_signal(wide, feed_mode="demo") is not None
    eng2 = PaperTradingEngine(db_path=str(tmp_path / "g2.db"))
    eng2.runtime.set("liquidity_gate_enabled", False)
    assert eng2.open_position_from_signal(_liq_signal("G_5", bid=50, ask=100, oi=10), feed_mode="demo") is not None
