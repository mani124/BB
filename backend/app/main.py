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

    # Finding 7: Protect state-changing API routes from unauthorized cross-origin / CSRF mutations
    from urllib.parse import urlparse
    from fastapi.responses import JSONResponse
    from fastapi import Request

    ALLOWED_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "options.34-14-178-224.sslip.io", "34.14.178.224"}

    @app.middleware("http")
    async def verify_state_mutation_origin(request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            target_header = origin or referer
            if target_header:
                try:
                    host = urlparse(target_header).hostname
                    if host and host not in ALLOWED_ORIGIN_HOSTS and not host.endswith(".sslip.io"):
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: Unauthorized cross-origin mutation request blocked."}
                        )
                except Exception:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: Malformed origin header."}
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
