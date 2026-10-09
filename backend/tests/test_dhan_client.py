import asyncio
import time
import pytest
import httpx
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.dhan_client import DhanClient

@pytest.mark.asyncio
async def test_verify_credentials_success():
    client = DhanClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"dhanClientId": "1000000001", "name": "Trader One"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await client.verify_credentials("1000000001", "valid_token")
        assert res["valid"] is True
        assert res["data"]["dhanClientId"] == "1000000001"
    await client.close()

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
    await client.close()

@pytest.mark.asyncio
async def test_verify_credentials_forbidden_403():
    client = DhanClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await client.verify_credentials("1000000001", "forbidden_token")
        assert res["valid"] is False
        assert "Invalid or expired" in res["error"]
    await client.close()

@pytest.mark.asyncio
async def test_verify_credentials_fallback_to_fundlimit():
    client = DhanClient()
    resp_profile = MagicMock(status_code=404)
    resp_fund = MagicMock(status_code=200)
    resp_fund.json.return_value = {"availMargin": 50000.0}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_profile, resp_fund]
        res = await client.verify_credentials("1000000001", "valid_token")
        assert res["valid"] is True
        assert res["data"]["availMargin"] == 50000.0
        assert mock_get.call_count == 2
    await client.close()

@pytest.mark.asyncio
async def test_verify_credentials_network_error():
    client = DhanClient()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        res = await client.verify_credentials("1000000001", "valid_token")
        assert res["valid"] is False
        assert "Network error" in res["error"]
    await client.close()

@pytest.mark.asyncio
async def test_rate_limiter_pacing():
    client = DhanClient(rps_limit=5, min_spacing=0.05)
    t0 = time.monotonic()
    # Call throttle multiple times sequentially
    await client._throttle()
    await client._throttle()
    await client._throttle()
    t1 = time.monotonic()
    # At 0.05s spacing across 3 calls, elapsed should be at least ~0.09s
    assert (t1 - t0) >= 0.08
    await client.close()

def test_parse_dhan_timestamps_epoch_seconds():
    client = DhanClient()
    # 1710000000 is 2024-03-09 16:00:00 UTC -> 2024-03-09 21:30:00 IST
    timestamps = [1710000000, 1710000300]
    parsed = client._parse_dhan_timestamps(timestamps)
    assert len(parsed) == 2
    assert parsed.tz is None  # Check tz is stripped to naive
    assert parsed[0].hour == 21
    assert parsed[0].minute == 30

def test_parse_dhan_timestamps_epoch_strings():
    client = DhanClient()
    timestamps = ["1710000000", "1710000300"]
    parsed = client._parse_dhan_timestamps(timestamps)
    assert len(parsed) == 2
    assert parsed[0].hour == 21

def test_parse_dhan_timestamps_iso_and_empty():
    client = DhanClient()
    # Empty
    assert len(client._parse_dhan_timestamps([])) == 0

    # ISO strings UTC
    timestamps = ["2024-03-09T16:00:00Z"]
    parsed = client._parse_dhan_timestamps(timestamps)
    assert len(parsed) == 1
    assert parsed[0].hour == 21  # UTC + 5:30 IST

    # Naive strings
    naive = ["2024-03-09 09:15:00"]
    parsed_naive = client._parse_dhan_timestamps(naive)
    assert parsed_naive[0].hour == 9
    assert parsed_naive[0].minute == 15

@pytest.mark.asyncio
async def test_fetch_intraday_candles_success():
    client = DhanClient(min_spacing=0.01)
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [99.0, 101.0],
        "close": [103.0, 104.0],
        "volume": [1500, 2500],
        "start_Time": [1710000000, 1710000300]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        df = await client.fetch_intraday_candles(
            client_id="10001",
            access_token="tok",
            security_id="1333",
            exchange_segment="NSE_EQ"
        )
        assert not df.empty
        assert len(df) == 2
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert df["close"].iloc[0] == 103.0
    await client.close()

@pytest.mark.asyncio
async def test_fetch_intraday_candles_nested_data():
    client = DhanClient(min_spacing=0.01)
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "data": {
            "open": [200.0],
            "high": [205.0],
            "low": [198.0],
            "close": [202.0],
            "volume": [5000],
            "timestamp": [1710000000]
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        df = await client.fetch_intraday_candles(
            client_id="10001",
            access_token="tok",
            security_id="13",
            exchange_segment="IDX_I"
        )
        assert not df.empty
        assert len(df) == 1
        assert df["close"].iloc[0] == 202.0
    await client.close()

@pytest.mark.asyncio
async def test_fetch_intraday_candles_rate_limit_429_retry():
    client = DhanClient(min_spacing=0.01)
    resp_429 = MagicMock(status_code=429)
    resp_200 = MagicMock(status_code=200)
    resp_200.json.return_value = {
        "open": [100.0],
        "high": [105.0],
        "low": [99.0],
        "close": [104.0],
        "volume": [1000],
        "start_Time": [1710000000]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_429, resp_200]
            df = await client.fetch_intraday_candles(
                client_id="10001",
                access_token="tok",
                security_id="1333",
                exchange_segment="NSE_EQ"
            )
            assert not df.empty
            assert len(df) == 1
            assert mock_post.call_count == 2
            mock_sleep.assert_called()
    await client.close()

@pytest.mark.asyncio
async def test_fetch_intraday_candles_error_returns_empty():
    client = DhanClient(min_spacing=0.01)
    mock_resp = MagicMock(status_code=500)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        df = await client.fetch_intraday_candles(
            client_id="10001",
            access_token="tok",
            security_id="1333",
            exchange_segment="NSE_EQ"
        )
        assert df.empty
    await client.close()

@pytest.mark.asyncio
async def test_verify_credentials_fallback_error_reports_status_code():
    client = DhanClient()
    resp_profile = MagicMock(status_code=404)
    resp_fund = MagicMock(status_code=502)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_profile, resp_fund]
        res = await client.verify_credentials("1000000001", "valid_token")
        assert res["valid"] is False
        assert "HTTP 502" in res["error"]
    await client.close()

@pytest.mark.asyncio
async def test_fetch_intraday_candles_corrupt_payload_returns_empty():
    client = DhanClient(min_spacing=0.01)
    mock_resp = MagicMock(status_code=200)
    # Corrupt payload: mismatched array length causing DataFrame construction error
    mock_resp.json.return_value = {
        "open": [100.0, 101.0],
        "high": [105.0],
        "low": [99.0],
        "close": [104.0, 105.0],
        "volume": [1000],
        "start_Time": [1710000000]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        df = await client.fetch_intraday_candles(
            client_id="10001",
            access_token="tok",
            security_id="1333",
            exchange_segment="NSE_EQ"
        )
        assert df.empty
    await client.close()

@pytest.mark.asyncio
async def test_fetch_marketfeed_quotes_chunks_large_request():
    client = DhanClient(min_spacing=0.01)
    # Request 213 securities on NSE_EQ
    large_securities = {"NSE_EQ": [i for i in range(1, 214)]}

    resp1 = MagicMock(status_code=200)
    resp1.json.return_value = {"data": {"NSE_EQ": {str(i): {"last_price": float(i)} for i in range(1, 101)}}}

    resp2 = MagicMock(status_code=200)
    resp2.json.return_value = {"data": {"NSE_EQ": {str(i): {"last_price": float(i)} for i in range(101, 201)}}}

    resp3 = MagicMock(status_code=200)
    resp3.json.return_value = {"data": {"NSE_EQ": {str(i): {"last_price": float(i)} for i in range(201, 214)}}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp1, resp2, resp3]
        quotes = await client.fetch_marketfeed_quotes("10001", "tok", large_securities)

        assert len(quotes.get("NSE_EQ", {})) == 213
        assert mock_post.call_count == 3
        # Check payload chunking: each call should send <= 100 instruments
        for call_arg in mock_post.call_args_list:
            payload = call_arg.kwargs["json"]
            assert len(payload["NSE_EQ"]) <= 100
    await client.close()


