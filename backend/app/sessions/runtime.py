from __future__ import annotations

import asyncio
import inspect
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
from app.tools.registry import ToolRegistry
from app.usage import record_llm_usage

from .ledger import RunLedger
from .prompt_rendering import PromptRenderer
from .provider_turn import ProviderTurnAssembler, ProviderTurnCancelled
from .tool_turn import ToolTurnExecutor

ProviderFactory = Callable[[LLMProviderConfig], ChatProvider]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        self.prompt_renderer = PromptRenderer(store)
        self.ledger = RunLedger(store)
        self.tool_turn_executor = ToolTurnExecutor(tool_registry)
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
            rendered_prompts = self.prompt_renderer.render(
                role_id=str(session.get("prompt_role_id") or "default"),
                user_input=message,
                render_time=replay_clock.effective_time if replay_clock else None,
            )
            if rendered_prompts.system_content:
                self.ledger.create_system_prompt_if_changed(session_id, rendered_prompts.system_content)

            provider_id = session.get("provider_id")
            model = session.get("model")
            if not provider_id:
                if not model:
                    raise ValueError("会话未选择模型，请在会话设置中选择后再运行。")
                resolved = self._resolve_provider_from_model(str(model))
                if resolved is None:
                    raise ValueError("未找到可用 Provider，请检查模型配置是否有效。")
                provider_row, model = resolved
                provider_id = str(provider_row["id"])
                self.store.execute(
                    "UPDATE chat_sessions SET provider_id = ?, updated_at = ? WHERE id = ?",
                    (provider_id, utc_now(), session_id),
                )
            else:
                provider_row = self._get_provider(str(provider_id))
            model = model or provider_row["model"]
            config = replace(
                self._provider_config(provider_row),
                model=self._provider_api_model(provider_row, str(model)),
            )
            provider = self.provider_factory(config)

            if message:
                user_content = rendered_prompts.user_content
                if user_content is None:
                    user_content = message
                if user_content.strip():
                    should_auto_title = self._should_auto_title(session_id, session)
                    self.ledger.create_message(session_id=session_id, role="user", content=user_content)
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
            self.ledger.create_run(
                run_id=run_id,
                session_id=session_id,
                provider_id=str(provider_id) if provider_id else None,
                model=str(model) if model else None,
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
                    system_prompt=rendered_prompts.system_content,
                    cancel_event=cancel_event,
                )
            except SessionRunError:
                raise
            except Exception as exc:
                error = self._format_run_error(exc)
                self.ledger.finish_run(run_id, status="error", error=error)
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
        system_prompt: str | None,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        messages = self.ledger.load_context(session_id, system_prompt=system_prompt)
        tools = self._tool_definitions(config, replay_clock=replay_clock)
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
        round_index = 0

        while True:
            round_index += 1
            if cancel_event.is_set():
                self.ledger.finish_run(run_id, status="cancelled", error="Cancelled by user", token_usage=usage)
                await self._send(
                    session_id,
                    "run_finished",
                    {"run_id": run_id, "status": "cancelled", "usage": usage},
                )
                return {"run_id": run_id, "status": "cancelled"}
            call_index += 1
            call_started = time.perf_counter()
            log_context = self._raw_log_context(
                session_id=session_id,
                session_created_at=session_created_at,
                run_id=run_id,
                call_index=call_index,
                round_index=round_index,
                provider_id=provider_id,
                config=config,
            )
            assembler = ProviderTurnAssembler()

            async def on_provider_delta(kind: str, token: str) -> None:
                if kind == "content":
                    await self._send(
                        session_id,
                        "assistant_token",
                        {"run_id": run_id, "token": token},
                    )
                    return
                await self._send(
                    session_id,
                    "assistant_reasoning",
                    {"run_id": run_id, "token": token},
                )

            try:
                turn = await assembler.assemble(
                    self._provider_chat_stream(
                        provider=provider,
                        config=config,
                        messages=messages,
                        tools=tools,
                        log_context=log_context,
                    ),
                    on_delta=on_provider_delta,
                    should_cancel=cancel_event.is_set,
                )
            except ProviderTurnCancelled as exc:
                final_message = self.ledger.create_interrupted_message(
                    session_id=session_id,
                    content_parts=exc.partial.content_parts,
                    reasoning_parts=exc.partial.reasoning_parts,
                    cause="User interrupt",
                )
                self.ledger.finish_run(
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
            except Exception as exc:
                error = self._format_run_error(exc)
                partial = assembler.snapshot()
                final_message = self.ledger.create_interrupted_message(
                    session_id=session_id,
                    content_parts=partial.content_parts,
                    reasoning_parts=partial.reasoning_parts,
                    cause=error,
                )
                self.ledger.finish_run(
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

            usage = self.ledger.record_provider_usage(
                usage_records=usage_records,
                session_id=session_id,
                run_id=run_id,
                provider_id=provider_id,
                provider_type=config.provider_type,
                provider_name=config.name,
                model=config.model,
                usage=turn.usage,
                latency_ms=(time.perf_counter() - call_started) * 1000,
                call_index=call_index,
                token_cap=config.run_token_limit,
            )

            if not turn.tool_calls:
                final_message = self.ledger.create_message(
                    session_id=session_id,
                    role="assistant",
                    content=turn.content,
                    message_type="assistant",
                    reasoning_content=turn.reasoning_content,
                )
                self.ledger.finish_run(
                    run_id,
                    status="finished",
                    final_message_id=str(final_message["id"]),
                    token_usage=usage,
                )
                await self._send(
                    session_id,
                    "assistant_message",
                    {"run_id": run_id, "message": final_message},
                )
                await self._send(session_id, "run_finished", {"run_id": run_id, "status": "finished", "usage": usage})
                return {"run_id": run_id, "status": "finished", "final_message": final_message, "usage": usage}

            assistant_message = self.ledger.create_message(
                session_id=session_id,
                role="assistant",
                content=turn.content,
                message_type="tool_call_request",
                reasoning_content=turn.reasoning_content,
            )
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=turn.content,
                    reasoning_content=turn.reasoning_content,
                    tool_calls=[self._tool_call_payload(call) for call in turn.tool_calls],
                )
            )

            for call in turn.tool_calls:
                if cancel_event.is_set():
                    self.ledger.finish_run(run_id, status="cancelled", error="Cancelled by user", token_usage=usage)
                    await self._send(
                        session_id,
                        "run_finished",
                        {"run_id": run_id, "status": "cancelled", "usage": usage},
                    )
                    return {"run_id": run_id, "status": "cancelled"}
                tool_call_id = self.ledger.create_tool_call(
                    run_id=run_id,
                    session_id=session_id,
                    message_id=str(assistant_message["id"]),
                    provider_call=call,
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

                tool_turn = await self.tool_turn_executor.execute(
                    call=call,
                    runtime_context=base_runtime_context,
                    tool_call_id=tool_call_id,
                    run_id=run_id,
                    simulator_account_id=simulator_account_id,
                )
                write_raw_llm_log(
                    context=log_context,
                    direction="internal",
                    event="tool_result",
                    payload={
                        "tool_name": call.name,
                        "arguments_json": call.arguments,
                        "ok": tool_turn.execution.ok,
                        "result": tool_turn.execution.result,
                        "error": tool_turn.execution.error,
                    },
                )
                self.ledger.save_tool_result(
                    run_id=run_id,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    result=tool_turn.execution,
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=tool_turn.execution.content(),
                    )
                )
                await self._send(
                    session_id,
                    "tool_call_finished",
                    {
                        "run_id": run_id,
                        "tool_call_id": tool_call_id,
                        "ok": tool_turn.execution.ok,
                        "result": tool_turn.execution.result,
                        "error": tool_turn.execution.error,
                    },
                )
                for intent in tool_turn.event_intents:
                    await self._send(
                        session_id,
                        intent.event_type,
                        intent.payload,
                    )
                    if intent.send_account_event and simulator_account_id:
                        await self.websocket_manager.send_account_event(
                            simulator_account_id,
                            {"type": intent.event_type, "session_id": session_id, **intent.payload},
                        )

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

    def _provider_api_model(self, provider_row: dict[str, Any], model: str) -> str:
        provider_prefix = f"{provider_row['name']}/"
        if model.startswith(provider_prefix):
            return model.removeprefix(provider_prefix)
        return model

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

    def _resolve_provider_from_model(self, model_value: str) -> tuple[dict[str, Any], str] | None:
        providers = self.store.fetch_all("SELECT * FROM llm_providers")
        exact_matches: list[tuple[dict[str, Any], str]] = []
        plain_matches: list[tuple[dict[str, Any], str]] = []
        for row in providers:
            name = str(row.get("name") or "")
            scoped_prefix = f"{name}/"
            available_models = self._parse_provider_models(row.get("available_models"))
            provider_default_model = str(row.get("model") or "").strip()
            if model_value.startswith(scoped_prefix):
                scoped_model = model_value.removeprefix(scoped_prefix)
                if scoped_model in available_models or scoped_model == provider_default_model:
                    exact_matches.append((row, model_value))
                continue
            if model_value in available_models or model_value == provider_default_model:
                plain_matches.append((row, model_value))
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(plain_matches) == 1:
            return plain_matches[0]
        return None

    def _parse_provider_models(self, value: Any) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(parsed, list):
            return []
        models: list[str] = []
        for item in parsed:
            model = str(item).strip()
            if model:
                models.append(model)
        return models

    def _replay_clock_for_account(self, account_id: str | None) -> ReplayClockSnapshot | None:
        if not account_id:
            return None
        return ReplayClockService(self.store).get_clock(account_id)

    async def _send(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.websocket_manager.send_session_event(
            session_id,
            {"type": event_type, "session_id": session_id, **payload},
        )
