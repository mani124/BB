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

from app.services.paper_trader import paper_trader

universe_mgr = UniverseManager()
worker = ScannerWorker(universe_mgr=universe_mgr)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await paper_trader.start_persistence_worker()
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

    import os
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

    # Finding 1 (post-fix): Use an exact allowed-origin set; reject null and unauthorized origins for writes
    @app.middleware("http")
    async def verify_state_mutation_origin(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")

            referer = request.headers.get("referer")
            # Browser requests MUST carry a valid Origin header that is in the allowlist
            if origin is not None:
                # Reject "null" origin (sandboxed iframe / cross-origin redirect)
                if origin == "null":
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: null origin is not permitted."}
                    )
                # Exact match only — no suffix / hostname logic
                if origin.rstrip("/") not in _ALLOWED_ORIGINS:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: Unauthorized cross-origin mutation request blocked."}
                    )
            elif referer:
                # Extract origin from Referer for same-origin form POSTs
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
            else:
                # Direct non-browser client (no Origin, no Referer).
                # Require valid capability token via X-Dashboard-Capability or Authorization header.
                cap_header = request.headers.get("X-Dashboard-Capability") or request.headers.get("x-dashboard-capability")
                auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
                expected_cap = settings.DASHBOARD_CAPABILITY

                is_authorized = False
                if cap_header and cap_header.strip() == expected_cap:
                    is_authorized = True
                elif auth_header:
                    token = auth_header.strip()
                    if token.startswith("Bearer "):
                        token = token[7:].strip()
                    if token == expected_cap:
                        is_authorized = True

                if not is_authorized:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: Dashboard capability required for direct-client mutations."}
                    )
        return await call_next(request)


    app.include_router(auth_router, prefix=settings.API_PREFIX)
    app.include_router(universe_router, prefix=settings.API_PREFIX)
    app.include_router(signals_router, prefix=settings.API_PREFIX)
    app.include_router(paper_router, prefix=settings.API_PREFIX)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
