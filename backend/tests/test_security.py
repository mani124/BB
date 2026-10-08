import logging
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from app.core.security import (
    sanitize_token,
    get_dhan_credentials,
    get_optional_dhan_credentials,
    RedactingFilter,
    setup_security_logging
)

def test_sanitize_token():
    assert sanitize_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9") == "eyJ...VCJ9"
    assert sanitize_token("short") == "***"
    assert sanitize_token("12345678") == "***"
    assert sanitize_token("123456789") == "123...6789"
    assert sanitize_token("") == ""
    assert sanitize_token(None) == ""

def test_get_dhan_credentials_success():
    request = MagicMock()
    request.headers = {
        "X-Dhan-Client-Id": " 1000000001 ",
        "X-Dhan-Access-Token": " secret_access_token_12345 "
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

    request.headers = {"X-Dhan-Client-Id": "1000000001"}
    with pytest.raises(HTTPException) as exc_info:
        get_dhan_credentials(request)
    assert exc_info.value.status_code == 401

    request.headers = {"X-Dhan-Access-Token": "secret_token"}
    with pytest.raises(HTTPException) as exc_info:
        get_dhan_credentials(request)
    assert exc_info.value.status_code == 401

def test_get_optional_dhan_credentials():
    request = MagicMock()
    request.headers = {}
    cid, tok = get_optional_dhan_credentials(request)
    assert cid is None
    assert tok is None

    request.headers = {"X-Dhan-Client-Id": " 1000000001 "}
    cid, tok = get_optional_dhan_credentials(request)
    assert cid == "1000000001"
    assert tok is None

    request.headers = {
        "X-Dhan-Client-Id": "1000000001",
        "X-Dhan-Access-Token": "token123"
    }
    cid, tok = get_optional_dhan_credentials(request)
    assert cid == "1000000001"
    assert tok == "token123"

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

def test_redacting_filter_args_and_jwt():
    log_filter = RedactingFilter(patterns=["user_secret_data"])
    
    # Test tuple args formatting redaction
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Received credential: %s and %s",
        args=("user_secret_data", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"),
        exc_info=None
    )
    log_filter.filter(record)
    assert "user_secret_data" not in record.args[0]
    assert record.args[0] == "[REDACTED]"
    assert "eyJ" not in record.args[1]
    assert record.args[1] == "[REDACTED]"

    # Test dict args redaction
    record_dict = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Credentials payload %(token)s",
        args=({"token": "user_secret_data"},),
        exc_info=None
    )
    log_filter.filter(record_dict)
    assert record_dict.args["token"] == "[REDACTED]"

def test_setup_security_logging():
    setup_security_logging()
    root_logger = logging.getLogger()
    assert any(isinstance(f, RedactingFilter) for f in root_logger.filters)
