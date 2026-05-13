from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import asdict
from typing import Any

from app.llm.base import ChatMessage, ChatResponse, LLMProviderConfig, ToolCall, ToolDefinition
from app.llm.raw_logger import RawLogContext, write_raw_llm_log


class OpenAICompatibleProvider:
    def _build_chat_request(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": config.model,
            "messages": [self._message_to_payload(message) for message in messages],
            "temperature": config.temperature,
        }
        if config.max_tokens is not None:
            request["max_tokens"] = config.max_tokens
        if tools and config.supports_tools:
            request["tools"] = [self._tool_to_payload(tool) for tool in tools]
            request["parallel_tool_calls"] = config.supports_parallel_tool_calls
        return request

    async def chat(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: RawLogContext | None = None,
    ) -> ChatResponse:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError("The openai package is required for LLM provider calls.") from exc

        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

        request = self._build_chat_request(config, messages, tools)
        self._log_request(context=log_context, config=config, request=request)
        try:
            response = await client.chat.completions.create(**request)
        except Exception as exc:
            self._log_exception(
                context=log_context,
                event="error",
                config=config,
                request=request,
                exc=exc,
            )
            raise
        raw = self._dump_model(response)
        write_raw_llm_log(
            context=log_context,
            direction="inbound",
            event="response",
            payload=raw,
        )
        choice = response.choices[0]
        message = choice.message
        calls = []
        for call in message.tool_calls or []:
            calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=call.function.arguments,
                )
            )

        usage = raw.get("usage") or {}
        return ChatResponse(content=message.content, tool_calls=calls, raw=raw, usage=usage)

    async def chat_stream(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: RawLogContext | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError("The openai package is required for LLM provider calls.") from exc

        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

        request = self._build_chat_request(config, messages, tools)
        request["stream"] = True
        request["stream_options"] = {"include_usage": True}

        self._log_request(context=log_context, config=config, request=request)
        try:
            stream = await client.chat.completions.create(**request)
            async for chunk in stream:
                raw_chunk = self._dump_model(chunk)
                write_raw_llm_log(
                    context=log_context,
                    direction="inbound",
                    event="chunk",
                    payload=raw_chunk,
                )
                yield raw_chunk
        except Exception as exc:
            self._log_exception(
                context=log_context,
                event="stream_error",
                config=config,
                request=request,
                exc=exc,
            )
            raise
        write_raw_llm_log(
            context=log_context,
            direction="inbound",
            event="stream_end",
            payload={},
        )

    def _message_to_payload(self, message: ChatMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role}
        if message.content is not None:
            payload["content"] = message.content
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls is not None:
            payload["tool_calls"] = message.tool_calls
        return payload

    def _tool_to_payload(self, tool: ToolDefinition) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        if tool.strict:
            payload["function"]["strict"] = True
        return payload

    def _log_request(
        self,
        *,
        context: RawLogContext | None,
        config: LLMProviderConfig,
        request: dict[str, Any],
    ) -> None:
        write_raw_llm_log(
            context=context,
            direction="outbound",
            event="request",
            payload={"provider_config": asdict(config), "request": request},
        )

    def _log_exception(
        self,
        *,
        context: RawLogContext | None,
        event: str,
        config: LLMProviderConfig,
        request: dict[str, Any],
        exc: Exception,
    ) -> None:
        write_raw_llm_log(
            context=context,
            direction="inbound",
            event=event,
            payload={
                "provider_config": asdict(config),
                "request": request,
                "exception": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "repr": repr(exc),
                },
            },
        )

    def _dump_model(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        raw = getattr(value, "__dict__", {})
        return raw if isinstance(raw, dict) else {}
