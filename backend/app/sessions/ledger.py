from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from app.llm.base import ChatMessage, ToolCall
from app.storage.sqlite import SQLiteStore
from app.tools.executor import ToolExecutionResult
from app.usage import aggregate_usage, record_llm_usage

from .runtime_clock import utc_now


class RunLedger:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create_run(
        self,
        *,
        run_id: str,
        session_id: str,
        provider_id: str | None,
        model: str | None,
    ) -> None:
        self.store.execute(
            """
            INSERT INTO chat_runs (
                id, session_id, provider_id, model, status, started_at
            )
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (run_id, session_id, provider_id, model, utc_now()),
        )

    def finish_run(
        self,
        run_id: str,
        status: str,
        final_message_id: str | None = None,
        error: str | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> None:
        self.store.execute(
            """
            UPDATE chat_runs
            SET status = ?, finished_at = ?, final_message_id = ?, error = ?, token_usage = ?
            WHERE id = ?
            """,
            (status, utc_now(), final_message_id, error, json.dumps(token_usage) if token_usage else None, run_id),
        )

    def load_context(self, session_id: str, system_prompt: str | None = None) -> list[ChatMessage]:
        rows = self.store.fetch_all(
            """
            SELECT role, content, reasoning_content
            FROM chat_messages
            WHERE session_id = ?
              AND role IN ('user', 'assistant')
              AND message_type != 'tool_call_request'
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        messages = [
            ChatMessage(
                role=str(row["role"]),
                content=str(row["content"]),
                reasoning_content=str(row["reasoning_content"]) if row["reasoning_content"] else None,
            )
            for row in rows
        ]
        if system_prompt:
            messages.insert(0, ChatMessage(role="system", content=system_prompt))
        return messages

    def create_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        message_type: str = "user",
        reasoning_content: str | None = None,
    ) -> dict[str, Any]:
        self._get_session(session_id)
        message_id = uuid4().hex
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, message_type, created_at, reasoning_content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, message_type, now, reasoning_content),
        )
        self.store.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?
            WHERE id = ?
            """,
            (now, session_id),
        )
        message = self.store.fetch_one("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
        assert message is not None
        return message

    def create_system_prompt_if_changed(self, session_id: str, content: str) -> None:
        last = self.store.fetch_one(
            """
            SELECT content
            FROM chat_messages
            WHERE session_id = ?
              AND role = 'system'
              AND message_type = 'system_prompt'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        if last and last["content"] == content:
            return
        self.create_message(
            session_id=session_id,
            role="system",
            content=content,
            message_type="system_prompt",
        )

    def create_interrupted_message(
        self,
        *,
        session_id: str,
        content_parts: list[str],
        reasoning_parts: list[str],
        cause: str,
    ) -> dict[str, Any] | None:
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts) or None
        if not content and not reasoning:
            return None
        return self.create_message(
            session_id=session_id,
            role="assistant",
            content=self._append_interrupt_marker(content, cause),
            message_type="assistant",
            reasoning_content=reasoning,
        )

    def create_tool_call(
        self,
        *,
        run_id: str,
        session_id: str,
        message_id: str,
        provider_call: ToolCall,
    ) -> str:
        tool_call_id = uuid4().hex
        self.store.execute(
            """
            INSERT INTO chat_tool_calls (
                id, run_id, session_id, message_id, provider_call_id,
                tool_name, arguments_json, status, started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                tool_call_id,
                run_id,
                session_id,
                message_id,
                provider_call.id,
                provider_call.name,
                provider_call.arguments,
                utc_now(),
            ),
        )
        return tool_call_id

    def save_tool_result(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_call_id: str,
        result: ToolExecutionResult,
    ) -> None:
        now = utc_now()
        self.store.execute(
            """
            UPDATE chat_tool_calls
            SET status = ?, finished_at = ?, error = ?
            WHERE id = ?
            """,
            ("finished" if result.ok else "error", now, result.error, tool_call_id),
        )
        self.store.execute(
            """
            INSERT INTO chat_tool_results (
                id, run_id, session_id, tool_call_id, result_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uuid4().hex, run_id, session_id, tool_call_id, result.content(), now),
        )

    def record_provider_usage(
        self,
        *,
        usage_records: list[dict[str, Any]],
        session_id: str,
        run_id: str,
        provider_id: str | None,
        provider_type: str,
        provider_name: str,
        model: str,
        usage: dict[str, Any] | None,
        latency_ms: float,
        call_index: int,
        token_cap: int | None,
    ) -> dict[str, Any]:
        usage_records.append(
            record_llm_usage(
                self.store,
                session_id=session_id,
                run_id=run_id,
                provider_id=provider_id,
                provider_type=provider_type,
                provider_name=provider_name,
                model=model,
                usage=usage,
                latency_ms=latency_ms,
                call_index=call_index,
                purpose="session_run",
                token_cap=token_cap,
            )
        )
        return aggregate_usage(usage_records)

    def _append_interrupt_marker(self, content: str, cause: str) -> str:
        marker = f"[Interrupted: {self._single_line(cause)}]"
        if not content.strip():
            return marker
        return f"{content.rstrip()}\n\n{marker}"

    def _single_line(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _get_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.fetch_one("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
        if session is None:
            raise LookupError("Session not found.")
        return session
