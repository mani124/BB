from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.api.paper import _resolve_view
from app.core.config import settings
from app.services import daily_journal
from app.services.journal_store import JournalStore, MAX_NOTE_LEN, MAX_TAG_LEN
from app.services.paper_trader import paper_trader

router = APIRouter(prefix="/journal", tags=["journal"])

_store: Optional[JournalStore] = None


def get_store() -> JournalStore:
    global _store
    if _store is None or _store.db_path != settings.DB_PATH:
        _store = JournalStore(settings.DB_PATH)
    return _store


class JournalEntry(BaseModel):
    note: str = Field(default="", max_length=MAX_NOTE_LEN)
    tag: str = Field(default="", max_length=MAX_TAG_LEN)


def _range(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Range is limited to one year")


def _closed():
    return paper_trader._portfolio.closed_trades


@router.get("/trades")
async def list_trades(start: date, end: Optional[date] = None, mode: Optional[str] = None):
    """Closed, non-quarantined trades in the range with their notes (default: a single day)."""
    end = end or start
    _range(start, end)
    notes = get_store().load_all()
    trades = daily_journal.select_trades(_closed(), start, end, _resolve_view(mode))
    return [
        {
            "id": p.id, "date": daily_journal.exit_date(p), "symbol": p.symbol, "strike_symbol": p.strike_symbol,
            "setup_type": p.setup_type, "exit_time": p.exit_time, "exit_reason": p.exit_reason,
            "net_pnl": round(p.net_pnl, 2), **notes.get(p.id, {"note": "", "tag": ""}),
        }
        for p in trades
    ]


@router.put("/trades/{position_id}")
async def save_entry(position_id: str, body: JournalEntry):
    known = next((p for p in _closed() if p.id == position_id and not p.quarantine_reason), None)
    if known is None:
        raise HTTPException(status_code=404, detail="Closed trade not found")
    return get_store().save(position_id, body.note, body.tag)


@router.get("/export.csv")
async def export_csv(start: date, end: Optional[date] = None, mode: Optional[str] = None):
    end = end or start
    _range(start, end)
    trades = daily_journal.select_trades(_closed(), start, end, _resolve_view(mode))
    body = daily_journal.to_csv(trades, get_store().load_all())
    name = f"journal_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/summary")
async def summary_json(day: date, mode: Optional[str] = None):
    trades = daily_journal.select_trades(_closed(), day, day, _resolve_view(mode))
    return daily_journal.summarize(trades, get_store().load_all())


@router.get("/summary.html")
async def summary_html(day: date, mode: Optional[str] = None):
    view = _resolve_view(mode)
    trades = daily_journal.select_trades(_closed(), day, day, view)
    body = daily_journal.render_summary_html(day.isoformat(), trades, get_store().load_all(), view)
    return HTMLResponse(body, headers={
        "Content-Disposition": f'attachment; filename="summary_{day.isoformat()}.html"'})
