import logging
from typing import Optional
import urllib.parse
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
async def get_oauth_login_url(
    app_id: str = Query(..., min_length=1, description="Dhan App ID / API Key"),
    app_secret: Optional[str] = Query(None, description="Dhan App Secret"),
    client_id: Optional[str] = Query(None, description="Dhan Client ID"),
    redirect_uri: Optional[str] = Query(None, description="Redirect URI after consent"),
):
    # If app_secret is provided, call official DhanHQ generate-consent endpoint
    if app_secret and app_secret.strip():
        cid = (client_id or app_id).strip()
        url = f"{settings.DHAN_GENERATE_CONSENT_URL}?client_id={cid}"
        headers = {
            "app_id": app_id.strip(),
            "app-id": app_id.strip(),
            "app_secret": app_secret.strip(),
            "app-secret": app_secret.strip(),
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                consent_app_id = (
                    data.get("consentAppId")
                    or (data.get("data") if isinstance(data.get("data"), dict) else {}).get("consentAppId")
                )
                if consent_app_id:
                    login_url = f"{settings.DHAN_CONSENT_LOGIN_URL}?consentAppId={consent_app_id}"
                    return {"login_url": login_url, "consent_app_id": consent_app_id}
            else:
                logger.warning(f"Dhan generate-consent returned {resp.status_code}: {resp.text}")
                detail_msg = resp.text
                if resp.status_code == 401:
                    detail_msg = "Invalid Dhan credentials: App ID, App Secret, or Client ID did not match. Please verify them in your Dhan Developer Portal."
                raise HTTPException(
                    status_code=resp.status_code if resp.status_code in [400, 401, 403] else status.HTTP_502_BAD_GATEWAY,
                    detail=f"Dhan API authentication rejected ({resp.status_code}): {detail_msg}",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error communicating with Dhan generate-consent: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dhan authentication server unreachable: {e}",
            )

    # Fallback / mock test format
    params = {"client_id": app_id.strip()}
    if redirect_uri and redirect_uri.strip():
        params["redirect_uri"] = redirect_uri.strip()
    query_str = urllib.parse.urlencode(params)
    login_url = f"{settings.DHAN_LOGIN_URL}?{query_str}"
    return {"login_url": login_url}


@router.post("/oauth/token")
async def exchange_oauth_token(payload: OAuthTokenRequest):
    # 1. Try official DhanHQ consumeApp-consent endpoint
    consume_url = f"{settings.DHAN_CONSUME_CONSENT_URL}?tokenId={payload.consent_id.strip()}"
    consume_headers = {
        "app_id": payload.app_id.strip(),
        "app_secret": payload.app_secret.strip(),
        "Accept": "application/json",
    }
    resp = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            consume_resp = await client.post(consume_url, headers=consume_headers)
            if consume_resp.status_code == 200:
                resp = consume_resp
    except Exception as e:
        logger.warning(f"Dhan consumeApp-consent request failed: {e}")

    # 2. Fallback to DHAN_TOKEN_URL
    if resp is None:
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
        or payload.app_id
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
