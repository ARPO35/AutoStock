from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_store
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/view", tags=["view"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/overview")
async def view_overview(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    accounts = _accounts(store, account_id)
    snapshots = [_account_snapshot(store, str(account["id"]), start, end, symbol) for account in accounts]
    totals = _totals(snapshots)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "summary": {
            **totals,
            "account_count": len(snapshots),
            "trade_count": sum(len(snapshot["recent_trades"]) for snapshot in snapshots),
            "order_count": sum(len(snapshot["recent_orders"]) for snapshot in snapshots),
        },
        "accounts": snapshots,
        "recent_trades": _trades(store, account_id, start, end, symbol, limit=12),
        "recent_logs": _logs(store, account_id, start, end, symbol, limit=12),
    }


@router.get("/accounts")
async def view_account_detail(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    snapshots = [
        _account_snapshot(store, str(account["id"]), start, end, symbol)
        for account in _accounts(store, account_id)
    ]
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "accounts": snapshots,
    }


@router.get("/accounts/{account_id}/snapshot")
async def view_account_snapshot(
    account_id: str,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    _account_or_404(store, account_id)
    return _account_snapshot(store, account_id, start, end, symbol)


@router.get("/trades")
async def view_trades(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows = _trades(store, account_id, start, end, symbol, limit=limit)
    turnover = sum(float(row["turnover"]) for row in rows)
    fees = sum(float(row["fee"]) + float(row["tax"]) for row in rows)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "summary": {
            "trade_count": len(rows),
            "turnover": round(turnover, 2),
            "fees": round(fees, 2),
        },
        "trades": rows,
    }


@router.get("/assets")
async def view_assets(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    accounts = _accounts(store, account_id)
    series = [
        {
            "account_id": account["id"],
            "account_name": account["name"],
            "points": _asset_points(store, account, start, end, symbol),
        }
        for account in accounts
    ]
    latest_total = sum(float(item["points"][-1]["total_asset"]) for item in series if item["points"])
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "summary": {
            "account_count": len(series),
            "latest_total_asset": round(latest_total, 2),
        },
        "series": series,
    }


@router.get("/logs")
async def view_logs(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows = _logs(store, account_id, start, end, symbol, limit)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "summary": {"log_count": len(rows)},
        "logs": rows,
    }


@router.get("/timeline")
async def view_timeline(
    account_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    limit: int = Query(default=300, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rows.extend(_message_timeline(store, account_id, start, end, limit))
    rows.extend(_run_timeline(store, account_id, start, end, limit))
    rows.extend(_trade_timeline(store, account_id, start, end, symbol, limit))
    rows.extend(_tool_timeline(store, account_id, start, end, symbol, limit))
    rows.sort(key=lambda row: str(row["time"]), reverse=True)
    rows = rows[:limit]
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, start, end, symbol),
        "summary": {"event_count": len(rows)},
        "items": rows,
    }


def _filters(
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> dict[str, str | None]:
    return {
        "account_id": account_id or None,
        "start": start or None,
        "end": end or None,
        "symbol": symbol or None,
    }


def _accounts(store: SQLiteStore, account_id: str | None = None) -> list[dict[str, Any]]:
    if account_id:
        return [_account_or_404(store, account_id)]
    return store.fetch_all(
        """
        SELECT *
        FROM simulator_accounts
        ORDER BY created_at DESC
        """
    )


def _account_or_404(store: SQLiteStore, account_id: str) -> dict[str, Any]:
    account = store.fetch_one("SELECT * FROM simulator_accounts WHERE id = ?", (account_id,))
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulator account not found: {account_id}",
        )
    return account


def _account_snapshot(
    store: SQLiteStore,
    account_id: str,
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> dict[str, Any]:
    account = _account_or_404(store, account_id)
    positions = _positions(store, account_id, symbol)
    market_value = round(sum(float(row.get("market_value") or 0) for row in positions), 2)
    floating_pnl = round(sum(float(row.get("unrealized_pnl") or 0) for row in positions), 2)
    total_asset = float(account["total_asset"])
    initial_cash = float(account["initial_cash"])
    cash = float(account["cash"])
    position_ratio = market_value / total_asset if total_asset > 0 else 0.0
    sessions = _sessions_for_account(store, account_id)
    return {
        "account": account,
        "metrics": {
            "initial_cash": round(initial_cash, 2),
            "cash": round(cash, 2),
            "frozen_cash": round(float(account.get("frozen_cash") or 0), 2),
            "total_asset": round(total_asset, 2),
            "market_value": market_value,
            "floating_pnl": floating_pnl,
            "total_pnl": round(total_asset - initial_cash, 2),
            "total_return_pct": round(((total_asset - initial_cash) / initial_cash * 100), 4)
            if initial_cash > 0
            else 0,
            "position_ratio": round(position_ratio, 4),
            "position_count": len(positions),
            "session_count": len(sessions),
            "running_sessions": sum(1 for row in sessions if "run" in str(row.get("status", "")).lower()),
        },
        "positions": positions,
        "recent_orders": _orders(store, account_id, start, end, symbol, limit=20),
        "recent_trades": _trades(store, account_id, start, end, symbol, limit=20),
        "asset_points": _asset_points(store, account, start, end, symbol),
        "sessions": sessions,
    }


def _positions(store: SQLiteStore, account_id: str, symbol: str | None = None) -> list[dict[str, Any]]:
    clauses = ["simulator_account_id = ?"]
    params: list[Any] = [account_id]
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    return store.fetch_all(
        f"""
        SELECT *
        FROM positions
        WHERE {' AND '.join(clauses)}
        ORDER BY symbol ASC
        """,
        params,
    )


def _orders(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses, params = _account_time_symbol_clauses("o", "created_at", account_id, start, end, symbol)
    return store.fetch_all(
        f"""
        SELECT o.*, a.name AS account_name, s.name AS session_name
        FROM orders o
        JOIN simulator_accounts a ON a.id = o.simulator_account_id
        LEFT JOIN chat_sessions s ON s.id = o.session_id
        WHERE {' AND '.join(clauses)}
        ORDER BY o.created_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )


def _trades(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses, params = _account_time_symbol_clauses("t", "traded_at", account_id, start, end, symbol)
    rows = store.fetch_all(
        f"""
        SELECT
            t.*,
            a.name AS account_name,
            s.name AS session_name,
            o.name AS name,
            ROUND(t.price * t.quantity, 2) AS turnover
        FROM trades t
        JOIN simulator_accounts a ON a.id = t.simulator_account_id
        LEFT JOIN chat_sessions s ON s.id = t.session_id
        LEFT JOIN orders o ON o.id = t.order_id
        WHERE {' AND '.join(clauses)}
        ORDER BY t.traded_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )
    for row in rows:
        row["total_fee"] = round(float(row.get("fee") or 0) + float(row.get("tax") or 0), 2)
    return rows


def _sessions_for_account(store: SQLiteStore, account_id: str) -> list[dict[str, Any]]:
    return store.fetch_all(
        """
        SELECT s.*, p.name AS provider_name, p.provider_type
        FROM chat_sessions s
        LEFT JOIN llm_providers p ON p.id = s.provider_id
        WHERE s.simulator_account_id = ?
        ORDER BY s.updated_at DESC
        """,
        (account_id,),
    )


def _asset_points(
    store: SQLiteStore,
    account: dict[str, Any],
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> list[dict[str, Any]]:
    account_id = str(account["id"])
    trades = list(reversed(_trades(store, account_id, None, end, symbol, limit=1000)))
    cash = float(account["initial_cash"])
    quantities: defaultdict[str, int] = defaultdict(int)
    last_prices: dict[str, float] = {}
    points = [
        {
            "time": account["created_at"],
            "cash": round(cash, 2),
            "market_value": 0.0,
            "total_asset": round(cash, 2),
            "source": "initial",
        }
    ]

    for trade in trades:
        price = float(trade["price"])
        quantity = int(trade["quantity"])
        fee = float(trade.get("fee") or 0) + float(trade.get("tax") or 0)
        trade_symbol = str(trade["symbol"])
        if trade["side"] == "buy":
            cash -= price * quantity + fee
            quantities[trade_symbol] += quantity
        else:
            cash += price * quantity - fee
            quantities[trade_symbol] -= quantity
        last_prices[trade_symbol] = price
        market_value = sum(max(qty, 0) * last_prices.get(sym, 0.0) for sym, qty in quantities.items())
        points.append(
            {
                "time": trade["traded_at"],
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "total_asset": round(cash + market_value, 2),
                "source": "trade",
                "trade_id": trade["id"],
            }
        )

    if not symbol:
        current_market_value = sum(float(pos.get("market_value") or 0) for pos in _positions(store, account_id))
        points.append(
            {
                "time": account["updated_at"],
                "cash": round(float(account["cash"]), 2),
                "market_value": round(current_market_value, 2),
                "total_asset": round(float(account["total_asset"]), 2),
                "source": "current",
            }
        )

    start_value = _start_value(start)
    if start_value:
        points = [point for point in points if str(point["time"]) >= start_value]
    return points[-240:]


def _totals(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [snapshot["metrics"] for snapshot in snapshots]
    return {
        "cash": round(sum(float(row["cash"]) for row in metrics), 2),
        "total_asset": round(sum(float(row["total_asset"]) for row in metrics), 2),
        "market_value": round(sum(float(row["market_value"]) for row in metrics), 2),
        "floating_pnl": round(sum(float(row["floating_pnl"]) for row in metrics), 2),
        "total_pnl": round(sum(float(row["total_pnl"]) for row in metrics), 2),
        "position_count": sum(int(row["position_count"]) for row in metrics),
        "running_sessions": sum(int(row["running_sessions"]) for row in metrics),
    }


def _logs(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["tc.tool_name IN ('order_buy', 'order_sell')"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_time_filter(clauses, params, "tc.started_at", start, end)
    if symbol:
        clauses.append("(tc.arguments_json LIKE ? OR tr.result_json LIKE ?)")
        like = f"%{symbol}%"
        params.extend([like, like])

    rows = store.fetch_all(
        f"""
        SELECT
            tc.id,
            tc.run_id,
            tc.session_id,
            tc.tool_name,
            tc.arguments_json,
            tc.status AS tool_status,
            tc.started_at,
            tc.finished_at,
            tc.error,
            tr.result_json,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name
        FROM chat_tool_calls tc
        JOIN chat_sessions s ON s.id = tc.session_id
        LEFT JOIN simulator_accounts a ON a.id = s.simulator_account_id
        LEFT JOIN chat_tool_results tr ON tr.tool_call_id = tc.id
        WHERE {' AND '.join(clauses)}
        ORDER BY tc.started_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )

    logs: list[dict[str, Any]] = []
    for row in rows:
        arguments = _json_object(str(row.get("arguments_json") or "{}"))
        envelope = _json_object(str(row.get("result_json") or "{}"))
        result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
        assert isinstance(result, dict)
        side = "buy" if row["tool_name"] == "order_buy" else "sell"
        logs.append(
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "session_id": row["session_id"],
                "session_name": row["session_name"],
                "account_id": row["account_id"],
                "account_name": row["account_name"],
                "tool_name": row["tool_name"],
                "side": side,
                "symbol": arguments.get("symbol") or result.get("symbol"),
                "quantity": arguments.get("quantity") or result.get("quantity"),
                "price": result.get("price") or result.get("filled_price"),
                "status": result.get("status") or row.get("tool_status"),
                "trade_reason": arguments.get("trade_reason") or result.get("trade_reason") or "",
                "created_at": row["started_at"],
                "finished_at": row.get("finished_at"),
                "error": row.get("error") or envelope.get("error"),
                "result": result,
            }
        )
    return logs


def _message_logs(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_time_filter(clauses, params, "m.created_at", start, end)
    if symbol:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM chat_tool_calls tc
                LEFT JOIN chat_tool_results tr ON tr.tool_call_id = tc.id
                WHERE tc.session_id = s.id
                  AND (tc.arguments_json LIKE ? OR tr.result_json LIKE ?)
            )
            """
        )
        like = f"%{symbol}%"
        params.extend([like, like])
    return store.fetch_all(
        f"""
        SELECT
            m.id,
            m.session_id,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name,
            m.role,
            m.message_type,
            m.content,
            m.reasoning_content,
            m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        LEFT JOIN simulator_accounts a ON a.id = s.simulator_account_id
        WHERE {' AND '.join(clauses)}
        ORDER BY m.created_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )


def _message_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = _message_logs(store, account_id, start, end, None, limit)
    return [
        {
            "id": row["id"],
            "type": "message",
            "time": row["created_at"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "title": f"{row['role']} / {row['message_type']}",
            "summary": str(row.get("content") or "")[:240],
            "payload": row,
        }
        for row in rows
    ]


def _run_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_time_filter(clauses, params, "r.started_at", start, end)
    rows = store.fetch_all(
        f"""
        SELECT
            r.*,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name
        FROM chat_runs r
        JOIN chat_sessions s ON s.id = r.session_id
        LEFT JOIN simulator_accounts a ON a.id = s.simulator_account_id
        WHERE {' AND '.join(clauses)}
        ORDER BY r.started_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )
    return [
        {
            "id": row["id"],
            "type": "run",
            "time": row["started_at"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "title": f"Run {row['status']}",
            "summary": row.get("error") or row.get("model") or "",
            "payload": row,
        }
        for row in rows
    ]


def _trade_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "type": "trade",
            "time": row["traded_at"],
            "account_id": row["simulator_account_id"],
            "account_name": row["account_name"],
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "symbol": row["symbol"],
            "title": f"{row['side']} {row['symbol']}",
            "summary": f"{row['quantity']} shares @ {row['price']}",
            "payload": row,
        }
        for row in _trades(store, account_id, start, end, symbol, limit)
    ]


def _tool_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_time_filter(clauses, params, "tc.started_at", start, end)
    if symbol:
        clauses.append("(tc.arguments_json LIKE ? OR tr.result_json LIKE ?)")
        like = f"%{symbol}%"
        params.extend([like, like])
    rows = store.fetch_all(
        f"""
        SELECT
            tc.*,
            tr.result_json,
            tr.created_at AS result_created_at,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name
        FROM chat_tool_calls tc
        JOIN chat_sessions s ON s.id = tc.session_id
        LEFT JOIN simulator_accounts a ON a.id = s.simulator_account_id
        LEFT JOIN chat_tool_results tr ON tr.tool_call_id = tc.id
        WHERE {' AND '.join(clauses)}
        ORDER BY tc.started_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )
    return [
        {
            "id": row["id"],
            "type": "tool",
            "time": row["started_at"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "title": row["tool_name"],
            "summary": row.get("error") or row["status"],
            "payload": row,
        }
        for row in rows
    ]


def _account_time_symbol_clauses(
    alias: str,
    time_column: str,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> tuple[list[str], list[Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append(f"{alias}.simulator_account_id = ?")
        params.append(account_id)
    if symbol:
        clauses.append(f"{alias}.symbol = ?")
        params.append(symbol)
    _append_time_filter(clauses, params, f"{alias}.{time_column}", start, end)
    return clauses, params


def _append_time_filter(
    clauses: list[str],
    params: list[Any],
    column: str,
    start: str | None,
    end: str | None,
) -> None:
    start_value = _start_value(start)
    end_value = _end_value(end)
    if start_value:
        clauses.append(f"{column} >= ?")
        params.append(start_value)
    if end_value:
        clauses.append(f"{column} <= ?")
        params.append(end_value)


def _start_value(value: str | None) -> str | None:
    if not value:
        return None
    return value if "T" in value else f"{value}T00:00:00"


def _end_value(value: str | None) -> str | None:
    if not value:
        return None
    return value if "T" in value else f"{value}T23:59:59.999999"


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
