import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_universe():
    response = client.get("/api/universe")
    assert response.status_code == 200
    data = response.json()
    assert "indices" in data
    assert "stocks" in data
    assert len(data["indices"]) == 4

def test_api_signals_snapshot():
    response = client.get("/api/signals")
    assert response.status_code == 200
    data = response.json()
    assert "signals" in data
    assert "radar" in data
    assert "scan_cycle_count" in data

def test_api_auth_verify_missing_headers():
    response = client.post("/api/auth/verify")
    assert response.status_code == 401
