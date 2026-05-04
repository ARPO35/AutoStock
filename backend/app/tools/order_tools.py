from __future__ import annotations

from typing import Any

from app.simulator.engine import SimulatorEngine
from app.simulator.rules import TradingRuleError
from app.tools.registry import ToolSpec


def create_order_tool_specs(engine: SimulatorEngine) -> list[ToolSpec]:
    async def order_buy(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = str(
            arguments.get("simulator_account_id")
            or (runtime_context or {}).get("simulator_account_id")
            or ""
        )
        if not account_id:
            raise TradingRuleError("缺少 simulator_account_id，且当前会话未绑定模拟账户。")
        symbol = str(arguments["symbol"]).strip()
        quantity = int(arguments["quantity"])
        session_id = str((runtime_context or {}).get("session_id") or "")

        result = await engine.place_buy(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
        )

        trade_data = result.get("trade")
        return {
            "kind": "order_result",
            "side": "买入",
            "symbol": symbol,
            "name": result.get("order", {}).get("name", ""),
            "quantity": quantity,
            "price": float(result.get("order", {}).get("price", 0)),
            "fee": (
                round(float(trade_data["fee"]) + float(trade_data["tax"]), 2)
                if trade_data
                else 0
            ),
            "status": "已成交",
            "total_cost": round(float(result.get("order", {}).get("price", 0)) * quantity, 2),
        }

    async def order_sell(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = str(
            arguments.get("simulator_account_id")
            or (runtime_context or {}).get("simulator_account_id")
            or ""
        )
        if not account_id:
            raise TradingRuleError("缺少 simulator_account_id，且当前会话未绑定模拟账户。")
        symbol = str(arguments["symbol"]).strip()
        quantity = int(arguments["quantity"])
        session_id = str((runtime_context or {}).get("session_id") or "")

        result = await engine.place_sell(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
        )

        trade_data = result.get("trade")
        return {
            "kind": "order_result",
            "side": "卖出",
            "symbol": symbol,
            "name": result.get("order", {}).get("name", ""),
            "quantity": quantity,
            "price": float(result.get("order", {}).get("price", 0)),
            "fee": (
                round(float(trade_data["fee"]) + float(trade_data["tax"]), 2)
                if trade_data
                else 0
            ),
            "status": "已成交",
            "total_proceeds": round(float(result.get("order", {}).get("price", 0)) * quantity, 2),
        }

    async def order_cancel(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = str(arguments["order_id"])

        result = engine.cancel_order(order_id)

        return {
            "kind": "order_result",
            "side": result["side"],
            "symbol": result["symbol"],
            "name": result["name"],
            "quantity": int(result["quantity"]),
            "price": float(result["price"]),
            "status": "已撤单",
        }

    return [
        ToolSpec(
            name="order_buy",
            display_name="order.buy",
            description="模拟买入A股股票。以当前市价立即成交，自动计算手续费。买入数量必须为100股的整数倍。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "A股股票代码，如 600000 或 000001。",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "买入股数，必须为100的整数倍。",
                    },
                },
                "required": ["symbol", "quantity"],
                "additionalProperties": False,
            },
            handler=order_buy,
            strict=True,
        ),
        ToolSpec(
            name="order_sell",
            display_name="order.sell",
            description="模拟卖出A股股票。以当前市价立即成交，自动计算手续费和印花税。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "A股股票代码。",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "卖出股数，不能超过可用持仓。",
                    },
                },
                "required": ["symbol", "quantity"],
                "additionalProperties": False,
            },
            handler=order_sell,
            strict=True,
        ),
        ToolSpec(
            name="order_cancel",
            display_name="order.cancel",
            description="撤销未成交的模拟订单（仅 pending 状态可撤）。",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "要撤销的订单ID。",
                    },
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
            handler=order_cancel,
            strict=True,
        ),
    ]
