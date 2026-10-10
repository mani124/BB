import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app, worker
from app.core.security import sanitize_token

client = TestClient(app)

def test_oauth_login_url_generation():
    res = client.get("/api/auth/oauth/login-url?app_id=APP123&redirect_uri=http://localhost:5174/")
    assert res.status_code == 200
    data = res.json()
    assert "https://auth.dhan.co/login/consent" in data["login_url"]
    assert "client_id=APP123" in data["login_url"]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A5174%2F" in data["login_url"]

def test_oauth_login_url_without_redirect_uri():
    res = client.get("/api/auth/oauth/login-url?app_id=APP123")
    assert res.status_code == 200
    data = res.json()
    assert "https://auth.dhan.co/login/consent" in data["login_url"]
    assert "client_id=APP123" in data["login_url"]
    assert "redirect_uri" not in data["login_url"]

def test_oauth_login_url_missing_app_id():
    res = client.get("/api/auth/oauth/login-url")
    assert res.status_code == 422

def test_oauth_login_url_post():
    res = client.post("/api/auth/oauth/login-url", json={
        "app_id": "APP123",
        "app_secret": "",
        "redirect_uri": "http://localhost:5174/"
    })
    assert res.status_code == 200
    data = res.json()
    assert "https://auth.dhan.co/login/consent" in data["login_url"]
    assert "client_id=APP123" in data["login_url"]

@pytest.mark.asyncio
async def test_oauth_token_exchange_success():
    mock_resp = {
        "status": "success",
        "data": {
            "dhanClientId": "1000000000",
            "accessToken": "eyJh...sample_token",
            "expiresIn": 86400
        }
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_resp
        res = client.post("/api/auth/oauth/token", json={
            "app_id": "APP123",
            "app_secret": "SEC456",
            "consent_id": "CONSENT789"
        })
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "connected"
        assert body["client_id"] == "1000000000"
        assert "accessToken" not in body  # Must not leak full raw token
        assert body["masked_token"] == sanitize_token("eyJh...sample_token")
        assert body["expires_in_hours"] == 24
        assert worker._session_credentials == ("1000000000", "eyJh...sample_token")
        assert worker.get_state().active_mode == "live"
        worker.set_session_credentials(None, None)

@pytest.mark.asyncio
async def test_oauth_token_exchange_failure_status_code():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 401
        mock_post.return_value.text = "Unauthorized"
        res = client.post("/api/auth/oauth/token", json={
            "app_id": "APP123",
            "app_secret": "SEC456",
            "consent_id": "BAD_CONSENT"
        })
        assert res.status_code == 401

def test_oauth_token_exchange_missing_fields():
    res = client.post("/api/auth/oauth/token", json={
        "app_id": "APP123"
    })
    assert res.status_code == 422

def test_oauth_login_url_get_rejects_app_secret():
    res = client.get("/api/auth/oauth/login-url?app_id=APP123&app_secret=SECRET123")
    assert res.status_code == 400
    assert "prohibited" in res.json()["detail"].lower()
