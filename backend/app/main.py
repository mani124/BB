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
            # No origin/referer = direct non-browser client (curl, pytest TestClient, internal).
            # These are allowed to reach the API for internal tooling and tests;
            # network exposure is limited to loopback (127.0.0.1) by the launcher.
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
