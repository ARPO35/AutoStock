from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.llm.base import ChatMessage, ChatResponse, LLMProviderConfig, ToolDefinition
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.raw_logger import RawLogContext


class DeepSeekProvider(OpenAICompatibleProvider):
    def _build_chat_request(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> dict[str, Any]:
        request = super()._build_chat_request(config, messages, tools)
        request.pop("temperature", None)  # thinking mode 不支持 temperature
        request["reasoning_effort"] = "high"
        request["extra_body"] = {"thinking": {"type": "enabled"}}
        return request

    async def chat(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: RawLogContext | None = None,
    ) -> ChatResponse:
        effective = config
        if config.strict_tool_schema and config.base_url.rstrip("/") == "https://api.deepseek.com":
            effective = replace(config, base_url="https://api.deepseek.com/beta")
        response = await super().chat(effective, messages, tools, log_context=log_context)

        reasoning: str | None = None
        raw = response.raw
        choices = raw.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            reasoning = msg.get("reasoning_content")

        return ChatResponse(
            content=response.content,
            reasoning_content=reasoning,
            tool_calls=response.tool_calls,
            raw=raw,
            usage=response.usage,
        )

    def _message_to_payload(self, message: ChatMessage) -> dict[str, Any]:
        payload = super()._message_to_payload(message)
        if message.reasoning_content is not None:
            payload["reasoning_content"] = message.reasoning_content
        return payload
