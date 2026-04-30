from __future__ import annotations

from dataclasses import replace

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
        return await super().chat(effective, messages, tools)
