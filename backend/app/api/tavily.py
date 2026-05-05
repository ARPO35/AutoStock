from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.core.config import get_settings
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/tavily", tags=["tavily"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:6]}{'*' * max(4, len(value) - 12)}{value[-6:]}"


class TavilyConfigRead(BaseModel):
    configured: bool
    api_key_masked: str | None
    default_search_depth: str
    default_topic: str
    default_max_results: int
    cache_ttl_seconds: int
    updated_at: str | None = None


class TavilyConfigUpdate(BaseModel):
    api_key: str | None = Field(default=None, min_length=1)
    default_search_depth: Literal["basic", "advanced"] = "basic"
    default_topic: Literal["general", "news", "finance"] = "finance"
    default_max_results: int = Field(default=5, ge=1, le=20)
    cache_ttl_seconds: int = Field(default=1800, ge=0, le=604800)


class TavilyUsageRead(BaseModel):
    total_calls: int
    cache_hits: int
    credits_estimated: float
    recent: list[dict[str, object]]


class TavilyTestRead(BaseModel):
    ok: bool
    result_count: int = 0
    credits_estimated: float = 0
    latency_ms: float | None = None
    error: str | None = None


@router.get("/config", response_model=TavilyConfigRead)
async def read_config(store: SQLiteStore = Depends(get_store)) -> dict[str, object]:
    return _public_config(store)


@router.put("/config", response_model=TavilyConfigRead)
async def update_config(
    payload: TavilyConfigUpdate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    current = _effective_config(store)
    api_key = payload.api_key if payload.api_key is not None else str(current["api_key"])
    now = utc_now()
    store.execute(
        """
        INSERT INTO tavily_config (
            id, api_key, default_search_depth, default_topic,
            default_max_results, cache_ttl_seconds, created_at, updated_at
        )
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            api_key = excluded.api_key,
            default_search_depth = excluded.default_search_depth,
            default_topic = excluded.default_topic,
            default_max_results = excluded.default_max_results,
            cache_ttl_seconds = excluded.cache_ttl_seconds,
            updated_at = excluded.updated_at
        """,
        (
            api_key,
            payload.default_search_depth,
            payload.default_topic,
            payload.default_max_results,
            payload.cache_ttl_seconds,
            now,
            now,
        ),
    )
    return _public_config(store)


@router.get("/usage", response_model=TavilyUsageRead)
async def read_usage(store: SQLiteStore = Depends(get_store)) -> dict[str, object]:
    totals = store.fetch_one(
        """
        SELECT
            COUNT(*) AS total_calls,
            COALESCE(SUM(cache_hit), 0) AS cache_hits,
            COALESCE(SUM(credits_estimated), 0) AS credits_estimated
        FROM tavily_usage_records
        """
    )
    recent = store.fetch_all(
        """
        SELECT id, session_id, run_id, tool_call_id, operation, cache_hit,
               status, error, latency_ms, result_count, credits_estimated, created_at
        FROM tavily_usage_records
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return {
        "total_calls": int(totals["total_calls"]) if totals else 0,
        "cache_hits": int(totals["cache_hits"]) if totals else 0,
        "credits_estimated": float(totals["credits_estimated"]) if totals else 0.0,
        "recent": recent,
    }


@router.post("/test", response_model=TavilyTestRead)
async def test_tavily(request: Request) -> dict[str, object]:
    try:
        result = await request.app.state.tavily_service.search(
            {"query": "A股 市场 新闻", "search_depth": "basic", "max_results": 1},
            runtime_context={"session_id": None, "run_id": None, "tool_call_id": None},
            use_cache=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "ok": True,
        "result_count": int(result.get("result_count") or 0),
        "credits_estimated": float(result.get("credits_estimated") or 0),
        "latency_ms": result.get("latency_ms"),
    }


def _public_config(store: SQLiteStore) -> dict[str, object]:
    config = _effective_config(store)
    api_key = str(config["api_key"])
    return {
        "configured": bool(api_key),
        "api_key_masked": mask_api_key(api_key),
        "default_search_depth": config["default_search_depth"],
        "default_topic": config["default_topic"],
        "default_max_results": config["default_max_results"],
        "cache_ttl_seconds": config["cache_ttl_seconds"],
        "updated_at": config.get("updated_at"),
    }


def _effective_config(store: SQLiteStore) -> dict[str, object]:
    row = store.fetch_one("SELECT * FROM tavily_config WHERE id = 'default'")
    settings = get_settings()
    if row:
        return {
            "api_key": str(row["api_key"] or settings.tavily_api_key),
            "default_search_depth": str(row["default_search_depth"]),
            "default_topic": str(row["default_topic"]),
            "default_max_results": int(row["default_max_results"]),
            "cache_ttl_seconds": int(row["cache_ttl_seconds"]),
            "updated_at": row["updated_at"],
        }
    return {
        "api_key": settings.tavily_api_key,
        "default_search_depth": settings.tavily_default_search_depth,
        "default_topic": settings.tavily_default_topic,
        "default_max_results": settings.tavily_default_max_results,
        "cache_ttl_seconds": settings.tavily_cache_ttl_seconds,
        "updated_at": None,
    }
