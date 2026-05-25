from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.llm.base import ToolDefinition

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    display_name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    strict: bool = False

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            strict=self.strict,
        )

    def public_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": self.strict,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def definitions(self) -> list[ToolDefinition]:
        return [tool.to_definition() for tool in self.list()]


async def echo_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"echo": arguments["message"]}


def create_default_registry(
    market_store: Any | None = None,
    market_provider: Any | None = None,
    simulator_engine: Any | None = None,
    tavily_service: Any | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="system_echo",
            display_name="system.echo",
            description="Echo a message back to verify tool calling and result handling.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Text to echo back.",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            handler=echo_tool,
            strict=True,
        )
    )
    if market_store is not None and market_provider is not None:
        from app.tools.market_tools import create_market_tool_specs

        for spec in create_market_tool_specs(market_store, market_provider):
            registry.register(spec)
    if simulator_engine is not None:
        from app.tools.order_tools import create_order_tool_specs
        from app.tools.portfolio_tools import create_portfolio_tool_specs

        for spec in create_order_tool_specs(
            simulator_engine,
            market_store=market_store,
            market_provider=market_provider,
        ):
            registry.register(spec)
        for spec in create_portfolio_tool_specs(simulator_engine):
            registry.register(spec)
    if tavily_service is not None:
        from app.tools.tavily_tools import create_tavily_tool_specs

        for spec in create_tavily_tool_specs(tavily_service):
            registry.register(spec)
    return registry
