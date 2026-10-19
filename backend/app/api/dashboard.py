"""Read-only, source-aware dashboard endpoints."""
import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.services.dashboard_read import list_dashboard_trades, build_dashboard_watch
from app.services.market_hours import now_ist
from app.services.dashboard_evidence import get_trade_evidence

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/watch")
async def watch() -> dict:
    from app.main import worker
    from app.api.setup16 import build_overview
    from app.services.cx_registry import get_engine as get_cx_engine
    from app.services.earnings_registry import get_engine as get_earnings_engine

    try:
        scanner = worker.get_state().model_dump()
    except Exception as exc:
        scanner = {"_error": str(exc), "signals": []}
    try:
        setup16 = build_overview(worker)
    except Exception as exc:
        setup16 = {"_error": str(exc), "contracts": []}
    try:
        cx_engine = get_cx_engine()
        cx = {"summary": cx_engine.summary(), "candidates": await asyncio.wait_for(cx_engine.candidates(), timeout=10)}
    except Exception as exc:
        cx = {"_error": str(exc)}
    try:
        earnings_engine = get_earnings_engine()
        earnings = {"summary": earnings_engine.summary(), "candidates": await asyncio.wait_for(earnings_engine.preview(), timeout=10)}
    except Exception as exc:
        earnings = {"_error": str(exc)}
    return build_dashboard_watch(scanner, setup16, cx, earnings, observed_at=now_ist().isoformat())


@router.get("/trades")
async def trades(
    status: str | None = None,
    book: str | None = None,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> list[dict]:
    return list_dashboard_trades(status=status, book=book, day=day)


def _trade(book: str, position_id: str) -> dict:
    if book not in ("paper", "cx", "earnings"):
        raise HTTPException(status_code=404, detail="Unknown book")
    key = f"{book}:{position_id}"
    row = next((r for r in list_dashboard_trades() if r["id"] == key), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return row


@router.get("/trades/{book}/{position_id}")
def trade_detail(book: str, position_id: str) -> dict:
    trade = _trade(book, position_id)
    evidence = get_trade_evidence(book, position_id)
    return {**trade, "reason_state": "recorded" if evidence and evidence.get("decision") else "unavailable",
            "decision": evidence["decision"] if evidence else None}


@router.get("/trades/{book}/{position_id}/chart")
def trade_chart(book: str, position_id: str) -> dict:
    _trade(book, position_id)
    if book == "paper":
        from app.api.position_chart import build_position_chart
        data = build_position_chart(position_id)
        series = [{"key": key, "label": key.title(), **data[key]} for key in ("option", "underlying") if data[key]["candles"]]
        return {"candle_state": "recorded" if series else "unavailable", "entry_time": data["entry_time"],
                "exit_time": data["exit_time"], "series": series}
    evidence = get_trade_evidence(book, position_id)
    series = [{"key": key, "label": key.replace("leg:", "Leg ").title(), "candles": rows,
               "indicators": {}, "levels": {}, "interval": "5m"}
              for key, rows in (evidence or {}).get("bars", {}).items() if rows]
    return {"candle_state": "recorded" if series else "unavailable", "entry_time": None,
            "exit_time": None, "series": series}
