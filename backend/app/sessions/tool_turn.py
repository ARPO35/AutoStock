from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.base import ToolCall
from app.tools.executor import ToolExecutor, ToolExecutionResult
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolEventIntent:
    event_type: str
    payload: dict[str, Any]
    send_account_event: bool = False


@dataclass(frozen=True)
class ToolTurnResult:
    execution: ToolExecutionResult
    event_intents: list[ToolEventIntent] = field(default_factory=list)


class ToolTurnExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.executor = ToolExecutor(registry)

    async def execute(
        self,
        *,
        call: ToolCall,
        runtime_context: dict[str, Any],
        tool_call_id: str,
        run_id: str,
        simulator_account_id: str | None,
    ) -> ToolTurnResult:
        execution = await self.executor.execute(
            call.name,
            call.arguments,
            runtime_context={**runtime_context, "tool_call_id": tool_call_id},
        )
        return ToolTurnResult(
            execution=execution,
            event_intents=self._event_intents(
                call=call,
                result=execution,
                tool_call_id=tool_call_id,
                run_id=run_id,
                simulator_account_id=simulator_account_id,
            ),
        )

    def _event_intents(
        self,
        *,
        call: ToolCall,
        result: ToolExecutionResult,
        tool_call_id: str,
        run_id: str,
        simulator_account_id: str | None,
    ) -> list[ToolEventIntent]:
        intents: list[ToolEventIntent] = []
        if call.name.startswith("order_") and result.ok and result.result:
            if result.result.get("order_id"):
                intents.append(
                    ToolEventIntent(
                        event_type="order_created",
                        payload={
                            "run_id": run_id,
                            "account_id": simulator_account_id,
                            "tool_call_id": tool_call_id,
                            "tool_name": call.name,
                            "order_id": result.result.get("order_id"),
                            "symbol": result.result.get("symbol"),
                            "side": result.result.get("side"),
                        },
                    )
                )
            if result.result.get("trade_id"):
                intents.append(
                    ToolEventIntent(
                        event_type="trade_created",
                        payload={
                            "run_id": run_id,
                            "account_id": simulator_account_id,
                            "tool_call_id": tool_call_id,
                            "tool_name": call.name,
                            "trade_id": result.result.get("trade_id"),
                            "symbol": result.result.get("symbol"),
                            "side": result.result.get("side"),
                        },
                    )
                )
        if call.name.startswith(("order_", "portfolio_")) and simulator_account_id:
            intents.append(
                ToolEventIntent(
                    event_type="portfolio_updated",
                    payload={
                        "run_id": run_id,
                        "account_id": simulator_account_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": call.name,
                    },
                    send_account_event=True,
                )
            )
        return intents
