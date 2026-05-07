from __future__ import annotations

from typing import Any

from app.simulator.engine import SimulatorEngine
from app.simulator.rules import TradingRuleError
from app.tools.registry import ToolSpec


def create_order_tool_specs(engine: SimulatorEngine) -> list[ToolSpec]:
    def _filled_order_result(
        *,
        result: dict[str, Any],
        side_label: str,
        symbol: str,
        quantity: int,
        trade_reason: str,
    ) -> dict[str, Any]:
        order = result.get("order") or {}
        trade = result.get("trade") or {}
        order_price = round(float(order.get("price", 0)), 2)
        trade_price = round(float(trade.get("price", order_price)), 2)
        commission = round(float(trade.get("fee", 0)), 2)
        tax = round(float(trade.get("tax", 0)), 2)
        total_fee = round(commission + tax, 2)
        turnover = round(trade_price * quantity, 2)

        payload = {
            "kind": "order_result",
            "order_id": order.get("id"),
            "trade_id": trade.get("id"),
            "side": side_label,
            "symbol": symbol,
            "name": order.get("name", ""),
            "quantity": quantity,
            "price": trade_price,
            "order_price": order_price,
            "trade_price": trade_price,
            "filled_price": trade_price,
            "commission": commission,
            "tax": tax,
            "fee": total_fee,
            "turnover": turnover,
            "trade_reason": trade_reason,
            "status": "已成交",
        }
        if side_label == "买入":
            payload["total_cost"] = round(turnover + total_fee, 2)
        else:
            payload["total_proceeds"] = round(turnover - total_fee, 2)
        return payload

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
        trade_reason = str(arguments["trade_reason"]).strip()
        if not trade_reason:
            raise TradingRuleError("trade_reason is required.")
        session_id = str((runtime_context or {}).get("session_id") or "")

        result = await engine.place_buy(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
        )

        return _filled_order_result(
            result=result,
            side_label="买入",
            symbol=symbol,
            quantity=quantity,
            trade_reason=trade_reason,
        )

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
        trade_reason = str(arguments["trade_reason"]).strip()
        if not trade_reason:
            raise TradingRuleError("trade_reason is required.")
        session_id = str((runtime_context or {}).get("session_id") or "")

        result = await engine.place_sell(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
        )

        return _filled_order_result(
            result=result,
            side_label="卖出",
            symbol=symbol,
            quantity=quantity,
            trade_reason=trade_reason,
        )

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
                    "trade_reason": {
                        "type": "string",
                        "minLength": 1,
                        "description": "本次买入的交易理由。必须是可展示给用户的简洁自然语言摘要，不要输出完整思维链。",
                    },
                },
                "required": ["symbol", "quantity", "trade_reason"],
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
                    "trade_reason": {
                        "type": "string",
                        "minLength": 1,
                        "description": "本次卖出的交易理由。必须是可展示给用户的简洁自然语言摘要，不要输出完整思维链。",
                    },
                },
                "required": ["symbol", "quantity", "trade_reason"],
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
