from __future__ import annotations

from app.llm.base import ChatProvider, LLMProviderConfig
from app.llm.deepseek import DeepSeekProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


def provider_from_config(config: LLMProviderConfig) -> ChatProvider:
    if config.provider_type == "deepseek":
        return DeepSeekProvider()
    if config.provider_type == "openai_compatible":
        return OpenAICompatibleProvider()
    raise ValueError(f"Unsupported provider type: {config.provider_type}")
