import time

from app.core import security
from app.core.config import settings


def test_session_token_valid_and_survives_without_server_state():
    tok = security.issue_session_token()
    assert security.is_valid_session_token(tok)


def test_session_token_rejects_tamper_expiry_and_key_rotation(monkeypatch):
    tok = security.issue_session_token()
    nonce, exp, sig = tok.split(".")
    assert not security.is_valid_session_token(f"{nonce}.{int(exp) + 999}.{sig}")
    assert not security.is_valid_session_token("junk")
    monkeypatch.setattr(time, "time", lambda: float(exp) + 1)
    assert not security.is_valid_session_token(tok)
    monkeypatch.undo()
    monkeypatch.setattr(settings, "DASHBOARD_CAPABILITY", "another-key")
    assert not security.is_valid_session_token(tok)
