import pytest
from starlette.testclient import TestClient
from app.main import create_app
from app.core.config import settings

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_spoofed_origin_mutation_rejected_without_capability(client):
    """F1: Supplying an allowed Origin does not bypass capability token requirement for mutations."""
    # Spoofed local development origin
    res = client.post(
        "/api/paper/reset",
        headers={"Origin": "http://localhost:5174", "X-Omit-Capability": "1"}
    )
    assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}: {res.text}"
    assert "capability" in res.json().get("detail", "").lower()

    # Spoofed production origin
    res_prod = client.post(
        "/api/paper/reset",
        headers={"Origin": "https://options.34-14-178-224.sslip.io", "X-Omit-Capability": "1"}
    )
    assert res_prod.status_code == 401, f"Expected 401 Unauthorized, got {res_prod.status_code}: {res_prod.text}"


def test_oauth_routes_protected_by_capability(client):
    """F1/F3: Session-mutating OAuth routes require dashboard capability to prevent session hijacking."""
    # /api/auth/verify without capability
    res_verify = client.post(
        "/api/auth/verify",
        headers={
            "X-Omit-Capability": "1",
            "X-Dhan-Client-Id": "1100000000",
            "X-Dhan-Access-Token": "test_token"
        }
    )
    assert res_verify.status_code == 401, f"Expected 401, got {res_verify.status_code}: {res_verify.text}"

    # /api/auth/oauth/token without capability
    res_token = client.post(
        "/api/auth/oauth/token",
        json={"app_id": "app", "app_secret": "secret", "consent_id": "consent"},
        headers={"X-Omit-Capability": "1"}
    )
    assert res_token.status_code == 401, f"Expected 401, got {res_token.status_code}: {res_token.text}"


def test_private_reads_and_sse_require_capability(client):
    """F3: Private dashboard reads and SSE streams are protected from unauthenticated access."""
    # Private portfolio read
    res_port = client.get("/api/paper/portfolio", headers={"X-Omit-Capability": "1"})
    assert res_port.status_code == 401, f"Expected 401 for /portfolio, got {res_port.status_code}"

    # Private scanner state read
    res_state = client.get("/api/signals/state", headers={"X-Omit-Capability": "1"})
    assert res_state.status_code == 401, f"Expected 401 for /signals/state, got {res_state.status_code}"

    # Public health check remains open
    res_health = client.get("/api/health")
    assert res_health.status_code == 200


def test_auth_session_endpoint_and_cookie_bootstrap(client):
    """F1/F3: POST /api/auth/session authorizes via master secret and issues dashboard_session cookie."""
    # Wrong secret rejected
    bad_res = client.post("/api/auth/session", json={"secret": "wrong_secret"})
    assert bad_res.status_code == 401

    # Valid master capability secret accepted
    good_res = client.post("/api/auth/session", json={"secret": settings.DASHBOARD_CAPABILITY})
    assert good_res.status_code == 200
    data = good_res.json()
    assert data.get("status") == "authenticated"
    assert "dashboard_session" in good_res.cookies

    # Authenticated client with cookie can read private endpoints
    cookie_val = good_res.cookies["dashboard_session"]
    auth_client = TestClient(create_app(), cookies={"dashboard_session": cookie_val})
    res_port = auth_client.get("/api/paper/portfolio")
    assert res_port.status_code == 200

    res_state = auth_client.get("/api/signals/state")
    assert res_state.status_code == 200


def test_mutation_with_both_origin_and_capability(client):
    """F1: Browser requests succeed when both allowed Origin and valid capability (or cookie) are present."""
    res = client.post(
        "/api/paper/reset",
        headers={
            "Origin": "http://localhost:5174",
            "X-Dashboard-Capability": settings.DASHBOARD_CAPABILITY
        }
    )
    assert res.status_code == 200
