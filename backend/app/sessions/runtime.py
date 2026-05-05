from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, replace
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
PROMPT_REF_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RenderedPrompts:
    system_content: str | None
    user_content: str | None


@dataclass
class ActiveRun:
    run_id: str
    cancel_event: asyncio.Event


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
        self._active_runs: dict[str, ActiveRun] = {}

    def cancel_run(self, session_id: str) -> dict[str, Any]:
        active = self._active_runs.get(session_id)
        if active is None:
            return {"status": "not_running"}
        active.cancel_event.set()
        return {"status": "cancelled", "run_id": active.run_id}

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
            active_run: ActiveRun | None = None
            session = self._get_session(session_id)
            rendered_prompts = self._render_prompts(
                role_id=str(session.get("prompt_role_id") or "default"),
                user_input=message,
            )
            if rendered_prompts.system_content:
                self._create_system_prompt_if_changed(session_id, rendered_prompts.system_content)
            if message:
                user_content = rendered_prompts.user_content
                if user_content is None:
                    user_content = message
                if user_content.strip():
                    self._create_message(session_id=session_id, role="user", content=user_content)

            simulator_account_id = (
                str(session["simulator_account_id"])
                if session.get("simulator_account_id")
                else None
            )
            provider_id = session.get("provider_id")
            if not provider_id:
                raise ValueError("会话未选择 Provider／模型，请在会话设置中选择后再运行。")
            provider_row = self._get_provider(str(provider_id))
            model = session.get("model") or provider_row["model"]
            config = self._provider_config(provider_row)
            provider = self.provider_factory(config)

            run_id = uuid4().hex
            cancel_event = asyncio.Event()
            active_run = ActiveRun(run_id=run_id, cancel_event=cancel_event)
            self._active_runs[session_id] = active_run
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
                    simulator_account_id=simulator_account_id,
                    provider=provider,
                    config=config,
                    max_tool_rounds=max_tool_rounds,
                    system_prompt=rendered_prompts.system_content,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._finish_run(run_id, status="error", error=error)
                await self._send(session_id, "error", {"run_id": run_id, "error": error})
                raise
            finally:
                current = self._active_runs.get(session_id)
                if current is not None and active_run is not None and current.run_id == active_run.run_id:
                    self._active_runs.pop(session_id, None)

            return result

    async def _run_loop(
        self,
        run_id: str,
        session_id: str,
        simulator_account_id: str | None,
        provider: ChatProvider,
        config: LLMProviderConfig,
        max_tool_rounds: int,
        system_prompt: str | None,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        messages = self._load_context(session_id, system_prompt=system_prompt)
        tools = self._tool_definitions(config)
        executor = ToolExecutor(self.tool_registry)

        usage: dict[str, Any] | None = None

        for _round in range(max_tool_rounds):
            if cancel_event.is_set():
                self._finish_run(run_id, status="cancelled", error="Cancelled by user", token_usage=usage)
                await self._send(
                    session_id,
                    "run_finished",
                    {"run_id": run_id, "status": "cancelled", "usage": usage},
                )
                return {"run_id": run_id, "status": "cancelled"}
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls_by_index: dict[int, dict[str, str]] = {}

            async for chunk in provider.chat_stream(config, messages, tools):  # type: ignore[attr-defined]
                if cancel_event.is_set():
                    self._finish_run(run_id, status="cancelled", error="Cancelled by user", token_usage=usage)
                    await self._send(
                        session_id,
                        "run_finished",
                        {"run_id": run_id, "status": "cancelled", "usage": usage},
                    )
                    return {"run_id": run_id, "status": "cancelled"}
                chunk_usage = chunk.get("usage")
                if chunk_usage:
                    usage = chunk_usage

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
                    await self._send(
                        session_id,
                        "assistant_reasoning",
                        {"run_id": run_id, "token": delta["reasoning_content"]},
                    )

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
                self._finish_run(run_id, status="finished", final_message_id=str(final_message["id"]), token_usage=usage)
                await self._send(
                    session_id,
                    "assistant_message",
                    {"run_id": run_id, "message": final_message},
                )
                await self._send(session_id, "run_finished", {"run_id": run_id, "status": "finished", "usage": usage})
                return {"run_id": run_id, "status": "finished", "final_message": final_message, "usage": usage}

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
                if cancel_event.is_set():
                    self._finish_run(run_id, status="cancelled", error="Cancelled by user", token_usage=usage)
                    await self._send(
                        session_id,
                        "run_finished",
                        {"run_id": run_id, "status": "cancelled", "usage": usage},
                    )
                    return {"run_id": run_id, "status": "cancelled"}
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

                tool_result = await executor.execute(
                    call.name,
                    call.arguments,
                    runtime_context={
                        "session_id": session_id,
                        "simulator_account_id": simulator_account_id,
                    },
                )
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

        self._finish_run(run_id, status="max_tool_rounds_reached", token_usage=usage)
        await self._send(
            session_id,
            "run_finished",
            {"run_id": run_id, "status": "max_tool_rounds_reached", "usage": usage},
        )
        return {"run_id": run_id, "status": "max_tool_rounds_reached"}

    def _tool_definitions(self, config: LLMProviderConfig) -> list[ToolDefinition]:
        strict_allowed = config.supports_strict_schema and config.strict_tool_schema
        return [
            replace(definition, strict=definition.strict and strict_allowed)
            for definition in self.tool_registry.definitions()
        ]

    def _load_context(self, session_id: str, system_prompt: str | None = None) -> list[ChatMessage]:
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

    def _render_prompts(self, role_id: str, user_input: str | None) -> RenderedPrompts:
        entries = self.store.fetch_all(
            """
            SELECT ref_name, content, enabled
            FROM prompt_entries
            WHERE role_id = ?
            ORDER BY sort_order ASC
            """,
            (role_id,),
        )
        if not entries and role_id != "default":
            entries = self.store.fetch_all(
                """
                SELECT ref_name, content, enabled
                FROM prompt_entries
                WHERE role_id = 'default'
                ORDER BY sort_order ASC
                """
            )
        by_ref = {str(row["ref_name"]): row for row in entries}
        render_time = datetime.now().astimezone().isoformat(timespec="seconds")

        def render_ref(ref_name: str, stack: set[str]) -> str:
            if ref_name == "UserInput":
                return user_input or ""
            if ref_name == "time":
                return render_time
            entry = by_ref.get(ref_name)
            if entry is None:
                return "{" + ref_name + "}"
            if not entry["enabled"]:
                return ""
            if ref_name in stack:
                return ""
            return PROMPT_REF_RE.sub(
                lambda match: render_ref(match.group(1), {*stack, ref_name}),
                str(entry["content"]),
            )

        def render_entry(ref_name: str) -> str | None:
            entry = by_ref.get(ref_name)
            if entry is None or not entry["enabled"]:
                return None
            return PROMPT_REF_RE.sub(
                lambda match: render_ref(match.group(1), {ref_name}),
                str(entry["content"]),
            )

        system_content = render_entry("system")
        user_content = render_entry("UserInput") if user_input is not None else None
        return RenderedPrompts(
            system_content=system_content if system_content and system_content.strip() else None,
            user_content=user_content,
        )

    def _create_system_prompt_if_changed(self, session_id: str, content: str) -> None:
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
        self._create_message(
            session_id=session_id,
            role="system",
            content=content,
            message_type="system_prompt",
        )

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
        return session

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
