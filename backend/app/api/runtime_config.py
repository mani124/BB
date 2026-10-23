"""Read and change runtime settings (risk limits, quality guards, telemetry, earnings strategy)."""
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.paper_trader import paper_trader
from app.services.runtime_settings import DEFINITIONS, SettingError

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsChange(BaseModel):
    changes: dict[str, Any]


def _payload() -> dict:
    groups: list[str] = []
    for d in DEFINITIONS:
        if d.group not in groups:
            groups.append(d.group)
    return {"groups": groups, "settings": paper_trader.runtime.all()}


@router.get("")
async def get_settings() -> dict:
    return _payload()


@router.put("")
async def update_settings(body: SettingsChange) -> dict:
    """Apply several settings at once. Every value is validated first; nothing is saved if any is invalid."""
    if not body.changes:
        raise HTTPException(status_code=422, detail="No changes supplied.")
    try:
        paper_trader.runtime.set_many(body.changes)
    except SettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _payload()


@router.post("/{key}/reset")
async def reset_setting(key: str) -> dict:
    try:
        paper_trader.runtime.reset(key)
    except SettingError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _payload()


@router.get("/audit")
async def settings_audit(key: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    return paper_trader.runtime.audit(limit=limit, key=key)
