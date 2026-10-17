import threading

from app.services import db
from app.services.paper_storage import PaperStorage
from app.services.runtime_settings import RuntimeSettings


def test_connect_enables_wal_and_busy_timeout(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 15000
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    conn.close()


def test_reader_is_not_blocked_by_open_write_transaction(tmp_path):
    path = str(tmp_path / "t.db")
    w = db.connect(path)
    w.execute("CREATE TABLE t (x INTEGER)")
    w.execute("INSERT INTO t VALUES (1)")
    w.commit()
    w.execute("BEGIN IMMEDIATE")
    w.execute("INSERT INTO t VALUES (2)")  # uncommitted
    r = db.connect(path, timeout=0.2)
    assert r.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1  # would raise 'database is locked' without WAL
    w.commit()
    assert r.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
    r.close(); w.close()


def test_modules_share_one_database_file_in_wal_mode(tmp_path):
    path = str(tmp_path / "t.db")
    PaperStorage(path)
    RuntimeSettings(path)
    assert db.connect(path).execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_concurrent_writers_do_not_fail(tmp_path):
    path = str(tmp_path / "t.db")
    c = db.connect(path)
    c.execute("CREATE TABLE t (x INTEGER)")
    c.commit(); c.close()
    errors = []

    def work(n):
        try:
            for i in range(50):
                with db.connect(path) as conn:
                    conn.execute("INSERT INTO t VALUES (?)", (n * 100 + i,))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    ts = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert errors == []
    assert db.connect(path).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 200
