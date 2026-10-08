import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.dhan_client import DhanClient

@pytest.mark.asyncio
async def test_verify_credentials_success():
    client = DhanClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"dhanClientId": "1000000001"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await client.verify_credentials("1000000001", "valid_token")
        assert res["valid"] is True
        assert "dhanClientId" in res["data"]

@pytest.mark.asyncio
async def test_verify_credentials_invalid_401():
    client = DhanClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await client.verify_credentials("1000000001", "invalid_token")
        assert res["valid"] is False
        assert "Invalid or expired" in res["error"]
