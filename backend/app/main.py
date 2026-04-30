from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.providers import router as providers_router
from app.api.sessions import router as sessions_router
from app.core.config import get_settings
from app.storage.sqlite import SQLiteStore


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    store = SQLiteStore(settings.sqlite_path)
    store.initialize()
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    app.include_router(providers_router)
    app.include_router(sessions_router)

    frontend_dist = Path(settings.frontend_dist_path)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
