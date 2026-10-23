import json
import logging

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.services import action_audit

logger = logging.getLogger(__name__)

_audit: action_audit.ActionAudit | None = None


def get_audit() -> action_audit.ActionAudit:
    global _audit
    if _audit is None or _audit.db_path != settings.DB_PATH:
        _audit = action_audit.ActionAudit(settings.DB_PATH)
    return _audit


class AuditMiddleware(BaseHTTPMiddleware):
    """Records every mutating /api request after the response is known. Registered last, so it also sees the 401 and 403
    answers of the authorization middleware. It never reads the request body."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method not in action_audit.MUTATING or not request.url.path.startswith(settings.API_PREFIX):
            return response
        try:
            action, target, sensitive = action_audit.classify(request.method, request.url.path, settings.API_PREFIX)
            status = response.status_code
            detail = None
            if status >= 400 and not sensitive:
                chunks = [c async for c in response.body_iterator]
                body = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks)
                response = Response(content=body, status_code=status, headers=dict(response.headers), media_type=response.media_type)
                try:
                    d = json.loads(body).get("detail")
                    detail = d if isinstance(d, str) else json.dumps(d)[:300] if d is not None else None
                except (ValueError, AttributeError):
                    detail = None
            fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            client = fwd or (request.client.host if request.client else None)
            await run_in_threadpool(
                get_audit().record, request.method, request.url.path, action, target,
                action_audit.outcome_of(status), status, detail, client,
            )
        except Exception:
            logger.warning("audit middleware failed", exc_info=True)
        return response
