from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.llm.base import ChatMessage, LLMProviderConfig
from app.llm.registry import provider_from_config
from app.storage.sqlite import SQLiteStore

router = APIRouter(tags=["providers"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(value: str) -> str | None:
    """返回格式：前 6 位 + **** + 后 6 位（不足 12 位则全掩码）"""
    if not value:
        return None
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:6]}{'*' * max(4, len(value) - 12)}{value[-6:]}"


class ProviderCreate(BaseModel):
    provider_type: Literal["openai_compatible", "deepseek"]
    name: str = Field(min_length=1, max_length=120)
    base_url: str | None = None
    api_key: str = Field(min_length=12)
    model: str = ""
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: float = 60
    supports_tools: bool = True
    supports_parallel_tool_calls: bool = False
    supports_strict_schema: bool = False
    thinking_mode: Literal["thinking", "non_thinking"] | None = None
    strict_tool_schema: bool = False


class ProviderRead(BaseModel):
    id: str
    provider_type: str
    name: str
    base_url: str
    api_key_masked: str | None
    has_api_key: bool
    model: str
    temperature: float
    max_tokens: int | None
    timeout_seconds: float
    supports_tools: bool
    supports_parallel_tool_calls: bool
    supports_strict_schema: bool
    thinking_mode: str | None
    strict_tool_schema: bool
    created_at: str
    updated_at: str


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    initial_cash: float = Field(default=1_000_000, ge=0)


class AccountRead(BaseModel):
    id: str
    name: str
    initial_cash: float
    created_at: str
    updated_at: str


@router.get("/api/providers", response_model=list[ProviderRead])
async def list_providers(store: SQLiteStore = Depends(get_store)) -> list[dict[str, object]]:
    rows = store.fetch_all(
        """
        SELECT *
        FROM llm_providers
        ORDER BY created_at DESC
        """
    )
    return [_provider_public(row) for row in rows]


@router.post("/api/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    provider_id = uuid4().hex
    now = utc_now()
    base_url = payload.base_url or _default_base_url(payload.provider_type, payload.strict_tool_schema)
    try:
        store.execute(
            """
            INSERT INTO llm_providers (
                id, provider_type, name, base_url, api_key, model, temperature,
                max_tokens, timeout_seconds, supports_tools, supports_parallel_tool_calls,
                supports_strict_schema, thinking_mode, strict_tool_schema, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                payload.provider_type,
                payload.name,
                base_url,
                payload.api_key,
                payload.model,
                payload.temperature,
                payload.max_tokens,
                payload.timeout_seconds,
                int(payload.supports_tools),
                int(payload.supports_parallel_tool_calls),
                int(payload.supports_strict_schema),
                payload.thinking_mode,
                int(payload.strict_tool_schema),
                now,
                now,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _provider_public(_get_provider_or_404(store, provider_id))


@router.get("/api/providers/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    return _provider_public(_get_provider_or_404(store, provider_id))


@router.get("/api/accounts", response_model=list[AccountRead])
async def list_accounts(store: SQLiteStore = Depends(get_store)) -> list[dict[str, object]]:
    return store.fetch_all(
        """
        SELECT *
        FROM llm_accounts
        ORDER BY created_at DESC
        """
    )


@router.post("/api/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    account_id = uuid4().hex
    now = utc_now()
    try:
        store.execute(
            """
            INSERT INTO llm_accounts (id, name, initial_cash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, payload.name, payload.initial_cash, now, now),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _get_account_or_404(store, account_id)


class ProviderUpdate(BaseModel):
    """可更新字段均为可选，留空表示不修改。"""
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    supports_tools: bool | None = None
    supports_strict_schema: bool | None = None
    strict_tool_schema: bool | None = None
    thinking_mode: str | None = None


class ProviderModelsResponse(BaseModel):
    provider_id: str
    models: list[str]


class ProviderChatTestPayload(BaseModel):
    message: str = "这是一个连接测试，你只需要回答\"1\"即可"


class ProviderChatTestResponse(BaseModel):
    ok: bool
    content: str | None = None
    model: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class ProviderUsageResponse(BaseModel):
    provider_id: str
    total_runs: int
    active_sessions: int
    model: str


@router.put("/api/providers/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: str,
    payload: ProviderUpdate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    """更新 Provider 配置字段，仅修改传入的非空字段。"""
    provider = _get_provider_or_404(store, provider_id)
    now = utc_now()

    # 构建动态 SET 子句
    setters: list[str] = []
    params: list[object] = []

    if payload.base_url is not None:
        setters.append("base_url = ?")
        params.append(payload.base_url)
    if payload.model is not None:
        setters.append("model = ?")
        params.append(payload.model)
    if payload.api_key is not None and payload.api_key.strip():
        setters.append("api_key = ?")
        params.append(payload.api_key)
    if payload.temperature is not None:
        setters.append("temperature = ?")
        params.append(payload.temperature)
    if payload.max_tokens is not None:
        setters.append("max_tokens = ?")
        params.append(payload.max_tokens)
    if payload.timeout_seconds is not None:
        setters.append("timeout_seconds = ?")
        params.append(payload.timeout_seconds)
    if payload.supports_tools is not None:
        setters.append("supports_tools = ?")
        params.append(int(payload.supports_tools))
    if payload.supports_strict_schema is not None:
        setters.append("supports_strict_schema = ?")
        params.append(int(payload.supports_strict_schema))
    if payload.strict_tool_schema is not None:
        setters.append("strict_tool_schema = ?")
        params.append(int(payload.strict_tool_schema))
    if payload.thinking_mode is not None:
        setters.append("thinking_mode = ?")
        params.append(payload.thinking_mode)

    if setters:
        setters.append("updated_at = ?")
        params.append(now)
        params.append(provider_id)
        store.execute(
            f"UPDATE llm_providers SET {', '.join(setters)} WHERE id = ?",
            params,
        )

    return _provider_public(_get_provider_or_404(store, provider_id))


@router.delete("/api/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    store: SQLiteStore = Depends(get_store),
) -> None:
    """删除 Provider 及其在数据库中的所有关联数据。"""
    _get_provider_or_404(store, provider_id)
    store.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
    return None


@router.post("/api/providers/{provider_id}/models", response_model=ProviderModelsResponse)
async def provider_models(
    provider_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    """用 Provider 凭据请求 /v1/models 获取可用模型列表。"""
    provider = _get_provider_or_404(store, provider_id)
    base_url = str(provider["base_url"]).rstrip("/")
    api_key = str(provider["api_key"])
    models_url = f"{base_url}/models"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            model_ids = sorted(
                {m["id"] for m in data.get("data", []) if "id" in m}
            )
            return {"provider_id": provider_id, "models": model_ids}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider 返回错误 {exc.response.status_code}: {exc.response.text[:200]}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"连接失败: {exc}",
        ) from exc


@router.post("/api/providers/{provider_id}/chat-test", response_model=ProviderChatTestResponse)
async def provider_chat_test(
    provider_id: str,
    payload: ProviderChatTestPayload,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    """发送测试消息给 Provider，20s 超时，返回是否成功及响应内容。"""
    provider = _get_provider_or_404(store, provider_id)
    config = _build_config(provider)

    chat_provider = provider_from_config(config)
    messages = [
        ChatMessage(role="user", content=payload.message),
    ]

    t0 = datetime.now(timezone.utc)
    try:
        response = await asyncio.wait_for(
            chat_provider.chat(config=config, messages=messages, tools=[]),
            timeout=20.0,
        )
        latency = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        return {
            "ok": True,
            "content": response.content,
            "model": config.model,
            "latency_ms": round(latency, 1),
            "error": None,
        }
    except asyncio.TimeoutError:
        latency = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        return {
            "ok": False,
            "content": None,
            "model": config.model,
            "latency_ms": round(latency, 1),
            "error": "请求超时（20s）",
        }
    except Exception as exc:
        latency = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        return {
            "ok": False,
            "content": None,
            "model": config.model,
            "latency_ms": round(latency, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.get("/api/providers/{provider_id}/usage", response_model=ProviderUsageResponse)
async def provider_usage(
    provider_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    """返回该 Provider 的使用统计。"""
    _get_provider_or_404(store, provider_id)

    total_runs = store.fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM chat_runs
        WHERE provider_id = ?
        """,
        (provider_id,),
    )

    active_sessions = store.fetch_one(
        """
        SELECT COUNT(DISTINCT id) AS cnt
        FROM chat_sessions
        WHERE provider_id = ? AND archived_at IS NULL
        """,
        (provider_id,),
    )

    provider = _get_provider_or_404(store, provider_id)

    return {
        "provider_id": provider_id,
        "total_runs": int(total_runs["cnt"]) if total_runs else 0,
        "active_sessions": int(active_sessions["cnt"]) if active_sessions else 0,
        "model": str(provider["model"]),
    }


def _build_config(row: dict[str, object]) -> LLMProviderConfig:
    """从数据库行构建 LLMProviderConfig。"""
    return LLMProviderConfig(
        provider_type=str(row["provider_type"]),
        name=str(row["name"]),
        base_url=str(row["base_url"]),
        api_key=str(row["api_key"]),
        model=str(row["model"]),
        temperature=float(row["temperature"]),
        max_tokens=int(row["max_tokens"]) if row["max_tokens"] is not None else None,
        timeout_seconds=float(row["timeout_seconds"]),
        supports_tools=bool(row["supports_tools"]),
        supports_parallel_tool_calls=bool(row["supports_parallel_tool_calls"]),
        supports_strict_schema=bool(row["supports_strict_schema"]),
        thinking_mode=str(row["thinking_mode"]) if row["thinking_mode"] is not None else None,
        strict_tool_schema=bool(row["strict_tool_schema"]),
    )


def _default_base_url(provider_type: str, strict_tool_schema: bool) -> str:
    if provider_type == "deepseek":
        return "https://api.deepseek.com/beta" if strict_tool_schema else "https://api.deepseek.com"
    return "https://api.openai.com/v1"


def _provider_public(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "api_key_masked": mask_api_key(str(row.get("api_key") or "")),
        "has_api_key": bool(row.get("api_key")),
        "supports_tools": bool(row["supports_tools"]),
        "supports_parallel_tool_calls": bool(row["supports_parallel_tool_calls"]),
        "supports_strict_schema": bool(row["supports_strict_schema"]),
        "strict_tool_schema": bool(row["strict_tool_schema"]),
    }


def _get_provider_or_404(store: SQLiteStore, provider_id: str) -> dict[str, object]:
    provider = store.fetch_one("SELECT * FROM llm_providers WHERE id = ?", (provider_id,))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


def _get_account_or_404(store: SQLiteStore, account_id: str) -> dict[str, object]:
    account = store.fetch_one("SELECT * FROM llm_accounts WHERE id = ?", (account_id,))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account
