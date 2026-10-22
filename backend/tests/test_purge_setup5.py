"""scripts/purge_setup5.py removes Setup 5 trades and their dependants, and nothing else."""
import glob
import sqlite3

from app.services.paper_trader import PaperTradingEngine
from scripts import purge_setup5 as purge
from tests.test_paper_reentry_gate import make_test_signal


def _db(tmp_path):
    from app.services.strategy_engine import SetupType
    path = str(tmp_path / "t.db")
    e = PaperTradingEngine(db_path=path)
    keep = make_test_signal("KEEP")
    keep.setup_type = SetupType.SETUP_1_SQUEEZE
    gone = make_test_signal("GONE", symbol="BANKNIFTY")
    gone.setup_type = SetupType.SETUP_5_OPTION_BB
    p_keep, p_gone = e.open_position_from_signal(keep, lots=2), e.open_position_from_signal(gone, lots=2)
    assert p_keep and p_gone
    return path, p_keep.id, p_gone.id


def _seed(path, keep_id, gone_id):
    con = sqlite3.connect(path)
    # the tables other modules create on the live database (same columns as production)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS trade_candles (position_id TEXT NOT NULL, kind TEXT NOT NULL, bars_json TEXT NOT NULL, updated_at TEXT, PRIMARY KEY (position_id, kind));
        CREATE TABLE IF NOT EXISTS trade_journal (position_id TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT '', tag TEXT NOT NULL DEFAULT '', updated_at TEXT);
        CREATE TABLE IF NOT EXISTS strategy_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, book TEXT, strategy TEXT, symbol TEXT, side TEXT, decision TEXT, reason TEXT, metrics TEXT, signal_id TEXT, position_id TEXT);
        CREATE TABLE IF NOT EXISTS processed_signals (signal_id TEXT PRIMARY KEY, created_at TEXT);
    """)
    for pid in (keep_id, gone_id):
        con.execute("INSERT INTO trade_candles (position_id, kind, bars_json, updated_at) VALUES (?, 'option', '[]', 'x')", (pid,))
        con.execute("INSERT INTO trade_journal (position_id, note, tag, updated_at) VALUES (?, 'n', 't', 'x')", (pid,))
    con.execute("INSERT INTO strategy_decisions (ts, book, strategy, symbol, side, decision, reason) VALUES ('2026-10-21 10:00:00','live','Setup 5: Option Chart BB Scalp','X','CE','SKIPPED','R')")
    con.execute("INSERT INTO strategy_decisions (ts, book, strategy, symbol, side, decision, reason) VALUES ('2026-10-21 10:00:00','live','Setup 1: BB Squeeze Breakout','X','CE','SKIPPED','R')")
    con.execute("INSERT OR REPLACE INTO processed_signals (signal_id, created_at) VALUES ('X_5m_S5_CE_1_20261021_100000', 'x')")
    con.execute("INSERT OR REPLACE INTO processed_signals (signal_id, created_at) VALUES ('X_5m_S1_CE_1_20261021_100000', 'x')")
    con.commit(); con.close()


def _n(path, q):
    con = sqlite3.connect(path)
    try:
        return con.execute(q).fetchone()[0]
    finally:
        con.close()


def test_dry_run_counts_and_changes_nothing(tmp_path):
    path, keep, gone = _db(tmp_path)
    _seed(path, keep, gone)
    found = purge.purge(path, execute=False)
    assert found["positions"] == 1 and found["trade_candles"] == 1 and found["strategy_decisions"] >= 1 and found["processed_signals"] == 1
    assert _n(path, "SELECT COUNT(*) FROM positions") == 2


def test_purge_deletes_only_setup_5_rows_and_writes_a_backup(tmp_path):
    path, keep, gone = _db(tmp_path)
    _seed(path, keep, gone)
    purge.purge(path, execute=True)
    assert _n(path, "SELECT COUNT(*) FROM positions") == 1
    assert _n(path, f"SELECT COUNT(*) FROM positions WHERE id = '{keep}'") == 1
    assert _n(path, "SELECT COUNT(*) FROM trade_candles") == 1 and _n(path, f"SELECT COUNT(*) FROM trade_candles WHERE position_id = '{keep}'") == 1
    assert _n(path, "SELECT COUNT(*) FROM trade_journal") == 1
    assert _n(path, "SELECT COUNT(*) FROM strategy_decisions WHERE strategy LIKE 'Setup 5%'") == 0
    assert _n(path, "SELECT COUNT(*) FROM strategy_decisions WHERE strategy LIKE 'Setup 1%'") >= 1
    assert _n(path, "SELECT COUNT(*) FROM processed_signals WHERE signal_id LIKE '%S1%'") == 1
    backups = glob.glob(path + ".before-setup5-purge-*")
    assert len(backups) == 1 and _n(backups[0], "SELECT COUNT(*) FROM positions") == 2          # the copy still has both trades


def test_the_engine_loads_cleanly_after_a_purge(tmp_path):
    path, keep, gone = _db(tmp_path)
    purge.purge(path, execute=True)
    e = PaperTradingEngine(db_path=path)
    ids = [p.id for p in e.get_portfolio().active_positions + e.get_portfolio().closed_trades]
    assert ids == [keep]
