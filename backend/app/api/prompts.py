from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/prompt-roles", tags=["prompt-roles"])

BUILTIN_REFS = ("system", "UserInput")
RESERVED_REFS = {*BUILTIN_REFS, "time"}
REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptEntryRead(BaseModel):
    id: str
    role_id: str
    name: str
    ref_name: str
    content: str
    enabled: bool
    builtin: bool
    sort_order: int
    created_at: str
    updated_at: str


class PromptRoleRead(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    entries: list[PromptEntryRead]


class PromptRoleCreate(BaseModel):
    name: str = Field(default="新角色", min_length=1, max_length=120)


class PromptEntryWrite(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    ref_name: str = Field(min_length=1, max_length=64)
    content: str = ""
    enabled: bool = True
    builtin: bool = False


class PromptRoleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entries: list[PromptEntryWrite] = Field(min_length=2)


class PromptRoleImport(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entries: list[PromptEntryWrite] = Field(min_length=2)


@router.get("", response_model=list[PromptRoleRead])
async def list_prompt_roles(store: SQLiteStore = Depends(get_store)) -> list[dict[str, object]]:
    roles = store.fetch_all(
        """
        SELECT *
        FROM prompt_roles
        ORDER BY CASE WHEN id = 'default' THEN 0 ELSE 1 END, created_at ASC
        """
    )
    return [_role_with_entries(store, str(role["id"])) for role in roles]


@router.post("", response_model=PromptRoleRead, status_code=status.HTTP_201_CREATED)
async def create_prompt_role(
    payload: PromptRoleCreate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    role_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO prompt_roles (id, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (role_id, payload.name, now, now),
    )
    _insert_default_entries(store, role_id, now)
    return _role_with_entries(store, role_id)


@router.get("/{role_id}", response_model=PromptRoleRead)
async def get_prompt_role(
    role_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    return _role_with_entries(store, role_id)


@router.put("/{role_id}", response_model=PromptRoleRead)
async def update_prompt_role(
    role_id: str,
    payload: PromptRoleUpdate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    existing = _get_role_or_404(store, role_id)
    entries = _validated_entries(payload.entries)
    now = utc_now()

    store.execute(
        """
        UPDATE prompt_roles
        SET name = ?, updated_at = ?
        WHERE id = ?
        """,
        (payload.name, now, existing["id"]),
    )
    store.execute("DELETE FROM prompt_entries WHERE role_id = ?", (role_id,))
    _insert_entries(store, role_id, entries, now)
    return _role_with_entries(store, role_id)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_role(
    role_id: str,
    store: SQLiteStore = Depends(get_store),
) -> None:
    _get_role_or_404(store, role_id)
    if role_id == "default":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default role cannot be deleted")
    now = utc_now()
    store.execute(
        """
        UPDATE chat_sessions
        SET prompt_role_id = ?, updated_at = ?
        WHERE prompt_role_id = ?
        """,
        ("default", now, role_id),
    )
    store.execute("DELETE FROM prompt_roles WHERE id = ?", (role_id,))


@router.get("/{role_id}/export", response_model=PromptRoleRead)
async def export_prompt_role(
    role_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    return _role_with_entries(store, role_id)


@router.post("/import", response_model=PromptRoleRead, status_code=status.HTTP_201_CREATED)
async def import_prompt_role(
    payload: PromptRoleImport,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    entries = _validated_entries(payload.entries)
    role_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO prompt_roles (id, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (role_id, payload.name, now, now),
    )
    _insert_entries(store, role_id, entries, now)
    return _role_with_entries(store, role_id)


def _get_role_or_404(store: SQLiteStore, role_id: str) -> dict[str, object]:
    role = store.fetch_one("SELECT * FROM prompt_roles WHERE id = ?", (role_id,))
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt role not found")
    return role


def _role_with_entries(store: SQLiteStore, role_id: str) -> dict[str, object]:
    role = _get_role_or_404(store, role_id)
    entries = store.fetch_all(
        """
        SELECT *
        FROM prompt_entries
        WHERE role_id = ?
        ORDER BY builtin DESC, sort_order ASC, created_at ASC
        """,
        (role_id,),
    )
    return {**role, "entries": entries}


def _insert_default_entries(store: SQLiteStore, role_id: str, now: str) -> None:
    _insert_entries(
        store,
        role_id,
        [
            PromptEntryWrite(
                name="系统提示词",
                ref_name="system",
                content="",
                enabled=True,
                builtin=True,
            ),
            PromptEntryWrite(
                name="用户输入",
                ref_name="UserInput",
                content="{UserInput}{time}",
                enabled=True,
                builtin=True,
            ),
        ],
        now,
    )


def _insert_entries(store: SQLiteStore, role_id: str, entries: list[PromptEntryWrite], now: str) -> None:
    store.connection.executemany(
        """
        INSERT INTO prompt_entries (
            id, role_id, name, ref_name, content, enabled, builtin,
            sort_order, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                entry.id or uuid4().hex,
                role_id,
                entry.name,
                entry.ref_name,
                entry.content,
                1 if entry.enabled else 0,
                1 if entry.builtin else 0,
                index,
                now,
                now,
            )
            for index, entry in enumerate(entries)
        ],
    )
    store.connection.commit()


def _validated_entries(entries: list[PromptEntryWrite]) -> list[PromptEntryWrite]:
    by_ref = {entry.ref_name: entry for entry in entries}
    for ref in BUILTIN_REFS:
        if ref not in by_ref:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing builtin prompt: {ref}")

    normalized: list[PromptEntryWrite] = []
    seen_refs: set[str] = set()
    for entry in entries:
        if not REF_PATTERN.fullmatch(entry.ref_name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid ref_name: {entry.ref_name}")
        if entry.ref_name in seen_refs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Duplicate ref_name: {entry.ref_name}")
        seen_refs.add(entry.ref_name)

        if entry.ref_name in BUILTIN_REFS:
            builtin_name = "系统提示词" if entry.ref_name == "system" else "用户输入"
            normalized.append(
                entry.model_copy(
                    update={
                        "id": entry.id,
                        "name": builtin_name,
                        "builtin": True,
                    }
                )
            )
            continue

        if entry.ref_name in RESERVED_REFS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Reserved ref_name: {entry.ref_name}")
        if entry.builtin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom prompts cannot be builtin")
        normalized.append(entry.model_copy(update={"builtin": False}))

    normalized.sort(key=lambda item: (0 if item.ref_name == "system" else 1 if item.ref_name == "UserInput" else 2))
    return normalized
