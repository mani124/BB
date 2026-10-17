from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_wrong_keys_are_throttled_and_success_resets(monkeypatch):
    auth_api._session_failures.clear()
    for _ in range(auth_api._SESSION_FAIL_LIMIT):
        assert client.post("/api/auth/session", json={"secret": "nope"}).status_code == 401
    # locked, even for the right key
    assert client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY}).status_code == 429
    auth_api._session_failures.clear()
    assert client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY}).status_code == 200


def test_failures_expire(monkeypatch):
    auth_api._session_failures.clear()
    auth_api._session_failures["testclient"] = [0.0] * auth_api._SESSION_FAIL_LIMIT
    monkeypatch.setattr("time.monotonic", lambda: auth_api._SESSION_FAIL_WINDOW_S + 1.0)
    assert client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY}).status_code == 200
    auth_api._session_failures.clear()
