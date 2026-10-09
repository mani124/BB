from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.paper_trader import paper_trader, PaperPortfolio, PaperPosition
from app.services.strategy_engine import Signal

router = APIRouter(prefix="/paper", tags=["paper"])

class ManualTradeRequest(BaseModel):
    signal: Signal
    lots: Optional[int] = 1

class SettingsRequest(BaseModel):
    auto_trade_enabled: Optional[bool] = None
    default_lots: Optional[int] = None
    max_risk_per_trade: Optional[float] = None

@router.get("/portfolio")
def get_portfolio() -> PaperPortfolio:
    return paper_trader.get_portfolio()

@router.post("/trade")
def open_manual_trade(body: ManualTradeRequest) -> PaperPosition:
    pos = paper_trader.open_position_from_signal(body.signal, lots=body.lots)
    if not pos:
        raise HTTPException(status_code=400, detail="Position already exists for this signal")
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
