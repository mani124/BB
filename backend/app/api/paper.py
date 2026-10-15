from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services.paper_trader import paper_trader, PaperPortfolio, PaperPosition, DailyPnl
from app.services.strategy_engine import Signal
from app.services import setup_switches
from app.services.setup_stats import SetupDayStats, compute_setup_stats

router = APIRouter(prefix="/paper", tags=["paper"])

# Every endpoint here is async on purpose: the scanner mutates the paper portfolio on the event
# loop without awaiting in between, so handlers that also run on the loop can never interleave
# with a price update. A plain `def` handler would run in a worker thread and race it.

class ManualTradeRequest(BaseModel):
    signal: Signal
    lots: Optional[int] = Field(default=None, ge=1)  # None -> portfolio default (2 lots)
    feed_mode: Optional[str] = None

class SettingsRequest(BaseModel):
    auto_trade_enabled: Optional[bool] = None
    default_lots: Optional[int] = None
    max_risk_per_trade: Optional[float] = None
    setup_modes: Optional[dict[str, str]] = None
    daily_loss_limit: Optional[float] = Field(default=None, ge=0)  # INR; 0 disables the cap

def _resolve_view(mode: Optional[str]) -> Optional[str]:
    """Which book to show: "live" or "demo" follow the request; "all" is the raw
    combined book; the default ("auto") follows the server's current scan mode so demo
    rows never leak into live totals and vice versa."""
    m = (mode or "auto").lower()
    if m == "all":
        return None
    if m in ("live", "demo"):
        return m
    try:
        from app.main import worker
        return "demo" if getattr(worker._state, "active_mode", "demo") == "demo" else "live"
    except Exception:
        return "demo"

@router.get("/portfolio")
async def get_portfolio(mode: Optional[str] = None) -> PaperPortfolio:
    return paper_trader.get_portfolio(_resolve_view(mode))

@router.get("/daily")
async def get_daily_pnl(mode: Optional[str] = None) -> list[DailyPnl]:
    return paper_trader.get_daily_pnl(_resolve_view(mode))

@router.get("/setup-stats")
async def get_setup_stats(mode: Optional[str] = None) -> list[SetupDayStats]:
    return compute_setup_stats(paper_trader.get_portfolio(_resolve_view(mode)).closed_trades)

@router.post("/trade")
async def open_manual_trade(body: ManualTradeRequest) -> PaperPosition:
    # Finding 3: Reject unconfirmed provisional setups immediately
    if not getattr(body.signal, "is_confirmed", True):
        raise HTTPException(
            status_code=400,
            detail="Cannot enter trade on unconfirmed provisional candle setup. Please await candle completion."
        )

    mode = body.feed_mode
    try:
        from app.main import worker
        server_is_live = (
            worker._session_credentials is not None
            and getattr(worker._state, "active_mode", None) == "live"
        )
    except Exception:
        server_is_live = False

    # F3: Reject live mode entries when server credentials or live feed are absent
    if mode == "live" and not server_is_live:
        raise HTTPException(
            status_code=409,
            detail="Live feed unavailable. Server is running in demo mode or disconnected."
        )

    if not mode:
        mode = "live" if server_is_live else "demo"

    target_signal = body.signal
    if mode == "live":
        try:
            from app.main import worker
            active_signals = getattr(worker._state, "signals", [])
            matched = next((s for s in active_signals if s.id == body.signal.id), None)
            if matched:
                target_signal = matched
            else:
                # Finding 5: Reject forged or unobserved signals in live mode
                raise HTTPException(
                    status_code=400,
                    detail="Live signal not found or has expired in active scan radar. Cannot trade unobserved signals in live mode."
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Signal radar state unavailable for live trade validation."
            ) from exc

        # F3: Re-verify server signal confirmation
        if not getattr(target_signal, "is_confirmed", True):
            raise HTTPException(
                status_code=400,
                detail="Cannot enter trade on unconfirmed provisional candle setup. Await candle close confirmation."
            )

    rec = target_signal.strike_recommendation
    if mode == "live":
        sec_id = getattr(rec, "option_security_id", None)
        is_live = getattr(rec, "is_live_quote", False)
        real_ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
        real_ltp = float(getattr(rec, "real_ltp", 0.0) or 0.0)
        if not sec_id or not str(sec_id).strip() or not (is_live or real_ask > 0 or real_ltp > 0):
            raise HTTPException(
                status_code=400,
                detail="Cannot open live position without a resolved option contract and real live quote."
            )

    pos = paper_trader.open_position_from_signal(target_signal, lots=body.lots, feed_mode=mode)
    if not pos:
        raise HTTPException(status_code=400, detail="Position already exists or was skipped for this signal")
    return pos

class ClosePositionRequest(BaseModel):
    reason: Optional[str] = "Manual User Exit"
    exit_price: Optional[float] = None
    real_bid_price: Optional[float] = None
    real_opt_price: Optional[float] = None


def _close_position_with_freshness(
    position_id: str,
    reason: str,
) -> "PaperPosition":
    """Shared close logic for both /api/paper/close and /api/signals/close.

    F2, F4, F8: Enforces server-owned pricing. All fill prices, bids, and theoretical
    exit metrics are resolved strictly from server-owned data (worker.get_option_quote
    or pos.current_option_price). Caller-supplied price inputs are ignored to protect
    P&L and slippage integrity.
    """
    pos_to_close = next(
        (p for p in paper_trader.get_portfolio().active_positions if p.id == position_id), None
    )
    if not pos_to_close:
        raise HTTPException(status_code=404, detail="Position not found")

    server_bid: Optional[float] = None
    server_ltp: Optional[float] = None

    try:
        from app.main import worker
        sec_id = pos_to_close.option_security_id
        if sec_id:
            quote = worker.get_option_quote(str(sec_id), max_age_s=15.0)
            if quote:
                server_bid = quote.bid
                server_ltp = quote.ltp
    except Exception:
        pass

    if pos_to_close.feed_mode == "live":
        if server_bid is None and server_ltp is None:
            if "(Modeled" not in reason:
                reason = f"{reason} (Modeled: Unquoted)"

    closed = paper_trader.close_position(
        position_id,
        reason=reason,
        exit_price=None,
        real_bid_price=server_bid,
        real_opt_price=server_ltp,
    )
    if not closed:
        raise HTTPException(status_code=404, detail="Position not found")
    return closed


@router.post("/close/{position_id}")
async def close_trade(position_id: str, body: Optional[ClosePositionRequest] = None):
    reason = body.reason if (body and body.reason) else "Manual User Exit"
    return _close_position_with_freshness(position_id, reason)


@router.post("/settings")
async def update_settings(body: SettingsRequest):
    if body.auto_trade_enabled is not None:
        paper_trader.set_auto_trade(body.auto_trade_enabled)
    if body.default_lots is not None:
        paper_trader.set_default_lots(body.default_lots)
    if body.max_risk_per_trade is not None:
        paper_trader.set_max_risk_per_trade(body.max_risk_per_trade)
    if body.daily_loss_limit is not None:
        paper_trader.set_daily_loss_limit(body.daily_loss_limit)
    if body.setup_modes is not None:
        bad = [f"{k}={v}" for k, v in body.setup_modes.items()
               if k not in setup_switches.DEFAULT_MODES or v not in setup_switches.MODES]
        if bad:
            raise HTTPException(status_code=422, detail=f"Invalid setup mode(s): {', '.join(bad)}")
        paper_trader.set_setup_modes(body.setup_modes)
    return paper_trader.get_portfolio(_resolve_view(None))

@router.post("/reset")
async def reset_portfolio():
    await paper_trader.reset()
    return {"status": "portfolio_reset"}


class KillSwitchRequest(BaseModel):
    confirm: bool = False


@router.post("/kill-switch")
async def engage_kill_switch(body: KillSwitchRequest):
    """Pause all new entries and square off every open position (both books). Needs confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Kill switch needs confirm=true.")
    # Engage first so no new entry can slip in while positions are being closed.
    paper_trader.set_kill_switch(True)
    closed, failed = 0, []
    for pos in list(paper_trader.get_portfolio().active_positions):
        try:
            _close_position_with_freshness(pos.id, "KILL_SWITCH")
            closed += 1
        except HTTPException:
            failed.append(pos.id)
    return {"status": "engaged", "closed": closed, "failed": failed, "risk": paper_trader.risk_status(None)}


@router.post("/kill-switch/release")
async def release_kill_switch(body: KillSwitchRequest):
    """Allow new entries again. Needs confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Releasing the kill switch needs confirm=true.")
    paper_trader.set_kill_switch(False)
    return {"status": "released", "risk": paper_trader.risk_status(None)}
