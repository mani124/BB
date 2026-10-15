import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.security import setup_security_logging, is_valid_dashboard_capability
from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker
from app.api.auth import router as auth_router
from app.api.universe import router as universe_router
from app.api.signals import router as signals_router
from app.api.paper import router as paper_router
from app.api.cost import router as cost_router
from app.api.position_chart import router as position_chart_router
from app.api.journal import router as journal_router

setup_security_logging()

from app.services.paper_trader import paper_trader
from app.services.notifier import notify

universe_mgr = UniverseManager()
worker = ScannerWorker(universe_mgr=universe_mgr)

@asynccontextmanager
async def lifespan(app: FastAPI):
    cap = settings.DASHBOARD_CAPABILITY.strip()
    if not cap or cap == settings.DEFAULT_DASHBOARD_CAPABILITY:
        # resolve_dashboard_capability() never returns these; guard against a future regression.
        raise RuntimeError("Refusing to start without a private DASHBOARD_CAPABILITY.")
    from app.services import market_hours
    if market_hours.holiday_list_missing_soon():
        logging.getLogger(__name__).error(
            "DATA_QUALITY next year's NSE holiday list is missing; from 1 January every day is "
            "treated as closed until app/services/market_hours.py is updated."
        )
    await paper_trader.start_persistence_worker()
    notify("service_started", f"{settings.APP_NAME} started (v{settings.VERSION}).", min_interval=60)
    worker.start()
    yield
    await worker.stop()
    await paper_trader.stop_persistence_worker()

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan
    )

    from urllib.parse import urlparse
    from fastapi import Request
    from fastapi.responses import JSONResponse

    # Build exact origin allowlist from local dev hosts + deployed origin from env
    _allowed_origins_list = [
        "http://localhost:5174",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5173",
        "https://options.34-14-178-224.sslip.io",
        "http://options.34-14-178-224.sslip.io",
    ]
    _deployed_origin = os.getenv("ALLOWED_ORIGIN", "")
    if _deployed_origin:
        for _o in _deployed_origin.split(","):
            _cleaned = _o.strip().rstrip("/")
            if _cleaned and _cleaned not in _allowed_origins_list:
                _allowed_origins_list.append(_cleaned)

    _ALLOWED_ORIGINS: set[str] = set(_allowed_origins_list)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins_list,
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

    # Finding 1 & Finding 3: Enforce dashboard capability across all mutations and private endpoints
    @app.middleware("http")
    async def verify_dashboard_authorization(request: Request, call_next):
        path = request.url.path
        # CORS preflight carries no credentials; let CORSMiddleware answer it.
        if request.method == "OPTIONS":
            return await call_next(request)
        is_public = (
            path in ("/api/health", "/api/auth/session")
            or not path.startswith(("/api/", "/docs", "/openapi.json", "/redoc"))
        )

        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # /api/auth/session is the bootstrap endpoint that exchanges the secret for session
            if path != "/api/auth/session":
                # 1. Require valid capability token/cookie for ALL mutations
                if not is_valid_dashboard_capability(request):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: Dashboard capability required for mutations."}
                    )

                # 2. Additional browser CSRF protection: validate Origin/Referer if present
                origin = request.headers.get("origin")
                referer = request.headers.get("referer")
                if origin is not None:
                    if origin == "null":
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: null origin is not permitted."}
                        )
                    if origin.rstrip("/") not in _ALLOWED_ORIGINS:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: Unauthorized cross-origin mutation request blocked."}
                        )
                elif referer:
                    try:
                        parsed = urlparse(referer)
                        ref_origin = f"{parsed.scheme}://{parsed.netloc}"
                        if ref_origin.rstrip("/") not in _ALLOWED_ORIGINS:
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Forbidden: Unauthorized origin (via Referer)."}
                            )
                    except Exception:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: Malformed Referer header."}
                        )
        elif not is_public:
            # Private GET / SSE endpoints require capability authorization
            if not is_valid_dashboard_capability(request):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: Dashboard capability required for private endpoints."}
                )

        return await call_next(request)


    app.include_router(auth_router, prefix=settings.API_PREFIX)
    app.include_router(universe_router, prefix=settings.API_PREFIX)
    app.include_router(signals_router, prefix=settings.API_PREFIX)
    app.include_router(paper_router, prefix=settings.API_PREFIX)
    app.include_router(cost_router, prefix=settings.API_PREFIX)
    app.include_router(position_chart_router, prefix=settings.API_PREFIX)
    app.include_router(journal_router, prefix=settings.API_PREFIX)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=os.getenv("DASH_RELOAD", "0") == "1")
