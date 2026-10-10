import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.api.paper import ClosePositionRequest

router = APIRouter(prefix="/signals", tags=["signals"])

@router.get("")
@router.get("/snapshot")
@router.get("/state")
def get_signals_snapshot():
    from app.main import worker
    return worker.get_state().model_dump()

@router.post("/scan-now")
async def trigger_manual_scan():
    from app.main import worker
    state = await worker.run_single_scan_cycle()
    return {"status": "scan_complete", "signals_found": len(state.signals), "cycle": state.scan_cycle_count}

SSE_PING_INTERVAL = 10.0

@router.get("/stream")
async def stream_signals(request: Request, max_events: Optional[int] = None):
    from app.main import worker
    queue = worker.subscribe()

    async def event_generator():
        count = 0
        try:
            # Send initial state immediately
            initial_data = worker.get_state().model_dump()
            yield f"data: {json.dumps(initial_data)}\n\n"
            count += 1
            if max_events is not None and count >= max_events:
                return

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next update from worker with a timeout for keepalive
                    data = await asyncio.wait_for(queue.get(), timeout=SSE_PING_INTERVAL)
                    if hasattr(data, "model_dump"):
                        data = data.model_dump()
                    if isinstance(data, dict) and data.get("type") == "tick":
                        yield f"event: tick\ndata: {json.dumps(data)}\n\n"
                    else:
                        yield f"data: {json.dumps(data)}\n\n"
                    count += 1
                    if max_events is not None and count >= max_events:
                        break
                except asyncio.TimeoutError:
                    # Send comment to keep connection alive
                    yield ": ping\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            worker.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/close/{position_id}")
def close_trade_signal(position_id: str, body: Optional[ClosePositionRequest] = None):
    # F2 (post-fix): Route through the shared freshness-checking close logic
    # so both /api/paper/close and /api/signals/close apply identical staleness
    # detection and modeled-fill labeling. Do NOT call paper_trader.close_position
    # directly here — that skips freshness gates and lets callers set arbitrary P&L.
    from app.api.paper import _close_position_with_freshness
    if isinstance(body, dict):
        reason = body.get("reason", "Manual User Exit")
        exit_price = body.get("exit_price")
        real_bid_price = body.get("real_bid_price")
        real_opt_price = body.get("real_opt_price")
    elif body is not None:
        reason = body.reason or "Manual User Exit"
        exit_price = body.exit_price
        real_bid_price = body.real_bid_price
        real_opt_price = body.real_opt_price
    else:
        reason = "Manual User Exit"
        exit_price = None
        real_bid_price = None
        real_opt_price = None

    return _close_position_with_freshness(
        position_id,
        reason,
        float(exit_price) if exit_price is not None else None,
        float(real_bid_price) if real_bid_price is not None else None,
        float(real_opt_price) if real_opt_price is not None else None,
    )

