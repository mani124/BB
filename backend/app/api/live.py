"""Live broker routing: status, mode, the two-step switch to live, broker login, reconcile and audit.

Every mutation here also passes the dashboard-capability middleware in app.main. Going live is two calls
(``/arm`` then ``/enable``) on top of the server's ``LIVE_TRADING_CONFIRM=CONFIRMED`` env flag; ``/mode`` can
only choose ``off`` or ``dry_run``.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.broker_adapter import BrokerError
from app.services.order_router import get_router

router = APIRouter(prefix="/live", tags=["live"])


class ModeBody(BaseModel):
    mode: str


class EnableBody(BaseModel):
    code: str
    phrase: str


class LoginBody(BaseModel):
    totp: str


@router.get("/status")
async def live_status() -> dict:
    return get_router().status()


@router.get("/orders")
async def live_orders(limit: int = Query(100, ge=1, le=500), day: Optional[str] = None) -> list[dict]:
    return get_router().orders(limit=limit, day=day)


@router.get("/audit")
async def live_audit(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return get_router().audit_log(limit=limit)


@router.post("/mode")
async def set_mode(body: ModeBody) -> dict:
    r = get_router()
    try:
        r.set_mode(body.mode)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return r.status()


@router.post("/arm")
async def arm() -> dict:
    try:
        return get_router().arm()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/enable")
async def enable(body: EnableBody) -> dict:
    r = get_router()
    try:
        await r.enable_live(body.code, body.phrase)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return r.status()


@router.post("/resume")
async def resume() -> dict:
    r = get_router()
    await r.resume()
    return r.status()


@router.post("/reconcile")
async def reconcile() -> dict:
    return await get_router().reconcile()


@router.post("/positions/{position_id}/retry-exit")
async def retry_exit(position_id: str) -> dict:
    r = get_router()
    await r.retry_exit(position_id)
    return r.status()


@router.post("/broker/login")
async def broker_login(body: LoginBody) -> dict:
    """Log in to the broker with the 6-digit TOTP. The API token and secret come from the server environment."""
    r = get_router()
    try:
        await r.broker.login(body.totp)  # type: ignore[attr-defined]
    except BrokerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    r.audit("broker_login", f"{r.broker.name} session started")
    return {"broker_session": r.broker.has_session()}


@router.post("/broker/logout")
async def broker_logout() -> dict:
    r = get_router()
    r.broker.clear_session()  # type: ignore[attr-defined]
    r.audit("broker_logout", f"{r.broker.name} session cleared")
    return {"broker_session": r.broker.has_session()}
