from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.llm.base import ToolCall

ProviderDeltaKind = Literal["content", "reasoning"]
ProviderDeltaCallback = Callable[[ProviderDeltaKind, str], Awaitable[None]]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class ProviderTurnResult:
    content: str
    reasoning_content: str | None
    tool_calls: list[ToolCall]
    usage: dict[str, Any] | None = None
    content_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)


class ProviderTurnCancelled(Exception):
    def __init__(self, partial: ProviderTurnResult) -> None:
        super().__init__("Provider turn cancelled.")
        self.partial = partial


class ProviderTurnAssembler:
    def __init__(self) -> None:
        self._content_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_calls_by_index: dict[int, dict[str, str]] = {}
        self._usage: dict[str, Any] | None = None

    async def assemble(
        self,
        stream: AsyncIterable[dict[str, Any]],
        *,
        on_delta: ProviderDeltaCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> ProviderTurnResult:
        async for chunk in stream:
            if should_cancel and should_cancel():
                raise ProviderTurnCancelled(self.snapshot())
            chunk_usage = chunk.get("usage")
            if chunk_usage:
                self._usage = chunk_usage

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            content = delta.get("content")
            if content:
                self._content_parts.append(content)
                if on_delta:
                    await on_delta("content", content)

            reasoning = delta.get("reasoning_content")
            if reasoning:
                self._reasoning_parts.append(reasoning)
                if on_delta:
                    await on_delta("reasoning", reasoning)

            for tool_call_delta in delta.get("tool_calls") or []:
                idx = tool_call_delta.get("index", 0)
                if idx not in self._tool_calls_by_index:
                    self._tool_calls_by_index[idx] = {"id": "", "name": "", "arguments": ""}
                tool_call = self._tool_calls_by_index[idx]
                if tool_call_delta.get("id"):
                    tool_call["id"] = tool_call_delta["id"]
                function_delta = tool_call_delta.get("function") or {}
                if function_delta.get("name"):
                    tool_call["name"] = function_delta["name"]
                if function_delta.get("arguments"):
                    tool_call["arguments"] += function_delta["arguments"]

        return self.snapshot()

    def snapshot(self) -> ProviderTurnResult:
        tool_calls: list[ToolCall] = []
        for idx in sorted(self._tool_calls_by_index):
            tool_call = self._tool_calls_by_index[idx]
            if tool_call["id"] and tool_call["name"]:
                tool_calls.append(
                    ToolCall(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        arguments=tool_call["arguments"],
                    )
                )
        return ProviderTurnResult(
            content="".join(self._content_parts),
            reasoning_content="".join(self._reasoning_parts) or None,
            tool_calls=tool_calls,
            usage=self._usage,
            content_parts=list(self._content_parts),
            reasoning_parts=list(self._reasoning_parts),
        )
