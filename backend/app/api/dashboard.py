"""Read-only, source-aware dashboard endpoints."""
import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.services.dashboard_read import list_dashboard_trades, build_dashboard_watch, get_dashboard_session
from app.services.market_hours import now_ist
from app.services.dashboard_evidence import get_trade_evidence

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/watch")
async def watch() -> dict:
    from app.main import worker
    from app.services.cx_registry import get_engine as get_cx_engine
    from app.services.earnings_registry import get_engine as get_earnings_engine

    try:
        scanner = worker.get_state().model_dump()
    except Exception as exc:
        scanner = {"_error": str(exc), "signals": []}
    try:
        cx_engine = get_cx_engine()
        cx = {"summary": cx_engine.summary(), "candidates": await asyncio.wait_for(cx_engine.candidates(), timeout=10)}
    except Exception as exc:
        cx = {"_error": str(exc)}
    try:
        earnings_engine = get_earnings_engine()
        earnings = {"summary": earnings_engine.summary(), "candidates": await earnings_engine.preview_cached()}
    except Exception as exc:
        earnings = {"_error": str(exc)}
    return build_dashboard_watch(scanner, cx, earnings, observed_at=now_ist().isoformat())


@router.get("/trades")
async def trades(
    status: str | None = None,
    book: str | None = None,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> list[dict]:
    return list_dashboard_trades(status=status, book=book, day=day)


@router.get("/session")
def session(day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")) -> dict:
    try:
        return get_dashboard_session(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid calendar day")


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
    trade = _trade(book, position_id)
    # The legacy chart and saved dashboard evidence encode IST wall time as UTC.
    # Convert at this API boundary so the redesigned chart receives real epochs.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    def actual_epoch(value):
        if not value:
            return None
        try:
            stamp = datetime.fromisoformat(str(value))
            return int((stamp.replace(tzinfo=ist) if stamp.tzinfo is None else stamp).timestamp())
        except ValueError:
            return None
    def actual_bar_time(value):
        return actual_epoch(datetime.fromtimestamp(value, ZoneInfo("UTC")).replace(tzinfo=None).isoformat())
    def convert_series(series):
        for item in series:
            item["candles"] = [{**bar, "time": actual_bar_time(bar["time"])} for bar in item["candles"]]
            item["indicators"] = {name: [{**point, "time": actual_bar_time(point["time"])} for point in points]
                                  for name, points in item.get("indicators", {}).items()}
        return series
    if book == "paper":
        from app.api.position_chart import build_position_chart
        data = build_position_chart(position_id)
        series = [{"key": key, "label": key.title(), **data[key]} for key in ("option", "underlying") if data[key]["candles"]]
        return {"candle_state": "recorded" if any(s["key"] == "option" for s in series) else "unavailable",
                "entry_time": actual_epoch(trade.get("opened_at")), "exit_time": actual_epoch(trade.get("closed_at")),
                "series": convert_series(series)}
    evidence = get_trade_evidence(book, position_id)
    series = [{"key": key, "label": key.replace("leg:", "Leg ").title(), "candles": rows,
               "indicators": {}, "levels": {}, "interval": "5m"}
              for key, rows in (evidence or {}).get("bars", {}).items() if rows]
    traded_keys = {"option"} if book == "cx" else {f"leg:{i}" for i in range(len((evidence or {}).get("decision", {}).get("legs", [])))}
    return {"candle_state": "recorded" if any(s["key"] in traded_keys for s in series) else "unavailable",
            "entry_time": actual_epoch(trade.get("opened_at")), "exit_time": actual_epoch(trade.get("closed_at")),
            "series": convert_series(series)}
