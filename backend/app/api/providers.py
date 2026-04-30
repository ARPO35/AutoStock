from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.storage.sqlite import SQLiteStore

router = APIRouter(tags=["providers"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


class ProviderCreate(BaseModel):
    provider_type: Literal["openai_compatible", "deepseek"]
    name: str = Field(min_length=1, max_length=120)
    base_url: str | None = None
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
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
    provider_id: str = Field(min_length=1)
    initial_cash: float = Field(default=1_000_000, ge=0)


class AccountRead(BaseModel):
    id: str
    name: str
    provider_id: str
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
    _get_provider_or_404(store, payload.provider_id)
    account_id = uuid4().hex
    now = utc_now()
    try:
        store.execute(
            """
            INSERT INTO llm_accounts (id, name, provider_id, initial_cash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account_id, payload.name, payload.provider_id, payload.initial_cash, now, now),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _get_account_or_404(store, account_id)


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
