"""Setup 16 (option squeeze breakout): one overview for the dashboard section that shows what it is doing."""
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.services import market_hours
from app.services.paper_trader import paper_trader
from app.services.setup_stats import compute_setup_stats
from app.services.strategy_engine import SetupType
from app.services.watchlist_registry import get_service

router = APIRouter(prefix="/setup16", tags=["setup16"])

NAME = SetupType.SETUP_16_OPTION_SQUEEZE_BREAK.value
STAGES = ("SIGNAL", "NO_BREAKOUT", "NO_SQUEEZE", "RED_BAR", "LOW_VOLUME", "OUT_OF_WINDOW", "WARMUP", "NO_DATA")
STALE_AFTER_S = 15 * 60


def _is_s16(p: Any) -> bool:
    return "Setup 16" in str(getattr(p, "setup_type", ""))


def _contract_rank(c: dict) -> tuple:
    """Closest to a breakout first: a signal, then squeezed contracts by distance to the upper band."""
    squeezed = 0 if c.get("in_squeeze") else 1
    stage = 0 if c.get("stage") == "SIGNAL" else 1
    dist = c.get("pct_to_upper")
    return (stage, squeezed, dist if isinstance(dist, (int, float)) else 1e9)


def build_overview(worker: Any, now: datetime | None = None) -> dict:
    rt = paper_trader.runtime
    portfolio = paper_trader.get_portfolio(None)
    modes = portfolio.setup_modes or {}

    status = getattr(worker, "_s16_status", {}) or {}
    today = market_hours.now_ist().date().isoformat()
    contracts = [dict(v) for v in status.values()]
    for c in contracts:
        c["stale"] = (time.time() - float(c.get("updated_ts", 0))) > STALE_AFTER_S  # not re-checked recently (market closed or feed gap)
    funnel = {s: 0 for s in STAGES}
    for c in contracts:
        funnel[c.get("stage", "NO_DATA")] = funnel.get(c.get("stage", "NO_DATA"), 0) + 1
    contracts.sort(key=_contract_rank)

    open_pos = [p for p in portfolio.active_positions if _is_s16(p)]
    closed = [p for p in portfolio.closed_trades if _is_s16(p) and not p.quarantine_reason]
    stats = [s.model_dump() for s in compute_setup_stats(closed) if s.date == "ALL"]
    today_closed = [p for p in closed if str(p.exit_datetime or "")[:10] == today]

    def trade_row(p: Any) -> dict:
        return {
            "id": p.id, "strike_symbol": p.strike_symbol, "symbol": p.symbol, "side": p.option_type,
            "entry_time": p.entry_datetime or p.entry_time, "exit_time": p.exit_datetime or p.exit_time,
            "entry": p.option_entry, "stop": p.option_sl, "target_1": p.option_target_1, "target_2": p.option_target_2,
            "price": p.current_option_price, "status": p.status, "exit_reason": p.exit_reason,
            "lots": p.lots, "net_pnl": p.net_pnl if p.status != "OPEN" else p.est_net_pnl,
        }

    skips: list[dict] = []
    try:
        skips = [
            {"ts": r["ts"], "symbol": r["symbol"], "side": r["side"], "decision": r["decision"], "reason": r["reason"]}
            for r in paper_trader.telemetry.decisions(hours=24, strategy=NAME, limit=60)
        ]
    except Exception:
        pass

    wl = get_service().current()
    return {
        "mode": modes.get("16", "off"),
        "settings": {
            "stop_pct": rt.get("setup16_stop_pct"),
            "window_start": rt.get("setup16_window_start"),
            "window_end": rt.get("setup16_window_end"),
        },
        "watchlist": {k: wl.get(k) for k in ("enabled", "built_for", "built_at", "last_bar_day", "screened", "last_cycle")}
        | {"candidates": wl.get("candidates", [])},
        "funnel": funnel,
        "contracts_checked": len(contracts),
        "contracts": contracts[:60],
        "open_positions": [trade_row(p) for p in open_pos],
        "today_closed": [trade_row(p) for p in today_closed],
        "today_net_pnl": round(sum(p.net_pnl for p in today_closed), 2),
        "stats_all_time": stats[0] if stats else None,
        "decisions": skips,
        "as_of": market_hours.now_ist_naive().strftime("%H:%M:%S"),
    }


@router.get("/overview")
async def overview() -> dict:
    from app.main import worker
    return build_overview(worker)
