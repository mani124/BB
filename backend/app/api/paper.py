from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.paper_trader import paper_trader, PaperPortfolio, PaperPosition
from app.services.strategy_engine import Signal

router = APIRouter(prefix="/paper", tags=["paper"])

class ManualTradeRequest(BaseModel):
    signal: Signal
    lots: Optional[int] = 1
    feed_mode: Optional[str] = None

class SettingsRequest(BaseModel):
    auto_trade_enabled: Optional[bool] = None
    default_lots: Optional[int] = None
    max_risk_per_trade: Optional[float] = None

@router.get("/portfolio")
def get_portfolio() -> PaperPortfolio:
    return paper_trader.get_portfolio()

@router.post("/trade")
def open_manual_trade(body: ManualTradeRequest) -> PaperPosition:
    mode = body.feed_mode
    if not mode:
        try:
            from app.main import worker
            if hasattr(worker, "_state") and getattr(worker._state, "active_mode", None):
                mode = worker._state.active_mode
            elif hasattr(worker, "active_mode"):
                mode = getattr(worker, "active_mode")
        except Exception:
            mode = None
    if not mode:
        if getattr(body.signal.strike_recommendation, "is_live_quote", False):
            mode = "live"
        else:
            mode = "demo"

    if mode == "live" and not getattr(body.signal, "is_confirmed", True):
        raise HTTPException(
            status_code=400,
            detail="Cannot enter trade on unconfirmed provisional candle setup. Please await candle completion."
        )

    rec = body.signal.strike_recommendation
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

    pos = paper_trader.open_position_from_signal(body.signal, lots=body.lots, feed_mode=mode)
    if not pos:
        raise HTTPException(status_code=400, detail="Position already exists or was skipped for this signal")
    return pos

class ClosePositionRequest(BaseModel):
    reason: Optional[str] = "Manual User Exit"
    exit_price: Optional[float] = None
    real_bid_price: Optional[float] = None
    real_opt_price: Optional[float] = None

@router.post("/close/{position_id}")
def close_trade(position_id: str, body: Optional[ClosePositionRequest] = None):
    reason = body.reason if (body and body.reason) else "Manual User Exit"
    exit_price = body.exit_price if body else None
    real_bid_price = body.real_bid_price if body else None
    real_opt_price = body.real_opt_price if body else None

    pos_to_close = next((p for p in paper_trader.get_portfolio().active_positions if p.id == position_id), None)
    if pos_to_close and pos_to_close.feed_mode == "live":
        try:
            from app.main import worker
            sec_id = pos_to_close.option_security_id
            if sec_id:
                candle_forming = getattr(worker, "_option_forming_candle", {}).get(sec_id)
                if candle_forming and candle_forming.get("close", 0) > 0 and real_opt_price is None:
                    real_opt_price = float(candle_forming["close"])
        except Exception:
            pass

        if real_bid_price is None and real_opt_price is None and exit_price is None:
            if "(Modeled" not in reason:
                reason = f"{reason} (Modeled: Unquoted)"

    closed = paper_trader.close_position(
        position_id,
        reason=reason,
        exit_price=exit_price,
        real_bid_price=real_bid_price,
        real_opt_price=real_opt_price,
    )
    if not closed:
        raise HTTPException(status_code=404, detail="Position not found")
    return closed

@router.post("/settings")
def update_settings(body: SettingsRequest):
    if body.auto_trade_enabled is not None:
        paper_trader.set_auto_trade(body.auto_trade_enabled)
    if body.default_lots is not None:
        paper_trader.set_default_lots(body.default_lots)
    if body.max_risk_per_trade is not None:
        paper_trader.set_max_risk_per_trade(body.max_risk_per_trade)
    return paper_trader.get_portfolio()

@router.post("/reset")
def reset_portfolio():
    paper_trader.reset()
    return {"status": "portfolio_reset"}
