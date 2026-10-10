from starlette.testclient import TestClient
from app.core.config import settings

_original_request = TestClient.request

def _patched_request(self, method, url, *args, **kwargs):
    headers = dict(kwargs.get("headers") or {})
    # If test explicitly wants to test omitted capability:
    if headers.pop("X-Omit-Capability", None) == "1":
        kwargs["headers"] = headers
        return _original_request(self, method, url, *args, **kwargs)

    # For existing tests without headers: inject capability so existing test suite passes
    if method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
        has_origin = any(k.lower() == "origin" for k in headers)
        has_referer = any(k.lower() == "referer" for k in headers)
        has_cap = any(k.lower() in ("x-dashboard-capability", "authorization") for k in headers)
        if not has_origin and not has_referer and not has_cap:
            headers["X-Dashboard-Capability"] = settings.DASHBOARD_CAPABILITY
            kwargs["headers"] = headers

    return _original_request(self, method, url, *args, **kwargs)

TestClient.request = _patched_request
