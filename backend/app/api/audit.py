from typing import Optional

from fastapi import APIRouter, Query

from app.core.audit_middleware import get_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/actions")
async def list_actions(limit: int = Query(200, ge=1, le=1000), since: Optional[str] = None,
                       action: Optional[str] = None, outcome: Optional[str] = Query(None, pattern="^(ok|error|denied)$")):
    """Read-only trail of mutating requests, newest first."""
    return get_audit().list_actions(limit=limit, since=since, action=action, outcome=outcome)
