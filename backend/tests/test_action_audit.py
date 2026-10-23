import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.core import audit_middleware
from app.main import app
from app.services import action_audit
from app.services.action_audit import ActionAudit, classify

client = TestClient(app)
SECRET = "SENTINEL-SECRET-123456"


@pytest.fixture(autouse=True)
def fresh_audit(monkeypatch):
    d = tempfile.mkdtemp(prefix="audit-")
    audit = ActionAudit(os.path.join(d, "a.db"))
    monkeypatch.setattr(audit_middleware, "_audit", audit)
    monkeypatch.setattr(audit_middleware, "get_audit", lambda: audit)
    return audit


def rows(audit, **kw):
    return audit.list_actions(**kw)


def test_classify_known_routes():
    assert classify("POST", "/api/paper/close/abc-1") == ("paper.close", "abc-1", False)
    assert classify("POST", "/api/paper/kill-switch") == ("kill_switch.engage", None, False)
    assert classify("POST", "/api/paper/kill-switch/release")[0] == "kill_switch.release"
    assert classify("PUT", "/api/settings")[0] == "settings.update"
    assert classify("POST", "/api/settings/max_open_positions/reset") == ("settings.reset", "max_open_positions", False)
    assert classify("PUT", "/api/journal/trades/t9") == ("journal.save", "t9", False)
    assert classify("PUT", "/api/ui/layouts/custom:X") == ("ui.layout.save", "custom:X", False)
    assert classify("DELETE", "/api/earnings/calendar/TCS/2026-10-30")[0] == "earnings.calendar_delete"
    assert classify("POST", "/api/live/broker/login")[2] is True
    assert classify("POST", "/api/live/enable")[2] is True
    assert classify("POST", "/api/auth/verify")[2] is True


def test_every_existing_mutating_route_has_a_named_action():
    from app.main import create_app
    unknown = []
    for r in create_app().routes:
        for sub in getattr(r, "routes", None) or []:
            pass
    # Walk the included routers the way FastAPI exposes them in openapi.
    spec = TestClient(app).get("/openapi.json").json()
    for path, ops in spec["paths"].items():
        for method in ops:
            m = method.upper()
            if m in action_audit.MUTATING and path.startswith("/api"):
                concrete = path.replace("{", "").replace("}", "")
                action, _, _ = classify(m, concrete)
                if action.startswith("unknown."):
                    unknown.append((m, path))
    assert unknown == []


def test_error_response_is_recorded_with_detail_and_target(fresh_audit):
    r = client.post("/api/paper/close/NOPE-1")
    assert r.status_code >= 400
    row = rows(fresh_audit)[0]
    assert row["action"] == "paper.close" and row["target"] == "NOPE-1"
    assert row["outcome"] == "error" and row["status"] == r.status_code
    assert row["detail"]


def test_ok_response_is_recorded(fresh_audit):
    r = client.put("/api/ui/layouts/custom:aud1", json={"kind": "custom", "schema_version": 1, "body": {"a": 1}})
    assert r.status_code == 200
    row = rows(fresh_audit)[0]
    assert (row["action"], row["target"], row["outcome"], row["status"]) == ("ui.layout.save", "custom:aud1", "ok", 200)
    assert row["ts"] and row["method"] == "PUT"


def test_layout_put_is_recorded_as_ui_layout_save(fresh_audit):
    body = {"kind": "custom", "schema_version": 1, "body": {"a": 1}}
    assert client.put("/api/ui/layouts/custom:AuditMe", json=body).status_code == 200
    assert rows(fresh_audit)[0]["action"] == "ui.layout.save"


def test_response_body_is_unchanged_by_the_middleware():
    r = client.post("/api/paper/close/NOPE-2")
    assert r.json().get("detail")


@pytest.mark.parametrize("path", ["/api/auth/verify", "/api/live/broker/login", "/api/live/enable"])
def test_sensitive_route_bodies_and_errors_are_never_stored(fresh_audit, path):
    client.post(path, json={"totp": SECRET, "token": SECRET, "code": SECRET, "phrase": SECRET})
    stored = json.dumps(rows(fresh_audit))
    assert SECRET not in stored
    row = rows(fresh_audit)[0]
    assert row["detail"] is None


def test_request_body_is_never_stored_for_normal_routes(fresh_audit):
    client.put("/api/ui/layouts/custom:aud2", json={"kind": "custom", "schema_version": 1, "body": {"note": SECRET}})
    assert SECRET not in json.dumps(rows(fresh_audit))


def test_jwt_like_text_in_detail_is_redacted():
    assert "eyJ" not in (action_audit.clean_detail("bad token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc") or "")


def test_unknown_mutating_route_is_recorded_as_unknown(fresh_audit):
    client.post("/api/does/not/exist")
    row = rows(fresh_audit)[0]
    assert row["action"] == "unknown.does.not.exist" and row["status"] == 404


def test_get_routes_are_not_recorded(fresh_audit):
    client.get("/api/health")
    client.get("/api/paper/portfolio")
    assert rows(fresh_audit) == []


def test_unauthenticated_attempt_is_recorded_as_denied(fresh_audit):
    r = client.post("/api/paper/reset", headers={"X-Omit-Capability": "1"})
    assert r.status_code == 401
    row = rows(fresh_audit)[0]
    assert row["action"] == "paper.reset" and row["outcome"] == "denied" and row["status"] == 401


def test_a_failing_audit_write_does_not_change_the_response(fresh_audit, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(fresh_audit, "_conn", boom)
    r = client.put("/api/ui/layouts/custom:aud3", json={"kind": "custom", "schema_version": 1, "body": {"a": 1}})
    assert r.status_code == 200


def test_list_filters_and_limit(fresh_audit):
    for i in range(5):
        fresh_audit.record("POST", "/api/paper/close/x", "paper.close", f"x{i}", "error", 404, "nope")
    fresh_audit.record("PUT", "/api/settings", "settings.update", None, "ok", 200)
    assert len(rows(fresh_audit, limit=3)) == 3
    assert {r["action"] for r in rows(fresh_audit, action="settings.update")} == {"settings.update"}
    assert len(rows(fresh_audit, outcome="error")) == 5
    assert rows(fresh_audit, since="2999-01-01") == []


def test_audit_api_lists_and_validates():
    assert client.get("/api/audit/actions?limit=5").status_code == 200
    assert client.get("/api/audit/actions?outcome=bogus").status_code == 422
    assert client.get("/api/audit/actions", headers={"X-Omit-Capability": "1"}).status_code == 401
