import os
import time
from datetime import datetime

from starlette.testclient import TestClient

from app.services import market_hours, readiness
from app.services.readiness import FAIL, OK, WARN, ReadinessMonitor, check_backup, check_disk, run_checks

IST = market_hours.IST
WED = lambda h, m: datetime(2026, 10, 14, h, m, tzinfo=IST)  # trading day
SAT = lambda h, m: datetime(2026, 10, 17, h, m, tzinfo=IST)


def by_key(checks):
    return {c.key: c for c in checks}


def test_backup_states(tmp_path):
    d = str(tmp_path)
    now = time.time()
    assert check_backup(str(tmp_path / "missing"), now).status == WARN
    assert check_backup(d, now).status == FAIL  # nothing recorded yet
    ok = tmp_path / "last_success"
    ok.write_text("x")
    os.utime(ok, (now - 3600, now - 3600))
    assert check_backup(d, now).status == OK
    os.utime(ok, (now - 40 * 3600, now - 40 * 3600))
    assert check_backup(d, now).status == FAIL  # stale
    os.utime(ok, (now - 3600, now - 3600))
    bad = tmp_path / "last_failure"
    bad.write_text("x")
    os.utime(bad, (now - 60, now - 60))
    assert check_backup(d, now).status == FAIL  # failure newer than success


def test_disk_thresholds():
    class U:
        def __init__(self, used, total=100):
            self.used, self.total, self.free = used, total, total - used
    assert check_disk("/", lambda p: U(50)).status == OK
    assert check_disk("/", lambda p: U(85)).status == WARN
    assert check_disk("/", lambda p: U(95)).status == FAIL


def test_run_checks_flags_missing_login_and_telegram(tmp_path):
    checks = by_key(run_checks(has_dhan_login=False, feed_live=False, now=WED(8, 55), data_dir=str(tmp_path),
                               backup_dir=str(tmp_path / "b"), deploy_dir=str(tmp_path / "d"), telegram=False))
    assert checks["dhan_login"].status == FAIL
    assert checks["telegram"].status == WARN
    assert checks["trading_day"].status == OK
    assert checks["deploy"].status == OK


def test_live_mode_without_broker_session_fails(tmp_path):
    checks = by_key(run_checks(has_dhan_login=True, feed_live=True, router_mode="live", broker_session=False,
                               now=WED(8, 55), data_dir=str(tmp_path), backup_dir=str(tmp_path), deploy_dir=str(tmp_path),
                               telegram=True))
    assert checks["live_routing"].status == FAIL


def test_failed_deploy_is_reported(tmp_path):
    (tmp_path / "failed").write_text("abcdef1234567\n")
    assert readiness.check_deploy(str(tmp_path)).status == WARN


def _monitor(login=False, backup_fail=False):
    sent = []

    def gather():
        return [readiness.Check("dhan_login", OK if login else FAIL, "x"),
                readiness.Check("backup", FAIL if backup_fail else OK, "b")]

    return ReadinessMonitor(gather, send=lambda *a, **k: sent.append((a, k)) or True), sent


def test_morning_alert_once_per_day():
    m, sent = _monitor(login=True)
    assert m.tick(WED(8, 59)) == []
    assert m.tick(WED(9, 0)) == ["morning"]
    assert m.tick(WED(9, 1)) == []
    assert len(sent) == 1 and "Everything is ready" in sent[0][0][1]


def test_login_reminder_and_last_call_only_when_not_logged_in():
    m, sent = _monitor(login=False)
    assert m.tick(WED(9, 0)) == ["morning"]
    assert m.tick(WED(9, 10)) == ["reminder"]
    assert m.tick(WED(9, 20)) == ["last_call"]
    assert m.tick(WED(9, 21)) == []
    ok, sent_ok = _monitor(login=True)
    assert ok.tick(WED(9, 0)) == ["morning"]
    assert ok.tick(WED(9, 10)) == []
    assert ok.tick(WED(9, 20)) == []


def test_no_market_alerts_on_weekend_but_evening_machine_alert_fires():
    m, sent = _monitor(login=False, backup_fail=True)
    assert m.tick(SAT(9, 0)) == []
    assert m.tick(SAT(18, 0)) == ["evening"]
    assert len(sent) == 1 and "backup" in sent[0][0][1] and "dhan_login" not in sent[0][0][1]
    assert m.tick(SAT(18, 1)) == []


def test_evening_is_silent_when_machine_checks_pass():
    m, sent = _monitor(login=False, backup_fail=False)
    m.tick(WED(18, 0))
    assert sent == []


def test_readiness_endpoint():
    from app.main import app
    with TestClient(app) as client:
        r = client.get("/api/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in (OK, WARN, FAIL)
    assert {c["key"] for c in body["checks"]} >= {"dhan_login", "backup", "disk", "telegram", "holiday_list"}
