from contextlib import asynccontextmanager, suppress
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
from app.api.usage import router as usage_router
from app.api.view import router as view_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.websocket_manager import WebSocketManager
from app.market.akshare_provider import AKShareMarketProvider
from app.market.sync_service import MarketSyncService
from app.scheduler.account_valuation import AccountValuationRefreshService
from app.scheduler.market_sync import create_market_sync_scheduler
from app.sessions.runtime import SessionRunManager
from app.simulator.engine import SimulatorEngine
from app.storage.duckdb import MarketDuckDBStore
from app.storage.sqlite import SQLiteStore
from app.tavily_service import TavilyService
from app.tools.registry import create_default_registry


_asgi_app: FastAPI | None = None


def _get_asgi_app() -> FastAPI:
    global _asgi_app
    if _asgi_app is None:
        _asgi_app = create_app()
    return _asgi_app


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = app.state.market_sync_scheduler
        if scheduler is not None and not scheduler.running:
            scheduler.start()
        account_valuation_service = app.state.account_valuation_refresh_service
        account_valuation_service.start()
        try:
            yield
        finally:
            account_valuation_service = app.state.account_valuation_refresh_service
            await account_valuation_service.stop()
            scheduler = app.state.market_sync_scheduler
            if scheduler is not None:
                with suppress(Exception):
                    if scheduler.running:
                        scheduler.shutdown(wait=False)
            for state_name in ("market_store", "store"):
                resource = getattr(app.state, state_name, None)
                close = getattr(resource, "close", None)
                if close is not None:
                    with suppress(Exception):
                        close()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    store = SQLiteStore(settings.sqlite_path)
    store.initialize()
    market_store = MarketDuckDBStore(settings.market_duckdb_path)
    market_store.initialize()
    app.state.store = store
    app.state.market_store = market_store
    app.state.market_provider = AKShareMarketProvider()
    app.state.websocket_manager = WebSocketManager()
    app.state.market_sync_service = MarketSyncService(
        store=app.state.store,
        market_store=app.state.market_store,
        market_provider=app.state.market_provider,
        websocket_manager=app.state.websocket_manager,
    )
    app.state.market_sync_scheduler = create_market_sync_scheduler(app.state.market_sync_service)
    app.state.account_valuation_refresh_service = AccountValuationRefreshService(
        store=app.state.store,
        market_store=app.state.market_store,
        market_provider=app.state.market_provider,
        quote_coordinator=app.state.market_sync_service.quote_coordinator,
        websocket_manager=app.state.websocket_manager,
    )
    app.state.tavily_service = TavilyService(store=app.state.store, settings=settings)
    app.state.simulator_engine = SimulatorEngine(
        store=app.state.store,
        market_provider=app.state.market_provider,
        enforce_trading_hours=settings.simulator_enforce_trading_hours,
    )
    app.state.tool_registry = create_default_registry(
        market_store=app.state.market_store,
        market_provider=app.state.market_provider,
        simulator_engine=app.state.simulator_engine,
        tavily_service=app.state.tavily_service,
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
    app.include_router(usage_router)
    app.include_router(view_router)
    app.include_router(ws_router)

    frontend_dist = Path(settings.frontend_dist_path)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def get_app() -> FastAPI:
    return create_app()


# Backward-compatible ASGI3 entrypoint for `uvicorn app.main:app --reload`.
# Keep initialization lazy so import/reload does not eagerly lock local DB files.
async def app(scope, receive, send) -> None:
    await _get_asgi_app()(scope, receive, send)
