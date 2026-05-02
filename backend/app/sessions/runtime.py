from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.core.websocket_manager import WebSocketManager
from app.llm.base import ChatMessage, ChatProvider, LLMProviderConfig, ToolCall, ToolDefinition
from app.llm.registry import provider_from_config
from app.storage.sqlite import SQLiteStore
from app.tools.executor import ToolExecutor, ToolExecutionResult
from app.tools.registry import ToolRegistry

ProviderFactory = Callable[[LLMProviderConfig], ChatProvider]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionRunManager:
    def __init__(
        self,
        store: SQLiteStore,
        tool_registry: ToolRegistry,
        websocket_manager: WebSocketManager,
        provider_factory: ProviderFactory = provider_from_config,
    ) -> None:
        self.store = store
        self.tool_registry = tool_registry
        self.websocket_manager = websocket_manager
        self.provider_factory = provider_factory
        self._locks: dict[str, asyncio.Lock] = {}

    async def run_once(
        self,
        session_id: str,
        message: str | None = None,
        max_tool_rounds: int = 5,
    ) -> dict[str, Any]:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        if lock.locked():
            raise RuntimeError("Session already has an active run.")

        async with lock:
            if message:
                self._create_message(session_id=session_id, role="user", content=message)

            session = self._get_session(session_id)
            account = self._get_account(str(session["llm_account_id"]))  # 校验账号存在
            provider_id = session.get("provider_id")
            if not provider_id:
                raise ValueError("会话未选择 Provider／模型，请在会话设置中选择后再运行。")
            provider_row = self._get_provider(str(provider_id))
            model = session.get("model") or provider_row["model"]
            config = self._provider_config(provider_row)
            provider = self.provider_factory(config)

            run_id = uuid4().hex
            started_at = utc_now()
            self.store.execute(
                """
                INSERT INTO chat_runs (
                    id, session_id, provider_id, model, status,
                    max_tool_rounds, started_at
                )
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (run_id, session_id, provider_id, model, max_tool_rounds, started_at),
            )
            await self._send(session_id, "run_started", {"run_id": run_id})

            try:
                result = await self._run_loop(
                    run_id=run_id,
                    session_id=session_id,
                    provider=provider,
                    config=config,
                    max_tool_rounds=max_tool_rounds,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._finish_run(run_id, status="error", error=error)
                await self._send(session_id, "error", {"run_id": run_id, "error": error})
                raise

            return result

    async def _run_loop(
        self,
        run_id: str,
        session_id: str,
        provider: ChatProvider,
        config: LLMProviderConfig,
        max_tool_rounds: int,
    ) -> dict[str, Any]:
        messages = self._load_context(session_id)
        tools = self._tool_definitions(config)
        executor = ToolExecutor(self.tool_registry)

        for _round in range(max_tool_rounds):
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls_by_index: dict[int, dict[str, str]] = {}

            async for chunk in provider.chat_stream(config, messages, tools):  # type: ignore[attr-defined]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                if delta.get("content"):
                    content_parts.append(delta["content"])
                    await self._send(
                        session_id,
                        "assistant_token",
                        {"run_id": run_id, "token": delta["content"]},
                    )

                if delta.get("reasoning_content"):
                    reasoning_parts.append(delta["reasoning_content"])

                for tc_delta in delta.get("tool_calls") or []:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_by_index:
                        tool_calls_by_index[idx] = {"id": "", "name": "", "arguments": ""}
                    tc = tool_calls_by_index[idx]
                    if tc_delta.get("id"):
                        tc["id"] = tc_delta["id"]
                    fn = tc_delta.get("function") or {}
                    if fn.get("name"):
                        tc["name"] = fn["name"]
                    if fn.get("arguments"):
                        tc["arguments"] += fn["arguments"]

            full_content = "".join(content_parts)
            full_reasoning = "".join(reasoning_parts) or None

            tool_calls: list[ToolCall] = []
            for idx in sorted(tool_calls_by_index):
                tc = tool_calls_by_index[idx]
                if tc["id"] and tc["name"]:
                    tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"]))

            if not tool_calls:
                final_message = self._create_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_content,
                    message_type="assistant",
                    reasoning_content=full_reasoning,
                )
                self._finish_run(run_id, status="finished", final_message_id=str(final_message["id"]))
                await self._send(
                    session_id,
                    "assistant_message",
                    {"run_id": run_id, "message": final_message},
                )
                await self._send(session_id, "run_finished", {"run_id": run_id, "status": "finished"})
                return {"run_id": run_id, "status": "finished", "final_message": final_message}

            assistant_message = self._create_message(
                session_id=session_id,
                role="assistant",
                content=full_content,
                message_type="tool_call_request",
                reasoning_content=full_reasoning,
            )
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=full_content,
                    reasoning_content=full_reasoning,
                    tool_calls=[self._tool_call_payload(call) for call in tool_calls],
                )
            )

            for call in tool_calls:
                tool_call_id = uuid4().hex
                now = utc_now()
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
                        assistant_message["id"],
                        call.id,
                        call.name,
                        call.arguments,
                        now,
                    ),
                )
                await self._send(
                    session_id,
                    "tool_call_started",
                    {
                        "run_id": run_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": call.name,
                        "arguments_json": call.arguments,
                    },
                )

                tool_result = await executor.execute(call.name, call.arguments)
                self._save_tool_result(
                    run_id=run_id,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    result=tool_result,
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=tool_result.content(),
                    )
                )
                await self._send(
                    session_id,
                    "tool_call_finished",
                    {
                        "run_id": run_id,
                        "tool_call_id": tool_call_id,
                        "ok": tool_result.ok,
                        "result": tool_result.result,
                        "error": tool_result.error,
                    },
                )

        self._finish_run(run_id, status="max_tool_rounds_reached")
        await self._send(
            session_id,
            "run_finished",
            {"run_id": run_id, "status": "max_tool_rounds_reached"},
        )
        return {"run_id": run_id, "status": "max_tool_rounds_reached"}

    def _tool_definitions(self, config: LLMProviderConfig) -> list[ToolDefinition]:
        strict_allowed = config.supports_strict_schema and config.strict_tool_schema
        return [
            replace(definition, strict=definition.strict and strict_allowed)
            for definition in self.tool_registry.definitions()
        ]

    def _load_context(self, session_id: str) -> list[ChatMessage]:
        rows = self.store.fetch_all(
            """
            SELECT role, content, reasoning_content
            FROM chat_messages
            WHERE session_id = ?
              AND role IN ('system', 'user', 'assistant')
              AND message_type != 'tool_call_request'
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return [
            ChatMessage(
                role=str(row["role"]),
                content=str(row["content"]),
                reasoning_content=str(row["reasoning_content"]) if row["reasoning_content"] else None,
            )
            for row in rows
        ]

    def _create_message(
        self,
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

    def _save_tool_result(
        self,
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

    def _finish_run(
        self,
        run_id: str,
        status: str,
        final_message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self.store.execute(
            """
            UPDATE chat_runs
            SET status = ?, finished_at = ?, final_message_id = ?, error = ?
            WHERE id = ?
            """,
            (status, utc_now(), final_message_id, error, run_id),
        )

    def _provider_config(self, row: dict[str, Any]) -> LLMProviderConfig:
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

    def _tool_call_payload(self, call: ToolCall) -> dict[str, Any]:
        return {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": call.arguments},
        }

    def _get_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.fetch_one("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
        if session is None:
            raise LookupError("Session not found.")
        if not session.get("llm_account_id"):
            raise ValueError("Session is not bound to an LLM account.")
        return session

    def _get_account(self, account_id: str) -> dict[str, Any]:
        account = self.store.fetch_one("SELECT * FROM llm_accounts WHERE id = ?", (account_id,))
        if account is None:
            raise LookupError("LLM account not found.")
        return account

    def _get_provider(self, provider_id: str) -> dict[str, Any]:
        provider = self.store.fetch_one("SELECT * FROM llm_providers WHERE id = ?", (provider_id,))
        if provider is None:
            raise LookupError("LLM provider not found.")
        return provider

    async def _send(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.websocket_manager.send_session_event(
            session_id,
            {"type": event_type, "session_id": session_id, **payload},
        )
