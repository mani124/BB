import logging
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import get_dhan_credentials, sanitize_token
from app.services.dhan_client import DhanClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
dhan_client = DhanClient()


class OAuthTokenRequest(BaseModel):
    app_id: str = Field(..., min_length=1, description="Dhan App ID / Client ID")
    app_secret: str = Field(..., min_length=1, description="Dhan App Secret")
    consent_id: str = Field(..., min_length=1, description="OAuth consent ID from redirect")


@router.get("/oauth/login-url")
def get_oauth_login_url(
    app_id: str = Query(..., min_length=1, description="Dhan App ID / Client ID"),
    redirect_uri: Optional[str] = Query(None, description="Redirect URI after consent"),
):
    app_id_clean = app_id.strip()
    query_parts = [f"client_id={app_id_clean}"]
    if redirect_uri and redirect_uri.strip():
        query_parts.append(f"redirect_uri={redirect_uri.strip()}")
    query_str = "&".join(query_parts)
    login_url = f"{settings.DHAN_LOGIN_URL}?{query_str}"
    return {"login_url": login_url}


@router.post("/oauth/token")
async def exchange_oauth_token(payload: OAuthTokenRequest):
    headers = {
        "app-id": payload.app_id.strip(),
        "app-secret": payload.app_secret.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "consentId": payload.consent_id.strip(),
        "consent_id": payload.consent_id.strip(),
        "app_id": payload.app_id.strip(),
        "app_secret": payload.app_secret.strip(),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(settings.DHAN_TOKEN_URL, headers=headers, json=body)
    except Exception as e:
        logger.error(f"Failed to communicate with Dhan OAuth token endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dhan authentication server unreachable: {e}",
        )

    if resp.status_code != 200:
        logger.warning(f"Dhan OAuth exchange failed with status {resp.status_code}: {resp.text}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Dhan token exchange failed: {resp.text}",
        )

    try:
        data = resp.json()
        if hasattr(data, "__await__"):
            data = await data
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response format from Dhan authentication server",
        )

    resp_data = data.get("data") if isinstance(data.get("data"), dict) else data
    if data.get("status") in ["failure", "error"] or not resp_data:
        err_msg = data.get("remarks") or data.get("message") or data.get("error") or "Dhan OAuth token exchange rejected"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

    client_id = str(
        resp_data.get("dhanClientId")
        or resp_data.get("client_id")
        or resp_data.get("clientId")
        or ""
    ).strip()
    access_token = str(
        resp_data.get("accessToken")
        or resp_data.get("access_token")
        or ""
    ).strip()
    expires_in = resp_data.get("expiresIn") or resp_data.get("expires_in") or 86400

    if not client_id or not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete token response received from Dhan",
        )

    try:
        expires_in_hours = int(expires_in) // 3600
        if expires_in_hours <= 0:
            expires_in_hours = 24
    except (ValueError, TypeError):
        expires_in_hours = 24

    from app.main import worker
    worker.set_session_credentials(client_id, access_token)

    return {
        "status": "connected",
        "client_id": client_id,
        "masked_token": sanitize_token(access_token),
        "expires_in_hours": expires_in_hours,
    }


@router.post("/verify")
async def verify_token(request: Request, creds: tuple[str, str] = Depends(get_dhan_credentials)):
    client_id, access_token = creds
    result = await dhan_client.verify_credentials(client_id, access_token)
    
    # Notify scanner worker if valid
    from app.main import worker
    if result.get("valid"):
        worker.set_session_credentials(client_id, access_token)
        # trigger immediate scan with live credentials
        import asyncio
        asyncio.create_task(worker.run_single_scan_cycle(client_id, access_token))
        
    return {
        "client_id": client_id,
        "token_masked": sanitize_token(access_token),
        "valid": result.get("valid", False),
        "error": result.get("error")
    }

@router.post("/disconnect")
def disconnect_session():
    from app.main import worker
    worker.set_session_credentials(None, None)
    return {"status": "disconnected", "mode": "demo"}
