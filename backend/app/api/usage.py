from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_store
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/summary")
async def usage_summary(
    account_id: str | None = None,
    session_id: str | None = None,
    provider_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    clauses, params = _usage_clauses(account_id, session_id, provider_id, start, end)
    totals = _usage_totals(store, clauses, params)
    return {
        "filters": _filters(account_id, session_id, provider_id, start, end),
        "summary": totals,
        "by_provider": _usage_grouped(store, clauses, params, "u.provider_id, u.provider_name"),
        "by_model": _usage_grouped(store, clauses, params, "u.model"),
        "by_session": _usage_grouped(store, clauses, params, "u.session_id, s.name"),
        "recent_runs": _usage_runs(store, clauses, params, 20),
    }


@router.get("/runs")
async def usage_runs(
    account_id: str | None = None,
    session_id: str | None = None,
    provider_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    clauses, params = _usage_clauses(account_id, session_id, provider_id, start, end)
    return {
        "filters": _filters(account_id, session_id, provider_id, start, end),
        "summary": _usage_totals(store, clauses, params),
        "runs": _usage_runs(store, clauses, params, limit),
    }


@router.get("/sessions/{session_id}")
async def session_usage(
    session_id: str,
    start: str | None = None,
    end: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    clauses, params = _usage_clauses(None, session_id, None, start, end)
    return {
        "session_id": session_id,
        "summary": _usage_totals(store, clauses, params),
        "runs": _usage_runs(store, clauses, params, 100),
    }


def provider_usage_summary(store: SQLiteStore, provider_id: str) -> dict[str, Any]:
    clauses, params = _usage_clauses(None, None, provider_id, None, None)
    totals = _usage_totals(store, clauses, params)
    runs = store.fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM chat_runs
        WHERE provider_id = ?
        """,
        (provider_id,),
    )
    totals["total_runs"] = int(runs["cnt"]) if runs else 0
    return totals


def _usage_clauses(
    account_id: str | None,
    session_id: str | None,
    provider_id: str | None,
    start: str | None,
    end: str | None,
) -> tuple[list[str], list[Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    if session_id:
        clauses.append("u.session_id = ?")
        params.append(session_id)
    if provider_id:
        clauses.append("u.provider_id = ?")
        params.append(provider_id)
    start_value = _start_value(start)
    end_value = _end_value(end)
    if start_value:
        clauses.append("u.created_at >= ?")
        params.append(start_value)
    if end_value:
        clauses.append("u.created_at <= ?")
        params.append(end_value)
    return clauses, params


def _usage_totals(
    store: SQLiteStore,
    clauses: list[str],
    params: list[Any],
) -> dict[str, Any]:
    row = store.fetch_one(
        f"""
        SELECT
            COUNT(*) AS llm_calls,
            COUNT(DISTINCT u.run_id) AS run_count,
            COALESCE(SUM(u.prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(u.completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(u.thinking_tokens), 0) AS thinking_tokens,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            COALESCE(SUM(u.latency_ms), 0) AS latency_ms,
            COALESCE(AVG(u.latency_ms), 0) AS avg_latency_ms,
            COALESCE(SUM(u.cap_exceeded), 0) AS cap_exceeded_count
        FROM llm_usage_records u
        JOIN chat_sessions s ON s.id = u.session_id
        WHERE {' AND '.join(clauses)}
        """,
        params,
    )
    row = row or {}
    return {
        "llm_calls": int(row.get("llm_calls") or 0),
        "run_count": int(row.get("run_count") or 0),
        "prompt_tokens": int(row.get("prompt_tokens") or 0),
        "completion_tokens": int(row.get("completion_tokens") or 0),
        "thinking_tokens": int(row.get("thinking_tokens") or 0),
        "total_tokens": int(row.get("total_tokens") or 0),
        "latency_ms": round(float(row.get("latency_ms") or 0), 1),
        "avg_latency_ms": round(float(row.get("avg_latency_ms") or 0), 1),
        "cap_exceeded_count": int(row.get("cap_exceeded_count") or 0),
    }


def _usage_grouped(
    store: SQLiteStore,
    clauses: list[str],
    params: list[Any],
    group_by: str,
) -> list[dict[str, Any]]:
    label_expr = {
        "u.provider_id, u.provider_name": "u.provider_name",
        "u.model": "u.model",
        "u.session_id, s.name": "s.name",
    }[group_by]
    id_expr = {
        "u.provider_id, u.provider_name": "u.provider_id",
        "u.model": "u.model",
        "u.session_id, s.name": "u.session_id",
    }[group_by]
    return store.fetch_all(
        f"""
        SELECT
            {id_expr} AS id,
            {label_expr} AS name,
            COUNT(*) AS llm_calls,
            COUNT(DISTINCT u.run_id) AS run_count,
            COALESCE(SUM(u.prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(u.completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(u.thinking_tokens), 0) AS thinking_tokens,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            COALESCE(SUM(u.latency_ms), 0) AS latency_ms,
            COALESCE(AVG(u.latency_ms), 0) AS avg_latency_ms,
            COALESCE(SUM(u.cap_exceeded), 0) AS cap_exceeded_count
        FROM llm_usage_records u
        JOIN chat_sessions s ON s.id = u.session_id
        WHERE {' AND '.join(clauses)}
        GROUP BY {group_by}
        ORDER BY total_tokens DESC, llm_calls DESC
        LIMIT 50
        """,
        params,
    )


def _usage_runs(
    store: SQLiteStore,
    clauses: list[str],
    params: list[Any],
    limit: int,
) -> list[dict[str, Any]]:
    return store.fetch_all(
        f"""
        SELECT
            u.run_id,
            u.session_id,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name,
            u.provider_id,
            u.provider_name,
            u.model,
            MIN(u.created_at) AS created_at,
            COUNT(*) AS llm_calls,
            COALESCE(SUM(u.prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(u.completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(u.thinking_tokens), 0) AS thinking_tokens,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            COALESCE(SUM(u.latency_ms), 0) AS latency_ms,
            COALESCE(AVG(u.latency_ms), 0) AS avg_latency_ms,
            COALESCE(SUM(u.cap_exceeded), 0) AS cap_exceeded_count
        FROM llm_usage_records u
        JOIN chat_sessions s ON s.id = u.session_id
        LEFT JOIN simulator_accounts a ON a.id = s.simulator_account_id
        WHERE {' AND '.join(clauses)}
        GROUP BY u.run_id, u.session_id, s.name, s.simulator_account_id, a.name,
                 u.provider_id, u.provider_name, u.model
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )


def _filters(
    account_id: str | None,
    session_id: str | None,
    provider_id: str | None,
    start: str | None,
    end: str | None,
) -> dict[str, str | None]:
    return {
        "account_id": account_id or None,
        "session_id": session_id or None,
        "provider_id": provider_id or None,
        "start": start or None,
        "end": end or None,
    }


def _start_value(value: str | None) -> str | None:
    if not value:
        return None
    return value if "T" in value else f"{value}T00:00:00"


def _end_value(value: str | None) -> str | None:
    if not value:
        return None
    return value if "T" in value else f"{value}T23:59:59.999999"
