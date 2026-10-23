from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictInt

from app.core.config import settings
from app.services.ui_store import UiStore, UiStoreError

router = APIRouter(prefix="/ui", tags=["ui"])

_store: UiStore | None = None


def get_store() -> UiStore:
    global _store
    if _store is None or _store.db_path != settings.DB_PATH:
        _store = UiStore(settings.DB_PATH)
    return _store


class LayoutBody(BaseModel):
    kind: str = "custom"
    schema_version: StrictInt
    body: dict[str, Any]


def _raise(e: UiStoreError) -> None:
    raise HTTPException(status_code=e.status, detail=e.message)


@router.get("/layouts")
async def list_layouts():
    return get_store().list()


@router.put("/layouts/{name}")
async def put_layout(name: str, payload: LayoutBody):
    try:
        return get_store().put(name, payload.body, payload.schema_version)
    except UiStoreError as e:
        _raise(e)
    except ValueError:
        raise HTTPException(status_code=422, detail="Layout body must be plain JSON.")


@router.delete("/layouts/{name}")
async def delete_layout(name: str):
    try:
        return {"deleted": get_store().delete(name)}
    except UiStoreError as e:
        _raise(e)


@router.get("/layouts/{name}/snapshots")
async def layout_snapshots(name: str):
    try:
        return get_store().snapshots(name)
    except UiStoreError as e:
        _raise(e)


@router.post("/layouts/{name}/restore/{snapshot_id}")
async def restore_layout(name: str, snapshot_id: int):
    try:
        return get_store().restore(name, snapshot_id)
    except UiStoreError as e:
        _raise(e)
