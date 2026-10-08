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
        allow_origins=["*"],
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

    app.include_router(auth_router, prefix=settings.API_PREFIX)
    app.include_router(universe_router, prefix=settings.API_PREFIX)
    app.include_router(signals_router, prefix=settings.API_PREFIX)
    app.include_router(paper_router, prefix=settings.API_PREFIX)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
