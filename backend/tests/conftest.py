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
