from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.storage.sqlite import SQLiteStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class NormalizedUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    thinking_tokens: int


def normalize_usage(raw_usage: dict[str, Any] | None) -> NormalizedUsage:
    usage = raw_usage or {}
    prompt_tokens = _int_value(
        usage,
        "prompt_tokens",
        "input_tokens",
        "input_token_count",
    )
    completion_tokens = _int_value(
        usage,
        "completion_tokens",
        "output_tokens",
        "output_token_count",
    )
    completion_details = _dict_value(usage.get("completion_tokens_details"))
    output_details = _dict_value(usage.get("output_tokens_details"))
    thinking_tokens = _first_int(
        usage.get("thinking_tokens"),
        usage.get("reasoning_tokens"),
        completion_details.get("reasoning_tokens"),
        completion_details.get("thinking_tokens"),
        output_details.get("reasoning_tokens"),
        output_details.get("thinking_tokens"),
    )

    total_tokens = _int_value(usage, "total_tokens", "total_token_count")
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return NormalizedUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        thinking_tokens=thinking_tokens,
    )


def record_llm_usage(
    store: SQLiteStore,
    *,
    session_id: str,
    run_id: str | None,
    provider_id: str | None,
    provider_type: str,
    provider_name: str,
    model: str,
    usage: dict[str, Any] | None,
    latency_ms: float,
    call_index: int,
    purpose: str,
    token_cap: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_usage(usage)
    cap_exceeded = bool(token_cap is not None and normalized.total_tokens > token_cap)
    row_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO llm_usage_records (
            id, session_id, run_id, provider_id, provider_type, provider_name, model,
            prompt_tokens, completion_tokens, total_tokens, thinking_tokens,
            latency_ms, call_index, purpose, raw_usage_json, token_cap,
            cap_exceeded, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            session_id,
            run_id,
            provider_id,
            provider_type,
            provider_name,
            model,
            normalized.prompt_tokens,
            normalized.completion_tokens,
            normalized.total_tokens,
            normalized.thinking_tokens,
            round(latency_ms, 1),
            call_index,
            purpose,
            json.dumps(usage or {}, ensure_ascii=False),
            token_cap,
            int(cap_exceeded),
            now,
        ),
    )
    return {
        "id": row_id,
        "session_id": session_id,
        "run_id": run_id,
        "provider_id": provider_id,
        "provider_type": provider_type,
        "provider_name": provider_name,
        "model": model,
        "prompt_tokens": normalized.prompt_tokens,
        "completion_tokens": normalized.completion_tokens,
        "total_tokens": normalized.total_tokens,
        "thinking_tokens": normalized.thinking_tokens,
        "latency_ms": round(latency_ms, 1),
        "call_index": call_index,
        "purpose": purpose,
        "token_cap": token_cap,
        "cap_exceeded": cap_exceeded,
        "created_at": now,
    }


def aggregate_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    llm_calls = len(records)
    latency_ms = round(sum(float(row.get("latency_ms") or 0) for row in records), 1)
    return {
        "llm_calls": llm_calls,
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in records),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in records),
        "thinking_tokens": sum(int(row.get("thinking_tokens") or 0) for row in records),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in records),
        "latency_ms": latency_ms,
        "avg_latency_ms": round(latency_ms / llm_calls, 1) if llm_calls else 0,
        "cap_exceeded": any(bool(row.get("cap_exceeded")) for row in records),
    }


def _int_value(data: dict[str, Any], *keys: str) -> int:
    return _first_int(*(data.get(key) for key in keys))


def _first_int(*values: Any) -> int:
    for value in values:
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
