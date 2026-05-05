from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.storage.sqlite import SQLiteStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TavilyRuntimeConfig:
    api_key: str
    default_search_depth: str
    default_topic: str
    default_max_results: int
    cache_ttl_seconds: int


class TavilyService:
    def __init__(self, store: SQLiteStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    async def search(
        self,
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        config = self.config()
        request = self._search_request(arguments, config)
        return await self._run_operation(
            operation="search",
            request=request,
            runtime_context=runtime_context,
            use_cache=use_cache,
            credits_estimator=lambda response: self._search_credits(request, response),
            result_counter=lambda response: len(response.get("results") or []),
            invoke=lambda: self._client_call("search", config.api_key, request),
        )

    async def extract(
        self,
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        config = self.config()
        request = self._extract_request(arguments)
        return await self._run_operation(
            operation="extract",
            request=request,
            runtime_context=runtime_context,
            use_cache=use_cache,
            credits_estimator=lambda response: self._extract_credits(request, response),
            result_counter=lambda response: len(response.get("results") or []),
            invoke=lambda: self._client_call("extract", config.api_key, request),
        )

    def config(self) -> TavilyRuntimeConfig:
        row = self.store.fetch_one("SELECT * FROM tavily_config WHERE id = 'default'")
        if row:
            api_key = str(row["api_key"] or self.settings.tavily_api_key)
            return TavilyRuntimeConfig(
                api_key=api_key,
                default_search_depth=str(row["default_search_depth"]),
                default_topic=str(row["default_topic"]),
                default_max_results=int(row["default_max_results"]),
                cache_ttl_seconds=int(row["cache_ttl_seconds"]),
            )
        return TavilyRuntimeConfig(
            api_key=self.settings.tavily_api_key,
            default_search_depth=self.settings.tavily_default_search_depth,
            default_topic=self.settings.tavily_default_topic,
            default_max_results=self.settings.tavily_default_max_results,
            cache_ttl_seconds=self.settings.tavily_cache_ttl_seconds,
        )

    async def _run_operation(
        self,
        operation: str,
        request: dict[str, Any],
        runtime_context: dict[str, Any] | None,
        use_cache: bool,
        credits_estimator,
        result_counter,
        invoke,
    ) -> dict[str, Any]:
        config = self.config()
        cache_key = self._cache_key(operation, request)
        cached = self._read_cache(cache_key) if use_cache and config.cache_ttl_seconds > 0 else None
        if cached is not None:
            result_count = result_counter(cached)
            payload = self._tool_payload(
                operation=operation,
                request=request,
                response=cached,
                cache_hit=True,
                credits_estimated=0.0,
                result_count=result_count,
                latency_ms=None,
            )
            self._record_usage(
                operation=operation,
                request=request,
                response=payload,
                runtime_context=runtime_context,
                status="finished",
                cache_hit=True,
                result_count=result_count,
                credits_estimated=0.0,
                latency_ms=None,
                error=None,
            )
            return payload

        if not config.api_key:
            raise ValueError("Tavily API key is not configured.")

        started = perf_counter()
        try:
            response = self._normalize_response(await invoke())
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 1)
            self._record_usage(
                operation=operation,
                request=request,
                response=None,
                runtime_context=runtime_context,
                status="error",
                cache_hit=False,
                result_count=0,
                credits_estimated=0.0,
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        latency_ms = round((perf_counter() - started) * 1000, 1)
        result_count = result_counter(response)
        credits_estimated = credits_estimator(response)
        if config.cache_ttl_seconds > 0:
            self._write_cache(cache_key, operation, request, response, config.cache_ttl_seconds)
        payload = self._tool_payload(
            operation=operation,
            request=request,
            response=response,
            cache_hit=False,
            credits_estimated=credits_estimated,
            result_count=result_count,
            latency_ms=latency_ms,
        )
        self._record_usage(
            operation=operation,
            request=request,
            response=payload,
            runtime_context=runtime_context,
            status="finished",
            cache_hit=False,
            result_count=result_count,
            credits_estimated=credits_estimated,
            latency_ms=latency_ms,
            error=None,
        )
        return payload

    async def _client_call(self, method: str, api_key: str, request: dict[str, Any]) -> Any:
        try:
            from tavily import AsyncTavilyClient
        except ModuleNotFoundError as exc:
            raise RuntimeError("The tavily-python package is required for Tavily tools.") from exc

        client = AsyncTavilyClient(api_key=api_key)
        if method == "search":
            return await client.search(**request)
        if method == "extract":
            return await client.extract(**request)
        raise ValueError(f"Unsupported Tavily operation: {method}")

    def _search_request(self, arguments: dict[str, Any], config: TavilyRuntimeConfig) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required.")
        search_depth = str(arguments.get("search_depth") or config.default_search_depth)
        if search_depth not in {"basic", "advanced"}:
            raise ValueError("search_depth must be basic or advanced.")
        topic = str(arguments.get("topic") or config.default_topic)
        if topic not in {"general", "news", "finance"}:
            raise ValueError("topic must be general, news, or finance.")
        max_results = int(arguments.get("max_results") or config.default_max_results)
        if max_results < 1 or max_results > 20:
            raise ValueError("max_results must be between 1 and 20.")
        request: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "topic": topic,
            "max_results": max_results,
            "include_usage": True,
        }
        for key in ("time_range", "start_date", "end_date"):
            value = arguments.get(key)
            if value:
                request[key] = str(value)
        return request

    def _extract_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_urls = arguments.get("urls")
        if not isinstance(raw_urls, list):
            raise ValueError("urls must be an array.")
        urls = [str(url).strip() for url in raw_urls if str(url).strip()]
        if not urls:
            raise ValueError("urls is required.")
        if len(urls) > 20:
            raise ValueError("urls cannot contain more than 20 entries.")
        extract_depth = str(arguments.get("extract_depth") or "basic")
        if extract_depth not in {"basic", "advanced"}:
            raise ValueError("extract_depth must be basic or advanced.")
        content_format = str(arguments.get("format") or "markdown")
        if content_format not in {"markdown", "text"}:
            raise ValueError("format must be markdown or text.")
        request: dict[str, Any] = {
            "urls": urls,
            "extract_depth": extract_depth,
            "format": content_format,
            "include_usage": True,
        }
        query = arguments.get("query")
        if query:
            request["query"] = str(query)
        return request

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        row = self.store.fetch_one(
            """
            SELECT response_json, expires_at
            FROM tavily_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        )
        if row is None:
            return None
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at <= datetime.now(timezone.utc):
            return None
        return json.loads(str(row["response_json"]))

    def _write_cache(
        self,
        cache_key: str,
        operation: str,
        request: dict[str, Any],
        response: dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.store.execute(
            """
            INSERT INTO tavily_cache (
                cache_key, operation, arguments_json, response_json, created_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                cache_key,
                operation,
                self._json(request),
                self._json(response),
                now.isoformat(),
                (now + timedelta(seconds=ttl_seconds)).isoformat(),
            ),
        )

    def _record_usage(
        self,
        operation: str,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        runtime_context: dict[str, Any] | None,
        status: str,
        cache_hit: bool,
        result_count: int,
        credits_estimated: float,
        latency_ms: float | None,
        error: str | None,
    ) -> None:
        context = runtime_context or {}
        self.store.execute(
            """
            INSERT INTO tavily_usage_records (
                id, session_id, run_id, tool_call_id, operation, cache_hit,
                request_json, response_json, status, error, latency_ms,
                result_count, credits_estimated, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                context.get("session_id"),
                context.get("run_id"),
                context.get("tool_call_id"),
                operation,
                int(cache_hit),
                self._json(request),
                self._json(response) if response is not None else None,
                status,
                error,
                latency_ms,
                result_count,
                credits_estimated,
                utc_now(),
            ),
        )

    def _tool_payload(
        self,
        operation: str,
        request: dict[str, Any],
        response: dict[str, Any],
        cache_hit: bool,
        credits_estimated: float,
        result_count: int,
        latency_ms: float | None,
    ) -> dict[str, Any]:
        payload = {
            "kind": f"tavily_{operation}",
            "operation": operation,
            "cache_hit": cache_hit,
            "credits_estimated": credits_estimated,
            "result_count": result_count,
            "latency_ms": latency_ms,
            **response,
        }
        if operation == "search":
            payload["query"] = request["query"]
        if operation == "extract":
            payload["urls"] = request["urls"]
        return payload

    def _search_credits(self, request: dict[str, Any], response: dict[str, Any]) -> float:
        usage = self._usage_credits(response)
        if usage is not None:
            return usage
        return 2.0 if request.get("search_depth") == "advanced" else 1.0

    def _extract_credits(self, request: dict[str, Any], response: dict[str, Any]) -> float:
        usage = self._usage_credits(response)
        if usage is not None:
            return usage
        result_count = len(response.get("results") or [])
        if result_count == 0:
            return 0.0
        unit = 2.0 if request.get("extract_depth") == "advanced" else 1.0
        return float(math.ceil(result_count / 5) * unit)

    def _usage_credits(self, response: dict[str, Any]) -> float | None:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return None
        for key in ("credits", "credits_used", "total_credits"):
            value = usage.get(key)
            if isinstance(value, int | float):
                return float(value)
        return None

    def _cache_key(self, operation: str, request: dict[str, Any]) -> str:
        digest = hashlib.sha256(f"{operation}:{self._json(request)}".encode("utf-8")).hexdigest()
        return digest

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return response
        if hasattr(response, "model_dump"):
            return response.model_dump(mode="json")
        return json.loads(json.dumps(response, default=str))

    def _json(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
