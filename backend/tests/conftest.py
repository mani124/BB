from starlette.testclient import TestClient
from app.core.config import settings

_original_request = TestClient.request

def _patched_request(self, method, url, *args, **kwargs):
    headers = dict(kwargs.get("headers") or {})
    # If test explicitly wants to test omitted capability:
    if headers.pop("X-Omit-Capability", None) == "1":
        kwargs["headers"] = headers
        return _original_request(self, method, url, *args, **kwargs)

    # For existing test suite: inject capability if neither capability header nor cookie is present
    has_cap = any(k.lower() in ("x-dashboard-capability", "authorization") for k in headers)
    cookies = kwargs.get("cookies") or getattr(self, "cookies", {})
    has_cookie = bool(cookies and "dashboard_session" in cookies)
    if not has_cap and not has_cookie:
        headers["X-Dashboard-Capability"] = settings.DASHBOARD_CAPABILITY
        kwargs["headers"] = headers

    return _original_request(self, method, url, *args, **kwargs)

TestClient.request = _patched_request


import pytest
from datetime import datetime
from app.services import market_hours


@pytest.fixture(autouse=True)
def _pin_in_session_clock():
    """Pin the exchange clock to an in-session instant (Wed 2026-10-14 11:00 IST) so
    existing tests don't depend on the wall clock. Tests of the session guard
    override it with ``market_hours.set_clock``."""
    market_hours.set_clock(datetime(2026, 10, 14, 11, 0, 0, tzinfo=market_hours.IST))
    yield
    market_hours.set_clock(None)


@pytest.fixture
def no_reentry_cooldown(monkeypatch):
    """For tests that exercise re-entry logic itself (not the cooldown) and exit and
    re-enter the same stock/side within the same pinned instant."""
    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
