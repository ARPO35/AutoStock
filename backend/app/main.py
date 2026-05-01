from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.providers import router as providers_router
from app.api.sessions import router as sessions_router
from app.api.tools import router as tools_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.websocket_manager import WebSocketManager
from app.market.akshare_provider import AKShareMarketProvider
from app.sessions.runtime import SessionRunManager
from app.storage.duckdb import MarketDuckDBStore
from app.storage.sqlite import SQLiteStore
from app.tools.registry import create_default_registry


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    store = SQLiteStore(settings.sqlite_path)
    store.initialize()
    market_store = MarketDuckDBStore(settings.market_duckdb_path)
    market_store.initialize()
    app.state.store = store
    app.state.market_store = market_store
    app.state.market_provider = AKShareMarketProvider()
    app.state.tool_registry = create_default_registry()
    app.state.websocket_manager = WebSocketManager()
    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
    )

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
    app.include_router(tools_router)
    app.include_router(ws_router)

    frontend_dist = Path(settings.frontend_dist_path)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
