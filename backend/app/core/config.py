from functools import lru_cache
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    app_name: str = "AutoStock"
    app_version: str = "0.1.0"
    data_dir: str = "data"
    sqlite_path: str = "data/app.db"
    market_duckdb_path: str = "data/market.duckdb"
    frontend_dist_path: str = "frontend_dist"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    simulator_enforce_trading_hours: bool = True
    tavily_api_key: str = ""
    tavily_default_search_depth: str = "basic"
    tavily_default_topic: str = "finance"
    tavily_default_max_results: int = 5
    tavily_cache_ttl_seconds: int = 1800


@lru_cache
def get_settings() -> Settings:
    cors_origins = os.getenv("AUTOSTOCK_CORS_ORIGINS")
    simulator_enforce_trading_hours = (
        os.getenv("AUTOSTOCK_SIMULATOR_ENFORCE_TRADING_HOURS", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    return Settings(
        app_name=os.getenv("AUTOSTOCK_APP_NAME", "AutoStock"),
        app_version=os.getenv("AUTOSTOCK_APP_VERSION", "0.1.0"),
        data_dir=os.getenv("AUTOSTOCK_DATA_DIR", "data"),
        sqlite_path=os.getenv("AUTOSTOCK_SQLITE_PATH", "data/app.db"),
        market_duckdb_path=os.getenv("AUTOSTOCK_MARKET_DUCKDB_PATH", "data/market.duckdb"),
        frontend_dist_path=os.getenv("AUTOSTOCK_FRONTEND_DIST_PATH", "frontend_dist"),
        cors_origins=(
            [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
            if cors_origins
            else ["http://localhost:5173"]
        ),
        simulator_enforce_trading_hours=simulator_enforce_trading_hours,
        tavily_api_key=os.getenv("AUTOSTOCK_TAVILY_API_KEY", ""),
        tavily_default_search_depth=os.getenv("AUTOSTOCK_TAVILY_DEFAULT_SEARCH_DEPTH", "basic"),
        tavily_default_topic=os.getenv("AUTOSTOCK_TAVILY_DEFAULT_TOPIC", "finance"),
        tavily_default_max_results=_int_env("AUTOSTOCK_TAVILY_DEFAULT_MAX_RESULTS", 5),
        tavily_cache_ttl_seconds=_int_env("AUTOSTOCK_TAVILY_CACHE_TTL_SECONDS", 1800),
    )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
