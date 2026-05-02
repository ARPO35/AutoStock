from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.llm.base import ChatMessage, ChatResponse, LLMProviderConfig, ToolDefinition
from app.llm.openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    async def chat(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> ChatResponse:
        effective = config
        if config.strict_tool_schema and config.base_url.rstrip("/") == "https://api.deepseek.com":
            effective = replace(config, base_url="https://api.deepseek.com/beta")
        response = await super().chat(effective, messages, tools)

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
