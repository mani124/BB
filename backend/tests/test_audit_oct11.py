import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_direct_client_capability_required():
    """F1: Direct client mutations (no Origin/Referer) require a valid capability token."""
    # 1. Missing capability on direct mutation -> 401
    res_no_cap = client.post("/api/paper/reset", headers={"X-Omit-Capability": "1"})
    assert res_no_cap.status_code == 401
    assert "capability required" in res_no_cap.json()["detail"].lower()

    # 2. Invalid capability token on direct mutation -> 401
    res_bad_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": "wrong-secret-token"})
    assert res_bad_cap.status_code == 401
    assert "capability" in res_bad_cap.json()["detail"].lower()

    # 3. Valid X-Dashboard-Capability header -> 200
    res_good_cap = client.post("/api/paper/reset", headers={"X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY})
    assert res_good_cap.status_code == 200

    # 4. Valid Authorization Bearer header -> 200
    res_auth = client.post("/api/paper/reset", headers={"Authorization": f"Bearer {settings.DASHBOARD_CAPABILITY}"})
    assert res_auth.status_code == 200

    # 5. Browser request with valid origin does not require capability header -> 200
    res_origin = client.post("/api/paper/reset", headers={"Origin": "http://localhost:5174", "X-Omit-Capability": "1"})
    assert res_origin.status_code == 200

    # 6. Browser request with untrusted origin -> 403 Forbidden
    res_evil = client.post("/api/paper/reset", headers={"Origin": "https://evil.sslip.io", "X-Omit-Capability": "1"})
    assert res_evil.status_code == 403

    # 7. Direct GET request with no capability -> 200 (read routes not blocked)
    res_get = client.get("/api/health", headers={"X-Omit-Capability": "1"})
    assert res_get.status_code == 200
