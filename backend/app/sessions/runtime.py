from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.core.websocket_manager import WebSocketManager
from app.llm.base import ChatMessage, ChatProvider, LLMProviderConfig, ToolCall, ToolDefinition
from app.llm.raw_logger import RawLogContext, write_raw_llm_log
from app.llm.registry import provider_from_config
from app.simulator.replay_clock import ReplayClockService, ReplayClockSnapshot
from app.storage.sqlite import SQLiteStore
from app.tools.executor import ToolExecutor, ToolExecutionResult
from app.tools.registry import ToolRegistry
from app.usage import aggregate_usage, record_llm_usage

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


class SessionRunError(Exception):
    def __init__(self, run_id: str, error: str) -> None:
        super().__init__(error)
        self.run_id = run_id
        self.error = error


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
            simulator_account_id = (
                str(session["simulator_account_id"])
                if session.get("simulator_account_id")
                else None
            )
            replay_clock = self._replay_clock_for_account(simulator_account_id)
            rendered_prompts = self._render_prompts(
                role_id=str(session.get("prompt_role_id") or "default"),
                user_input=message,
                render_time=replay_clock.effective_time if replay_clock else None,
            )
            if rendered_prompts.system_content:
                self._create_system_prompt_if_changed(session_id, rendered_prompts.system_content)

            provider_id = session.get("provider_id")
            if not provider_id:
                raise ValueError("会话未选择 Provider／模型，请在会话设置中选择后再运行。")
            provider_row = self._get_provider(str(provider_id))
            model = session.get("model") or provider_row["model"]
            config = replace(self._provider_config(provider_row), model=str(model))
            provider = self.provider_factory(config)

            if message:
                user_content = rendered_prompts.user_content
                if user_content is None:
                    user_content = message
                if user_content.strip():
                    should_auto_title = self._should_auto_title(session_id, session)
                    self._create_message(session_id=session_id, role="user", content=user_content)
                    if should_auto_title:
                        await self._auto_title_from_first_message(
                            session_id=session_id,
                            session_created_at=str(session["created_at"]),
                            placeholder_name=str(session.get("name") or ""),
                            provider=provider,
                            provider_id=str(provider_id),
                            config=config,
                            user_message=user_content,
                        )

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
            await self._send(
                session_id,
                "run_started",
                {"run_id": run_id, "clock": replay_clock.as_dict() if replay_clock else None},
            )

            try:
                result = await self._run_loop(
                    run_id=run_id,
                    session_id=session_id,
                    session_created_at=str(session["created_at"]),
                    simulator_account_id=simulator_account_id,
                    replay_clock=replay_clock,
                    provider=provider,
                    provider_id=str(provider_id),
                    config=config,
                    max_tool_rounds=max_tool_rounds,
                    system_prompt=rendered_prompts.system_content,
                    cancel_event=cancel_event,
                )
            except SessionRunError:
                raise
            except Exception as exc:
                error = self._format_run_error(exc)
                self._finish_run(run_id, status="error", error=error)
                await self._send(session_id, "error", {"run_id": run_id, "error": error})
                raise SessionRunError(run_id=run_id, error=error) from exc
            finally:
                current = self._active_runs.get(session_id)
                if current is not None and active_run is not None and current.run_id == active_run.run_id:
                    self._active_runs.pop(session_id, None)

            return result

    async def _run_loop(
        self,
        run_id: str,
        session_id: str,
        session_created_at: str,
        simulator_account_id: str | None,
        replay_clock: ReplayClockSnapshot | None,
        provider: ChatProvider,
        provider_id: str | None,
        config: LLMProviderConfig,
        max_tool_rounds: int,
        system_prompt: str | None,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        messages = self._load_context(session_id, system_prompt=system_prompt)
        tools = self._tool_definitions(config, replay_clock=replay_clock)
        executor = ToolExecutor(self.tool_registry)
        base_runtime_context = {
            "session_id": session_id,
            "run_id": run_id,
            "simulator_account_id": simulator_account_id,
        }
        if replay_clock is not None:
            base_runtime_context.update(replay_clock.runtime_context())

        usage: dict[str, Any] | None = None
        usage_records: list[dict[str, Any]] = []
        call_index = 0

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
            call_index += 1
            call_usage: dict[str, Any] | None = None
            call_started = time.perf_counter()
            log_context = self._raw_log_context(
                session_id=session_id,
                session_created_at=session_created_at,
                run_id=run_id,
                call_index=call_index,
                round_index=_round + 1,
                provider_id=provider_id,
                config=config,
            )

            try:
                async for chunk in self._provider_chat_stream(
                    provider=provider,
                    config=config,
                    messages=messages,
                    tools=tools,
                    log_context=log_context,
                ):
                    if cancel_event.is_set():
                        final_message = self._create_interrupted_message(
                            session_id=session_id,
                            content_parts=content_parts,
                            reasoning_parts=reasoning_parts,
                            cause="User interrupt",
                        )
                        self._finish_run(
                            run_id,
                            status="cancelled",
                            final_message_id=str(final_message["id"]) if final_message else None,
                            error="Cancelled by user",
                            token_usage=usage,
                        )
                        if final_message:
                            await self._send(
                                session_id,
                                "assistant_message",
                                {"run_id": run_id, "message": final_message},
                            )
                        await self._send(
                            session_id,
                            "run_finished",
                            {"run_id": run_id, "status": "cancelled", "usage": usage},
                        )
                        result: dict[str, Any] = {"run_id": run_id, "status": "cancelled"}
                        if final_message:
                            result["final_message"] = final_message
                        return result
                    chunk_usage = chunk.get("usage")
                    if chunk_usage:
                        call_usage = chunk_usage

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
            except Exception as exc:
                error = self._format_run_error(exc)
                final_message = self._create_interrupted_message(
                    session_id=session_id,
                    content_parts=content_parts,
                    reasoning_parts=reasoning_parts,
                    cause=error,
                )
                self._finish_run(
                    run_id,
                    status="error",
                    final_message_id=str(final_message["id"]) if final_message else None,
                    error=error,
                    token_usage=usage,
                )
                if final_message:
                    await self._send(
                        session_id,
                        "assistant_message",
                        {"run_id": run_id, "message": final_message},
                    )
                await self._send(session_id, "error", {"run_id": run_id, "error": error})
                raise SessionRunError(run_id=run_id, error=error) from exc

            usage_records.append(
                record_llm_usage(
                    self.store,
                    session_id=session_id,
                    run_id=run_id,
                    provider_id=provider_id,
                    provider_type=config.provider_type,
                    provider_name=config.name,
                    model=config.model,
                    usage=call_usage,
                    latency_ms=(time.perf_counter() - call_started) * 1000,
                    call_index=call_index,
                    purpose="session_run",
                    token_cap=config.run_token_limit,
                )
            )
            usage = aggregate_usage(usage_records)

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
                    runtime_context={**base_runtime_context, "tool_call_id": tool_call_id},
                )
                write_raw_llm_log(
                    context=log_context,
                    direction="internal",
                    event="tool_result",
                    payload={
                        "tool_name": call.name,
                        "arguments_json": call.arguments,
                        "ok": tool_result.ok,
                        "result": tool_result.result,
                        "error": tool_result.error,
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
                if call.name.startswith("order_") and tool_result.ok and tool_result.result:
                    if tool_result.result.get("order_id"):
                        await self._send(
                            session_id,
                            "order_created",
                            {
                                "run_id": run_id,
                                "account_id": simulator_account_id,
                                "tool_call_id": tool_call_id,
                                "tool_name": call.name,
                                "order_id": tool_result.result.get("order_id"),
                                "symbol": tool_result.result.get("symbol"),
                                "side": tool_result.result.get("side"),
                            },
                        )
                    if tool_result.result.get("trade_id"):
                        await self._send(
                            session_id,
                            "trade_created",
                            {
                                "run_id": run_id,
                                "account_id": simulator_account_id,
                                "tool_call_id": tool_call_id,
                                "tool_name": call.name,
                                "trade_id": tool_result.result.get("trade_id"),
                                "symbol": tool_result.result.get("symbol"),
                                "side": tool_result.result.get("side"),
                            },
                        )
                if call.name.startswith(("order_", "portfolio_")) and simulator_account_id:
                    await self._send(
                        session_id,
                        "portfolio_updated",
                        {
                            "run_id": run_id,
                            "account_id": simulator_account_id,
                            "tool_call_id": tool_call_id,
                            "tool_name": call.name,
                        },
                    )

        self._finish_run(run_id, status="max_tool_rounds_reached", token_usage=usage)
        await self._send(
            session_id,
            "run_finished",
            {"run_id": run_id, "status": "max_tool_rounds_reached", "usage": usage},
        )
        return {"run_id": run_id, "status": "max_tool_rounds_reached"}

    async def _provider_chat(
        self,
        *,
        provider: ChatProvider,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: RawLogContext,
    ) -> Any:
        if self._accepts_log_context(provider.chat):
            return await provider.chat(config, messages, tools, log_context=log_context)
        return await provider.chat(config, messages, tools)

    async def _provider_chat_stream(
        self,
        *,
        provider: ChatProvider,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: RawLogContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self._accepts_log_context(provider.chat_stream):
            stream = provider.chat_stream(config, messages, tools, log_context=log_context)
        else:
            stream = provider.chat_stream(config, messages, tools)
        async for chunk in stream:
            yield chunk

    def _raw_log_context(
        self,
        *,
        session_id: str,
        session_created_at: str | None,
        run_id: str | None,
        call_index: int,
        round_index: int,
        provider_id: str | None,
        config: LLMProviderConfig,
    ) -> RawLogContext:
        return {
            "session_id": session_id,
            "run_id": run_id,
            "call_index": call_index,
            "round_index": round_index,
            "provider_type": config.provider_type,
            "provider_name": config.name,
            "provider_id": provider_id,
            "model": config.model,
            "session_created_at": session_created_at,
        }

    def _accepts_log_context(self, method: Callable[..., Any]) -> bool:
        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            return False
        return "log_context" in signature.parameters

    def _tool_definitions(
        self,
        config: LLMProviderConfig,
        replay_clock: ReplayClockSnapshot | None = None,
    ) -> list[ToolDefinition]:
        strict_allowed = config.supports_strict_schema and config.strict_tool_schema
        definitions = [
            definition for definition in self.tool_registry.definitions()
            if definition.name != "data_fetch_history"
        ]
        return [
            replace(definition, strict=definition.strict and strict_allowed)
            for definition in definitions
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

    def _render_prompts(
        self,
        role_id: str,
        user_input: str | None,
        render_time: str | None = None,
    ) -> RenderedPrompts:
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
        resolved_render_time = render_time or datetime.now().astimezone().isoformat(timespec="seconds")

        def render_ref(ref_name: str, stack: set[str]) -> str:
            if ref_name == "UserInput":
                return user_input or ""
            if ref_name == "time":
                return resolved_render_time
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

    def _create_interrupted_message(
        self,
        session_id: str,
        content_parts: list[str],
        reasoning_parts: list[str],
        cause: str,
    ) -> dict[str, Any] | None:
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts) or None
        if not content and not reasoning:
            return None
        return self._create_message(
            session_id=session_id,
            role="assistant",
            content=self._append_interrupt_marker(content, cause),
            message_type="assistant",
            reasoning_content=reasoning,
        )

    def _append_interrupt_marker(self, content: str, cause: str) -> str:
        marker = f"[Interrupted: {self._single_line(cause)}]"
        if not content.strip():
            return marker
        return f"{content.rstrip()}\n\n{marker}"

    def _single_line(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

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

    def _should_auto_title(self, session_id: str, session: dict[str, Any]) -> bool:
        name = str(session.get("name") or "").strip()
        if name != "新会话":
            return False
        existing_user = self.store.fetch_one(
            """
            SELECT id
            FROM chat_messages
            WHERE session_id = ?
              AND role = 'user'
            LIMIT 1
            """,
            (session_id,),
        )
        return existing_user is None

    async def _auto_title_from_first_message(
        self,
        session_id: str,
        session_created_at: str,
        placeholder_name: str,
        provider: ChatProvider,
        provider_id: str | None,
        config: LLMProviderConfig,
        user_message: str,
    ) -> None:
        title = self._fallback_title()
        prompt = (
            "请根据用户的第一条消息生成一个简洁会话标题。"
            "只输出标题本身，不加引号，不加句号，不加前缀。"
            "长度控制在8到20个中文字符，尽量准确概括主题。"
        )
        try:
            call_started = time.perf_counter()
            response = await self._provider_chat(
                provider=provider,
                config=config,
                messages=[
                    ChatMessage(role="system", content=prompt),
                    ChatMessage(role="user", content=user_message),
                ],
                tools=[],
                log_context=self._raw_log_context(
                    session_id=session_id,
                    session_created_at=session_created_at,
                    run_id=None,
                    call_index=1,
                    round_index=0,
                    provider_id=provider_id,
                    config=config,
                ),
            )
            record_llm_usage(
                self.store,
                session_id=session_id,
                run_id=None,
                provider_id=provider_id,
                provider_type=config.provider_type,
                provider_name=config.name,
                model=config.model,
                usage=response.usage,
                latency_ms=(time.perf_counter() - call_started) * 1000,
                call_index=1,
                purpose="session_title",
                token_cap=config.run_token_limit,
            )
            candidate = self._normalize_title(response.content)
            if candidate:
                title = candidate
        except Exception:
            title = self._fallback_title()

        now = utc_now()
        self.store.execute(
            """
            UPDATE chat_sessions
            SET name = ?, updated_at = ?
            WHERE id = ?
              AND name = ?
            """,
            (title, now, session_id, placeholder_name),
        )

    def _normalize_title(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        title = raw.strip()
        if not title:
            return None
        title = title.replace("\n", " ").replace("\r", " ").strip()
        title = re.sub(r"^标题[:：]\s*", "", title)
        title = title.strip("\"'“”‘’。.!！?？ ")
        title = re.sub(r"\s+", " ", title)
        if not title:
            return None
        return title[:32]

    def _fallback_title(self) -> str:
        return f"新会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

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
            run_token_limit=int(row["run_token_limit"]) if row.get("run_token_limit") is not None else None,
        )

    def _format_run_error(self, exc: Exception) -> str:
        detail = f"{type(exc).__name__}: {exc}"
        if self._is_connection_error(exc):
            return (
                "LLM Provider 连接失败：请检查 Provider Base URL、代理/网络和服务可用性。"
                f"（{detail}）"
            )
        return detail

    def _is_connection_error(self, exc: BaseException) -> bool:
        current: BaseException | None = exc
        while current is not None:
            name = type(current).__name__.lower()
            if "connection" in name or "connecterror" in name:
                return True
            current = current.__cause__ or current.__context__
        return False

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

    def _replay_clock_for_account(self, account_id: str | None) -> ReplayClockSnapshot | None:
        if not account_id:
            return None
        return ReplayClockService(self.store).get_clock(account_id)

    async def _send(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.websocket_manager.send_session_event(
            session_id,
            {"type": event_type, "session_id": session_id, **payload},
        )
