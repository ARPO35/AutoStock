from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.data import router as data_router
from app.api.market import router as market_router
from app.api.prompts import router as prompts_router
from app.api.providers import router as providers_router
from app.api.sessions import router as sessions_router
from app.api.simulator import router as simulator_router
from app.api.tavily import router as tavily_router
from app.api.tools import router as tools_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.websocket_manager import WebSocketManager
from app.market.akshare_provider import AKShareMarketProvider
from app.sessions.runtime import SessionRunManager
from app.simulator.engine import SimulatorEngine
from app.storage.duckdb import MarketDuckDBStore
from app.storage.sqlite import SQLiteStore
from app.tools.registry import create_default_registry


class LazyASGIApp:
    def __init__(self, factory):
        self._factory = factory
        self._app: FastAPI | None = None

    def _get_app(self) -> FastAPI:
        if self._app is None:
            self._app = self._factory()
        return self._app

    async def __call__(self, scope, receive, send):
        await self._get_app()(scope, receive, send)


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
    app.state.websocket_manager = WebSocketManager()
    app.state.simulator_engine = SimulatorEngine(
        store=app.state.store,
        market_provider=app.state.market_provider,
        enforce_trading_hours=settings.simulator_enforce_trading_hours,
    )
    app.state.tool_registry = create_default_registry(
        market_store=app.state.market_store,
        market_provider=app.state.market_provider,
        simulator_engine=app.state.simulator_engine,
    )
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
    app.include_router(prompts_router)
    app.include_router(sessions_router)
    app.include_router(tools_router)
    app.include_router(data_router)
    app.include_router(market_router)
    app.include_router(simulator_router)
    app.include_router(tavily_router)
    app.include_router(ws_router)

    frontend_dist = Path(settings.frontend_dist_path)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def get_app() -> FastAPI:
    return create_app()


# Backward-compatible ASGI entrypoint for `uvicorn app.main:app --reload`.
# Keep initialization lazy so import/reload does not eagerly lock local DB files.
app = LazyASGIApp(create_app)
