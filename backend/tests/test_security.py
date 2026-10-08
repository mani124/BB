import logging
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from app.core.security import sanitize_token, get_dhan_credentials, RedactingFilter

def test_sanitize_token():
    assert sanitize_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9") == "eyJ...VCJ9"
    assert sanitize_token("short") == "***"
    assert sanitize_token("") == ""

def test_get_dhan_credentials_success():
    request = MagicMock()
    request.headers = {
        "X-Dhan-Client-Id": "1000000001",
        "X-Dhan-Access-Token": "secret_access_token_12345"
    }
    client_id, token = get_dhan_credentials(request)
    assert client_id == "1000000001"
    assert token == "secret_access_token_12345"

def test_get_dhan_credentials_missing():
    request = MagicMock()
    request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        get_dhan_credentials(request)
    assert exc_info.value.status_code == 401

def test_redacting_filter():
    log_filter = RedactingFilter(patterns=["secret_token"])
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Logging secret_token here",
        args=(),
        exc_info=None
    )
    log_filter.filter(record)
    assert "secret_token" not in record.msg
    assert "[REDACTED]" in record.msg
