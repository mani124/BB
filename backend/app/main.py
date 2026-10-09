from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.security import setup_security_logging
from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker
from app.api.auth import router as auth_router
from app.api.universe import router as universe_router
from app.api.signals import router as signals_router
from app.api.paper import router as paper_router

setup_security_logging()

universe_mgr = UniverseManager()
worker = ScannerWorker(universe_mgr=universe_mgr)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-populate initial scan in background
    import asyncio
    asyncio.create_task(worker.run_single_scan_cycle())
    worker.start()
    yield
    await worker.stop()

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5174",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health_check():
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.VERSION,
            "active_mode": worker.get_state().active_mode
        }

    @app.get("/api/debug-dhan")
    async def debug_dhan():
        if not worker._session_credentials:
            return {"error": "no session credentials"}
        cid, tok = worker._session_credentials
        import httpx
        headers = {
            "client-id": cid,
            "access-token": tok,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        tests = [
            {"name": "test1_orig", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "dhanClientId": cid, "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "oi": False, "fromDate": "2026-10-04", "toDate": "2026-10-09"
            }},
            {"name": "test2_interval_str", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "dhanClientId": cid, "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": "15", "oi": False, "fromDate": "2026-10-04", "toDate": "2026-10-09"
            }},
            {"name": "test3_no_oi", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "dhanClientId": cid, "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "fromDate": "2026-10-04", "toDate": "2026-10-09"
            }},
            {"name": "test4_no_dhanClientId", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "fromDate": "2026-10-04", "toDate": "2026-10-09"
            }},
            {"name": "test5_today_only", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "dhanClientId": cid, "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "fromDate": "2026-10-09", "toDate": "2026-10-09"
            }},
            {"name": "test6_no_v2", "url": "https://api.dhan.co/charts/intraday", "json": {
                "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "fromDate": "2026-10-04", "toDate": "2026-10-09"
            }},
            {"name": "test8_datetime_format", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": "15", "oi": False, "fromDate": "2026-10-05 09:15:00", "toDate": "2026-10-09 15:30:00"
            }},
            {"name": "test9_datetime_int_interval", "url": "https://api.dhan.co/v2/charts/intraday", "json": {
                "securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 15, "oi": False, "fromDate": "2026-10-05 09:15:00", "toDate": "2026-10-09 15:30:00"
            }},
            {"name": "test7_sdk", "sdk": True}
        ]
        results = []
        async with httpx.AsyncClient() as c:
            for t in tests:
                if t.get("sdk"):
                    try:
                        from dhanhq import dhanhq
                        d = dhanhq(cid, tok)
                        res = d.intraday_minute_data(security_id="1333", exchange_segment="NSE_EQ", instrument_type="EQUITY", from_date="2026-10-04", to_date="2026-10-09", interval=15)
                        results.append({"name": t["name"], "res": str(res)[:200]})
                    except Exception as e:
                        results.append({"name": t["name"], "error": str(e)})
                    continue
                try:
                    r = await c.post(t["url"], headers=headers, json=t["json"], timeout=10.0)
                    results.append({"name": t["name"], "status": r.status_code, "body": r.text[:200]})
                except Exception as e:
                    results.append({"name": t["name"], "error": str(e)})
        return {"results": results}

    app.include_router(auth_router, prefix=settings.API_PREFIX)
    app.include_router(universe_router, prefix=settings.API_PREFIX)
    app.include_router(signals_router, prefix=settings.API_PREFIX)
    app.include_router(paper_router, prefix=settings.API_PREFIX)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
