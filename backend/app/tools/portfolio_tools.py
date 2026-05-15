from __future__ import annotations

from typing import Any

from app.simulator.engine import SimulatorEngine
from app.simulator.rules import TradingRuleError
from app.tools.registry import ToolSpec


def create_portfolio_tool_specs(engine: SimulatorEngine) -> list[ToolSpec]:
    def _resolve_account_id(
        arguments: dict[str, Any], runtime_context: dict[str, Any] | None
    ) -> str:
        account_id = str(
            arguments.get("simulator_account_id")
            or (runtime_context or {}).get("simulator_account_id")
            or ""
        )
        if not account_id:
            raise TradingRuleError("缺少 simulator_account_id，且当前会话未绑定模拟账户。")
        return account_id

    async def get_state(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = _resolve_account_id(arguments, runtime_context)
        await engine.refresh_account_valuation(account_id)
        account = engine.get_account(account_id)
        positions = engine.get_positions(account_id)

        market_value = 0.0
        floating_pnl = 0.0
        for pos in positions:
            market_value += float(pos.get("market_value", 0))
            floating_pnl += float(pos.get("unrealized_pnl", 0))

        return {
            "kind": "portfolio_state",
            "account_id": account_id,
            "account_name": account["name"],
            "initial_cash": float(account["initial_cash"]),
            "cash": float(account["cash"]),
            "frozen_cash": float(account["frozen_cash"]),
            "total_assets": float(account["total_asset"]),
            "market_value": round(market_value, 2),
            "floating_pnl": round(floating_pnl, 2),
            "total_pnl": round(float(account["total_asset"]) - float(account["initial_cash"]), 2),
            "commission_rate": float(account["commission_rate"]),
            "min_commission": float(account["min_commission"]),
            "position_count": len(positions),
        }

    async def get_positions(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = _resolve_account_id(arguments, runtime_context)
        await engine.refresh_account_valuation(account_id)
        positions = engine.get_positions(account_id)

        position_list = []
        for pos in positions:
            position_list.append({
                "symbol": pos["symbol"],
                "name": pos["name"],
                "quantity": int(pos["quantity"]),
                "available_quantity": int(pos["available_quantity"]),
                "avg_cost": round(float(pos["avg_cost"]), 4),
                "market_value": round(float(pos["market_value"]), 2),
                "unrealized_pnl": round(float(pos["unrealized_pnl"]), 2),
            })

        return {
            "kind": "portfolio_positions",
            "account_id": account_id,
            "positions": position_list,
            "position_count": len(position_list),
        }

    async def get_orders(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = _resolve_account_id(arguments, runtime_context)
        status = arguments.get("status")
        status_str = str(status) if status else None
        orders = engine.get_orders(account_id, status_str)

        order_list = []
        for o in orders:
            order_list.append({
                "order_id": o["id"],
                "symbol": o["symbol"],
                "name": o["name"],
                "side": o["side"],
                "order_type": o["order_type"],
                "price": round(float(o["price"]), 2),
                "quantity": int(o["quantity"]),
                "filled_quantity": int(o["filled_quantity"]),
                "status": o["status"],
                "created_at": o["created_at"],
            })

        return {
            "kind": "portfolio_orders",
            "account_id": account_id,
            "orders": order_list,
            "order_count": len(order_list),
        }

    async def get_trades(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = _resolve_account_id(arguments, runtime_context)
        trades = engine.get_trades(account_id)

        trade_list = []
        for trade in trades:
            order = engine.store.fetch_one(
                "SELECT name FROM orders WHERE id = ?",
                (trade["order_id"],),
            )
            price = round(float(trade["price"]), 2)
            quantity = int(trade["quantity"])
            fee = round(float(trade["fee"]), 2)
            tax = round(float(trade["tax"]), 2)
            trade_list.append({
                "trade_id": trade["id"],
                "order_id": trade["order_id"],
                "session_id": trade["session_id"],
                "symbol": trade["symbol"],
                "name": (order or {}).get("name", ""),
                "side": trade["side"],
                "price": price,
                "quantity": quantity,
                "fee": fee,
                "tax": tax,
                "total_fee": round(fee + tax, 2),
                "turnover": round(price * quantity, 2),
                "traded_at": trade["traded_at"],
            })

        return {
            "kind": "portfolio_trades",
            "account_id": account_id,
            "trades": trade_list,
            "trade_count": len(trade_list),
        }

    return [
        ToolSpec(
            name="portfolio_get_state",
            display_name="portfolio.get_state",
            description="查询模拟账户概览：现金、总资产、浮动盈亏、仓位数量等。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=get_state,
            strict=True,
        ),
        ToolSpec(
            name="portfolio_get_positions",
            display_name="portfolio.get_positions",
            description="查询模拟账户当前持仓列表：股票代码、名称、数量、可用数量、均价、市值、浮动盈亏。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=get_positions,
            strict=True,
        ),
        ToolSpec(
            name="portfolio_get_orders",
            display_name="portfolio.get_orders",
            description="查询模拟账户订单列表，可按状态过滤。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    },
                    "status": {
                        "type": "string",
                        "description": "订单状态过滤：pending/partial/filled/cancelled/rejected。不传则返回全部。",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=get_orders,
            strict=True,
        ),
        ToolSpec(
            name="portfolio_get_trades",
            display_name="portfolio.get_trades",
            description="查询模拟账户成交记录：成交ID、订单ID、股票、方向、成交价、数量、费用和成交时间。",
            parameters={
                "type": "object",
                "properties": {
                    "simulator_account_id": {
                        "type": "string",
                        "description": "模拟账户ID。",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=get_trades,
            strict=True,
        ),
    ]
