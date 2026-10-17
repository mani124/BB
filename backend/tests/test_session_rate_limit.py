from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_wrong_keys_are_throttled_and_success_resets(monkeypatch):
    auth_api._session_failures.clear()
    for _ in range(auth_api._SESSION_FAIL_LIMIT):
        assert client.post("/api/auth/session", json={"secret": "nope"}).status_code == 401
    # further wrong keys are blocked, but the right key still gets in (a stranger cannot lock the owner out)
    assert client.post("/api/auth/session", json={"secret": "nope"}).status_code == 429
    assert client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY}).status_code == 200
    assert auth_api._session_failures == {}


def test_failure_table_is_bounded():
    auth_api._session_failures.clear()
    for i in range(auth_api._SESSION_FAIL_MAX_CLIENTS + 5):
        auth_api._session_failures[f"10.0.{i}"] = [1e12]
    client.post("/api/auth/session", json={"secret": "nope"})
    assert len(auth_api._session_failures) <= auth_api._SESSION_FAIL_MAX_CLIENTS
    auth_api._session_failures.clear()


def test_failures_expire(monkeypatch):
    auth_api._session_failures.clear()
    auth_api._session_failures["testclient"] = [0.0] * auth_api._SESSION_FAIL_LIMIT
    monkeypatch.setattr("time.monotonic", lambda: auth_api._SESSION_FAIL_WINDOW_S + 1.0)
    assert client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY}).status_code == 200
    auth_api._session_failures.clear()


def test_dashboard_key_file_race_keeps_first_key(tmp_path, monkeypatch):
    from app.core.config import Settings, resolve_dashboard_capability
    cfg = Settings(DATA_DIR=str(tmp_path), DASHBOARD_CAPABILITY="")
    first = resolve_dashboard_capability(cfg)
    assert resolve_dashboard_capability(cfg) == first
