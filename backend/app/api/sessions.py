from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    llm_account_id: str | None = None
    skill_id: str | None = None
    simulator_account_id: str | None = None


class SessionRead(BaseModel):
    id: str
    name: str
    llm_account_id: str | None
    skill_id: str | None
    simulator_account_id: str | None
    status: str
    created_at: str
    updated_at: str
    archived_at: str | None


class MessageCreate(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str = Field(min_length=1)
    message_type: str = "user"
    trigger_id: str | None = None
    parent_message_id: str | None = None


class MessageRead(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    message_type: str
    trigger_id: str | None
    parent_message_id: str | None
    created_at: str


class RunCreate(BaseModel):
    message: str | None = Field(default=None, min_length=1)
    max_tool_rounds: int = Field(default=5, ge=1, le=20)


class RunRead(BaseModel):
    id: str
    session_id: str
    provider_id: str | None
    model: str | None
    status: str
    event_message_id: str | None
    max_tool_rounds: int
    started_at: str
    finished_at: str | None
    final_message_id: str | None
    error: str | None


class TimelineItemRead(BaseModel):
    type: Literal["message", "tool_call", "tool_result"]
    id: str
    session_id: str | None = None
    role: str | None = None
    message_type: str | None = None
    content: str | None = None
    created_at: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_json: str | None = None
    result_json: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


@router.get("", response_model=list[SessionRead])
async def list_sessions(store: SQLiteStore = Depends(get_store)) -> list[dict[str, object]]:
    return store.fetch_all(
        """
        SELECT *
        FROM chat_sessions
        ORDER BY created_at DESC
        """
    )


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    session_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO chat_sessions (
            id, name, llm_account_id, skill_id, simulator_account_id,
            status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            session_id,
            payload.name,
            payload.llm_account_id,
            payload.skill_id,
            payload.simulator_account_id,
            now,
            now,
        ),
    )
    return _get_session_or_404(store, session_id)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    return _get_session_or_404(store, session_id)


@router.get("/{session_id}/messages", response_model=list[MessageRead])
async def list_messages(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> list[dict[str, object]]:
    _get_session_or_404(store, session_id)
    return store.fetch_all(
        """
        SELECT *
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        """,
        (session_id,),
    )


@router.get("/{session_id}/timeline", response_model=list[TimelineItemRead])
async def session_timeline(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> list[dict[str, object]]:
    _get_session_or_404(store, session_id)
    items: list[dict[str, object]] = []

    for row in store.fetch_all(
        """
        SELECT *
        FROM chat_messages
        WHERE session_id = ?
        """,
        (session_id,),
    ):
        items.append(
            {
                "type": "message",
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "message_type": row["message_type"],
                "trigger_id": row.get("trigger_id"),
                "parent_message_id": row.get("parent_message_id"),
                "created_at": row["created_at"],
                "_sort_time": row["created_at"],
            }
        )

    for row in store.fetch_all(
        """
        SELECT *
        FROM chat_tool_calls
        WHERE session_id = ?
        """,
        (session_id,),
    ):
        items.append(
            {
                "type": "tool_call",
                "id": row["id"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "tool_call_id": row["id"],
                "tool_name": row["tool_name"],
                "arguments_json": row["arguments_json"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "error": row["error"],
                "_sort_time": row["started_at"],
            }
        )

    for row in store.fetch_all(
        """
        SELECT *
        FROM chat_tool_results
        WHERE session_id = ?
        """,
        (session_id,),
    ):
        items.append(
            {
                "type": "tool_result",
                "id": row["id"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "tool_call_id": row["tool_call_id"],
                "result_json": row["result_json"],
                "created_at": row["created_at"],
                "_sort_time": row["created_at"],
            }
        )

    items.sort(key=lambda item: str(item["_sort_time"]))
    for item in items:
        item.pop("_sort_time", None)
    return items


@router.post(
    "/{session_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    session_id: str,
    payload: MessageCreate,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, object]:
    _get_session_or_404(store, session_id)
    message_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO chat_messages (
            id, session_id, role, content, message_type,
            trigger_id, parent_message_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            session_id,
            payload.role,
            payload.content,
            payload.message_type,
            payload.trigger_id,
            payload.parent_message_id,
            now,
        ),
    )
    store.execute(
        """
        UPDATE chat_sessions
        SET updated_at = ?
        WHERE id = ?
        """,
        (now, session_id),
    )
    return _get_message_or_404(store, message_id)


@router.get("/{session_id}/runs", response_model=list[RunRead])
async def list_runs(
    session_id: str,
    store: SQLiteStore = Depends(get_store),
) -> list[dict[str, object]]:
    _get_session_or_404(store, session_id)
    return store.fetch_all(
        """
        SELECT *
        FROM chat_runs
        WHERE session_id = ?
        ORDER BY started_at DESC
        """,
        (session_id,),
    )


@router.post("/{session_id}/run")
async def run_session(
    session_id: str,
    payload: RunCreate,
    request: Request,
) -> dict[str, object]:
    try:
        return await request.app.state.run_manager.run_once(
            session_id=session_id,
            message=payload.message,
            max_tool_rounds=payload.max_tool_rounds,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _get_session_or_404(store: SQLiteStore, session_id: str) -> dict[str, object]:
    session = store.fetch_one(
        """
        SELECT *
        FROM chat_sessions
        WHERE id = ?
        """,
        (session_id,),
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _get_message_or_404(store: SQLiteStore, message_id: str) -> dict[str, object]:
    message = store.fetch_one(
        """
        SELECT *
        FROM chat_messages
        WHERE id = ?
        """,
        (message_id,),
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message
