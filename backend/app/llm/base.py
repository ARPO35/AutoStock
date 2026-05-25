from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMProviderConfig:
    provider_type: str
    name: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: float = 60
    supports_tools: bool = True
    supports_parallel_tool_calls: bool = False
    supports_strict_schema: bool = False
    thinking_mode: str | None = None
    strict_tool_schema: bool = False
    run_token_limit: int | None = None


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str | None = None
    reasoning_content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = False


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatResponse:
    content: str | None
    reasoning_content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)


class ChatProvider(Protocol):
    async def chat(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: dict[str, Any] | None = None,
    ) -> ChatResponse:
        ...

    async def chat_stream(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        log_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        ...
