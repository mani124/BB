"""Live routing API: guarded by the same capability middleware, and live cannot be switched on by one call."""
import pytest
from starlette.testclient import TestClient

from app.main import app, live_router
from app.services.order_router import CONFIRM_ENV, DRY_RUN, OFF, ENABLE_PHRASE

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(CONFIRM_ENV, raising=False)
    live_router.set_mode(OFF)
    live_router._set_state("halted", "")
    yield
    live_router.set_mode(OFF)


def test_status_defaults_to_off():
    r = client.get("/api/live/status")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "off" and body["broker"] == "definedge" and body["env_confirmed"] is False
    assert body["broker_session"] is False and body["positions"] == [] or isinstance(body["positions"], list)


def test_endpoints_need_capability():
    for method, path in (("get", "/api/live/status"), ("post", "/api/live/mode"), ("post", "/api/live/arm")):
        r = getattr(client, method)(path, headers={"X-Omit-Capability": "1"})
        assert r.status_code == 401


def test_mode_can_be_dry_run_but_never_live_directly():
    assert client.post("/api/live/mode", json={"mode": "dry_run"}).json()["mode"] == DRY_RUN
    r = client.post("/api/live/mode", json={"mode": "live"})
    assert r.status_code == 403
    assert client.post("/api/live/mode", json={"mode": "bogus"}).status_code == 422
    assert client.get("/api/live/status").json()["mode"] == DRY_RUN


def test_arm_refused_without_server_flag():
    r = client.post("/api/live/arm")
    assert r.status_code == 403 and CONFIRM_ENV in r.json()["detail"]


def test_enable_without_arm_is_refused():
    r = client.post("/api/live/enable", json={"code": "123456", "phrase": ENABLE_PHRASE})
    assert r.status_code == 403
    assert client.get("/api/live/status").json()["mode"] == OFF


def test_live_mode_is_not_a_generic_setting():
    keys = {s["key"] for s in client.get("/api/settings").json()["settings"]}
    assert "live_max_lots_per_order" in keys and "live_algo_id" in keys
    assert not {"live_mode", "trading_mode", "live_enabled"} & keys
    assert client.put("/api/settings", json={"changes": {"live_mode": "live"}}).status_code == 422


def test_broker_login_without_server_credentials_is_a_clean_error(monkeypatch):
    monkeypatch.delenv("DEFINEDGE_API_TOKEN", raising=False)
    r = client.post("/api/live/broker/login", json={"totp": "123456"})
    assert r.status_code == 400 and "DEFINEDGE_API_TOKEN" in r.json()["detail"]
