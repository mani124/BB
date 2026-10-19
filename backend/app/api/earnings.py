"""Stock earnings options book: calendar, IV history, positions, previews and manual controls (paper only)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.earnings_registry import get_engine

router = APIRouter(prefix="/earnings", tags=["earnings"])


class CalendarRow(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    earnings_date: str  # YYYY-MM-DD
    session: str = ""  # BMO, AMC or empty (uses the "unspecified session" setting)
    sector: str = ""
    note: str = ""


class CalendarBulk(BaseModel):
    rows: list[CalendarRow] = Field(min_length=1, max_length=1000)


class IvPoint(BaseModel):
    symbol: str
    day: str
    iv: float = Field(gt=0)
    spot: float = 0.0


class IvBulk(BaseModel):
    points: list[IvPoint] = Field(min_length=1, max_length=20000)


@router.get("/summary")
async def summary() -> dict:
    return get_engine().summary()


@router.get("/positions")
async def positions(status: Optional[str] = Query(None, pattern="^(OPEN|CLOSED)$")) -> list[dict]:
    return get_engine().positions(status)


@router.get("/candidates")
async def candidates() -> list[dict]:
    """What the engine would do right now (needs a connected Dhan session). Nothing is opened or logged."""
    return await get_engine().preview()


@router.get("/calendar")
async def get_calendar() -> list[dict]:
    return get_engine().calendar_view()


@router.post("/calendar/sync")
async def sync_calendar() -> dict:
    """Pull financial-result dates for F&O stocks from the NSE event calendar now."""
    res = await get_engine().sync_calendar(force=True)
    if res["status"] == "error":
        raise HTTPException(status_code=502, detail=f"NSE calendar fetch failed: {res['error']}")
    return res


@router.post("/calendar")
async def add_calendar(body: CalendarBulk) -> list[dict]:
    store = get_engine().store
    from datetime import date
    try:
        # Validate every row before writing any, so a bad row never leaves the calendar half-updated.
        for r in body.rows:
            date.fromisoformat(r.earnings_date)
            if not r.symbol.strip():
                raise ValueError("symbol is required")
            if (r.session or "").strip().upper() not in ("", "BMO", "AMC"):
                raise ValueError("session must be BMO, AMC or empty")
        for r in body.rows:
            store.upsert_calendar(r.symbol, r.earnings_date, r.session, r.sector, r.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return get_engine().calendar_view()


@router.delete("/calendar/{symbol}/{earnings_date}")
async def delete_calendar(symbol: str, earnings_date: str) -> dict:
    try:
        removed = get_engine().store.delete_calendar(symbol, earnings_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="No such calendar row")
    return {"status": "deleted"}


@router.post("/iv-history")
async def import_iv_history(body: IvBulk) -> dict:
    """Backfill daily at-the-money IV so IV percentile / rank work before the engine has recorded enough days."""
    from datetime import date
    store = get_engine().store
    n = 0
    try:
        parsed = [(p.symbol.strip().upper(), date.fromisoformat(p.day), p.iv, p.spot) for p in body.points]
        for sym, day, iv, spot in parsed:
            store.record_iv(sym, day, iv, spot)
            n += 1
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"imported": n}


@router.post("/run-cycle")
async def run_cycle() -> dict:
    """Run one scan / mark / exit pass now."""
    return await get_engine().run_cycle()


@router.post("/square-off")
async def square_off() -> dict:
    return {"closed": await get_engine().square_off_all("MANUAL_SQUARE_OFF")}
