from fastapi import APIRouter, Depends, Request
from app.core.security import get_dhan_credentials, sanitize_token
from app.services.dhan_client import DhanClient

router = APIRouter(prefix="/auth", tags=["auth"])
dhan_client = DhanClient()

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
