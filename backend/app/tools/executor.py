from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def content(self) -> str:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.result is not None:
            payload["result"] = self.result
        if self.error:
            payload["error"] = self.error
        return json.dumps(payload, ensure_ascii=False)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, tool_name: str, arguments_json: str) -> ToolExecutionResult:
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments={},
                result=None,
                error=f"Invalid JSON arguments: {exc.msg}",
            )

        if not isinstance(arguments, dict):
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments={},
                result=None,
                error="Tool arguments must decode to an object.",
            )

        try:
            tool = self.registry.get(tool_name)
            result = await tool.handler(arguments)
        except KeyError as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        return ToolExecutionResult(tool_name=tool_name, arguments=arguments, result=result)
