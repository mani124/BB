import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/signals", tags=["signals"])

@router.get("")
def get_signals_snapshot():
    from app.main import worker
    return worker.get_state().model_dump()

@router.post("/scan-now")
async def trigger_manual_scan():
    from app.main import worker
    state = await worker.run_single_scan_cycle()
    return {"status": "scan_complete", "signals_found": len(state.signals), "cycle": state.scan_cycle_count}

@router.get("/stream")
async def stream_signals(request: Request):
    from app.main import worker
    queue = worker.subscribe()

    async def event_generator():
        try:
            # Send initial state immediately
            initial_data = worker.get_state().model_dump()
            yield f"data: {json.dumps(initial_data)}\n\n"

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next update from worker with a timeout for keepalive
                    data = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Send comment to keep connection alive
                    yield ": ping\n\n"
        except asyncio.CancelledError:
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
