from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import get_store
from app.scheduler.account_valuation import AccountValuationRefreshService
from app.simulator.replay_clock import ReplayClockService, parse_clock_time
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/view", tags=["view"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_account_valuation_service(request: Request) -> AccountValuationRefreshService:
    service = getattr(request.app.state, "account_valuation_refresh_service", None)
    if (
        service is None
        or service.store is not request.app.state.store
        or service.market_store is not request.app.state.market_store
        or service.market_provider is not request.app.state.market_provider
    ):
        market_sync_service = getattr(request.app.state, "market_sync_service", None)
        service = AccountValuationRefreshService(
            store=request.app.state.store,
            market_store=request.app.state.market_store,
            market_provider=request.app.state.market_provider,
            quote_coordinator=getattr(market_sync_service, "quote_coordinator", None),
            websocket_manager=getattr(request.app.state, "websocket_manager", None),
        )
        request.app.state.account_valuation_refresh_service = service
    return service


@router.get("/overview")
async def view_overview(
    account_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    accounts = _accounts(store, account_id)
    snapshots = [
        _account_snapshot(store, str(account["id"]), start, end, symbol, session_id, model, side, status_filter)
        for account in accounts
    ]
    totals = _totals(snapshots)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, status_filter),
        "summary": {
            **totals,
            "account_count": len(snapshots),
            "trade_count": sum(len(snapshot["recent_trades"]) for snapshot in snapshots),
            "order_count": sum(len(snapshot["recent_orders"]) for snapshot in snapshots),
        },
        "accounts": snapshots,
        "recent_trades": _trades(store, account_id, start, end, symbol, limit=12, session_id=session_id, model=model, side=side),
        "recent_logs": _logs(store, account_id, start, end, symbol, limit=12, session_id=session_id, model=model, side=side, status_filter=status_filter),
        "recent_tools": _tool_timeline(store, account_id, start, end, symbol, 12, session_id=session_id, model=model, status_filter=status_filter),
        "recent_errors": _error_timeline(store, account_id, start, end, symbol, 12, session_id=session_id, model=model),
    }


@router.get("/accounts")
async def view_account_detail(
    account_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    accounts = _accounts(store, account_id)
    snapshots = [
        _account_snapshot(store, str(account["id"]), start, end, symbol, session_id, model, side, status_filter)
        for account in accounts
    ]
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, status_filter),
        "accounts": snapshots,
    }


@router.get("/accounts/{account_id}/snapshot")
async def view_account_snapshot(
    account_id: str,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    _account_or_404(store, account_id)
    return _account_snapshot(store, account_id, start, end, symbol, session_id, model, side, status_filter)


@router.post("/accounts/{account_id}/valuation/refresh")
async def refresh_account_valuation(
    account_id: str,
    store: SQLiteStore = Depends(get_store),
    valuation_service: AccountValuationRefreshService = Depends(get_account_valuation_service),
) -> dict[str, Any]:
    _account_or_404(store, account_id)
    try:
        result = await valuation_service.refresh_account(account_id, source="valuation")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    snapshot = _account_snapshot(store, account_id, None, None, None)
    return {
        "generated_at": result["generated_at"],
        "account": snapshot["account"],
        "metrics": snapshot["metrics"],
        "valuation_point": result.get("valuation_point"),
        "clock": result["clock"],
        "symbols": result.get("symbols", []),
        "source": result["source"],
    }


@router.get("/trades")
async def view_trades(
    account_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows = _trades(store, account_id, start, end, symbol, limit=limit, session_id=session_id, model=model, side=side)
    turnover = sum(float(row["turnover"]) for row in rows)
    fees = sum(float(row["fee"]) + float(row["tax"]) for row in rows)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, None),
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
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    time_scope: str = Query(default="current_clock", pattern="^(current_clock|all)$"),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    accounts = _accounts(store, account_id)
    series = [
        {
            "account_id": account["id"],
            "account_name": account["name"],
            "points": _asset_points(
                store,
                account,
                start,
                end,
                symbol,
                session_id=session_id,
                model=model,
                side=side,
                time_scope=time_scope,
            ),
        }
        for account in accounts
    ]
    latest_total = sum(float(item["points"][-1]["total_asset"]) for item in series if item["points"])
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, None, time_scope=time_scope),
        "summary": {
            "account_count": len(series),
            "latest_total_asset": round(latest_total, 2),
        },
        "series": series,
    }


@router.get("/logs")
async def view_logs(
    account_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows = _logs(store, account_id, start, end, symbol, limit, session_id=session_id, model=model, side=side, status_filter=status_filter)
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, status_filter),
        "summary": {"log_count": len(rows)},
        "logs": rows,
    }


@router.get("/timeline")
async def view_timeline(
    account_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=300, ge=1, le=1000),
    store: SQLiteStore = Depends(get_store),
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rows.extend(_message_timeline(store, account_id, start, end, limit, session_id=session_id, model=model))
    rows.extend(_run_timeline(store, account_id, start, end, limit, session_id=session_id, model=model, status_filter=status_filter))
    rows.extend(_trade_timeline(store, account_id, start, end, symbol, limit, session_id=session_id, model=model, side=side))
    rows.extend(_tool_timeline(store, account_id, start, end, symbol, limit, session_id=session_id, model=model, status_filter=status_filter))
    rows.sort(key=lambda row: str(row["time"]), reverse=True)
    rows = rows[:limit]
    return {
        "generated_at": utc_now(),
        "filters": _filters(account_id, session_id, model, start, end, symbol, side, status_filter),
        "summary": {"event_count": len(rows)},
        "items": rows,
    }


def _filters(
    account_id: str | None,
    session_id: str | None,
    model: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    side: str | None,
    status_filter: str | None,
    time_scope: str | None = None,
) -> dict[str, str | None]:
    return {
        "account_id": account_id or None,
        "session_id": session_id or None,
        "model": model or None,
        "start": start or None,
        "end": end or None,
        "symbol": symbol or None,
        "side": side or None,
        "status": status_filter or None,
        "time_scope": time_scope or None,
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
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
    status_filter: str | None = None,
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
        "recent_orders": _orders(store, account_id, start, end, symbol, limit=20, session_id=session_id, model=model, side=side, status_filter=status_filter),
        "recent_trades": _trades(store, account_id, start, end, symbol, limit=20, session_id=session_id, model=model, side=side),
        "asset_points": _asset_points(store, account, start, end, symbol, session_id=session_id, model=model, side=side),
        "sessions": sessions,
        "session_contributions": _session_contributions(store, account_id, start, end, symbol),
    }


def _positions(store: SQLiteStore, account_id: str, symbol: str | None = None) -> list[dict[str, Any]]:
    clauses = ["simulator_account_id = ?"]
    params: list[Any] = [account_id]
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    rows = store.fetch_all(
        f"""
        SELECT *
        FROM positions
        WHERE {' AND '.join(clauses)}
        ORDER BY symbol ASC
        """,
        params,
    )
    for row in rows:
        row["name"] = _clean_stock_name(row.get("name"))
    return rows


def _orders(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    clauses, params = _account_time_symbol_clauses("o", "created_at", account_id, start, end, symbol)
    _append_session_model_filter(clauses, params, "o", "s", "r", session_id, model)
    if side:
        clauses.append("o.side = ?")
        params.append(side)
    if status_filter:
        clauses.append("o.status = ?")
        params.append(status_filter)
    rows = store.fetch_all(
        f"""
        SELECT
            o.*,
            a.name AS account_name,
            s.name AS session_name,
            s.provider_id AS session_provider_id,
            p.name AS provider_name,
            p.provider_type,
            COALESCE(r.model, s.model) AS model
        FROM orders o
        JOIN simulator_accounts a ON a.id = o.simulator_account_id
        LEFT JOIN chat_sessions s ON s.id = o.session_id
        LEFT JOIN chat_runs r ON r.id = o.run_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
        WHERE {' AND '.join(clauses)}
        ORDER BY o.created_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )
    for row in rows:
        row["name"] = _clean_stock_name(row.get("name"))
    return rows


def _trades(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
) -> list[dict[str, Any]]:
    clauses, params = _account_time_symbol_clauses("t", "traded_at", account_id, start, end, symbol)
    _append_session_model_filter(clauses, params, "t", "s", "r", session_id, model)
    if side:
        clauses.append("t.side = ?")
        params.append(side)
    rows = store.fetch_all(
        f"""
        SELECT
            t.*,
            a.name AS account_name,
            s.name AS session_name,
            s.provider_id AS session_provider_id,
            p.name AS provider_name,
            p.provider_type,
            COALESCE(r.provider_id, s.provider_id) AS provider_id,
            COALESCE(r.model, s.model) AS model,
            o.name AS name,
            u.total_tokens AS run_total_tokens,
            u.prompt_tokens AS run_prompt_tokens,
            u.completion_tokens AS run_completion_tokens,
            u.thinking_tokens AS run_thinking_tokens,
            u.llm_calls AS run_llm_calls,
            u.cap_exceeded_count AS run_cap_exceeded_count,
            u.latency_ms AS run_latency_ms,
            tc.run_trade_count AS run_trade_count,
            ROUND(t.price * t.quantity, 2) AS turnover
        FROM trades t
        JOIN simulator_accounts a ON a.id = t.simulator_account_id
        LEFT JOIN chat_sessions s ON s.id = t.session_id
        LEFT JOIN chat_runs r ON r.id = t.run_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
        LEFT JOIN orders o ON o.id = t.order_id
        LEFT JOIN (
            SELECT
                run_id,
                COUNT(*) AS llm_calls,
                SUM(prompt_tokens) AS prompt_tokens,
                SUM(completion_tokens) AS completion_tokens,
                SUM(thinking_tokens) AS thinking_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(latency_ms) AS latency_ms,
                SUM(cap_exceeded) AS cap_exceeded_count
            FROM llm_usage_records
            WHERE run_id IS NOT NULL
            GROUP BY run_id
        ) u ON u.run_id = t.run_id
        LEFT JOIN (
            SELECT run_id, COUNT(*) AS run_trade_count
            FROM trades
            WHERE run_id IS NOT NULL
            GROUP BY run_id
        ) tc ON tc.run_id = t.run_id
        WHERE {' AND '.join(clauses)}
        ORDER BY t.traded_at DESC
        LIMIT ?
        """,
        [*params, limit],
    )
    for row in rows:
        row["name"] = _clean_stock_name(row.get("name"))
        row["total_fee"] = round(float(row.get("fee") or 0) + float(row.get("tax") or 0), 2)
        _attach_trade_usage_attribution(row)
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


def _attach_trade_usage_attribution(row: dict[str, Any]) -> None:
    run_trade_count = int(row.get("run_trade_count") or 0)
    fields = {
        "attributed_prompt_tokens": "run_prompt_tokens",
        "attributed_completion_tokens": "run_completion_tokens",
        "attributed_thinking_tokens": "run_thinking_tokens",
        "attributed_total_tokens": "run_total_tokens",
        "attributed_latency_ms": "run_latency_ms",
    }
    for target, source in fields.items():
        value = row.get(source)
        if value is None or run_trade_count <= 0:
            row[target] = None
        else:
            row[target] = round(float(value) / run_trade_count, 2)


def _asset_points(
    store: SQLiteStore,
    account: dict[str, Any],
    start: str | None,
    end: str | None,
    symbol: str | None,
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
    time_scope: str = "current_clock",
) -> list[dict[str, Any]]:
    account_id = str(account["id"])
    effective_end = _asset_scope_end(store, account, end, time_scope)
    trades = list(
        reversed(
            _trades(
                store,
                account_id,
                None,
                effective_end,
                symbol,
                limit=1000,
                session_id=session_id,
                model=model,
                side=side,
            )
        )
    )
    cash = float(account["initial_cash"])
    positions: dict[str, dict[str, Any]] = {}
    points = [
        _asset_point(
            account,
            {
                "time": account["created_at"],
                "cash": round(cash, 2),
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "total_asset": round(cash, 2),
                "source": "initial",
                "positions": [],
                "positions_recorded": True,
            },
        )
    ]

    for trade in trades:
        price = float(trade["price"])
        quantity = int(trade["quantity"])
        fee = float(trade.get("fee") or 0) + float(trade.get("tax") or 0)
        trade_symbol = str(trade["symbol"])
        if trade["side"] == "buy":
            cash -= price * quantity + fee
            existing = positions.get(trade_symbol)
            old_quantity = int(existing["quantity"]) if existing else 0
            old_avg_cost = float(existing["avg_cost"]) if existing else 0.0
            new_quantity = old_quantity + quantity
            avg_cost = ((old_quantity * old_avg_cost) + (price * quantity) + fee) / new_quantity if new_quantity > 0 else price
            positions[trade_symbol] = {
                "symbol": trade_symbol,
                "name": _clean_stock_name(trade.get("name")),
                "quantity": new_quantity,
                "avg_cost": round(avg_cost, 4),
                "last_price": price,
            }
        else:
            cash += price * quantity - fee
            existing = positions.get(trade_symbol)
            if existing is not None:
                new_quantity = int(existing["quantity"]) - quantity
                if new_quantity <= 0:
                    positions.pop(trade_symbol, None)
                else:
                    existing["quantity"] = new_quantity
                    existing["last_price"] = price
                    if trade.get("name"):
                        existing["name"] = _clean_stock_name(trade.get("name"))
        if trade_symbol in positions:
            positions[trade_symbol]["last_price"] = price
        position_snapshots = _asset_position_snapshots(positions)
        market_value = sum(float(pos["market_value"]) for pos in position_snapshots)
        unrealized_pnl = sum(float(pos["unrealized_pnl"]) for pos in position_snapshots)
        points.append(
            _asset_point(
                account,
                {
                    "time": trade["traded_at"],
                    "cash": round(cash, 2),
                    "market_value": round(market_value, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "total_asset": round(cash + market_value, 2),
                    "source": "trade",
                    "trade_id": trade["id"],
                    "trade": _asset_trade_summary(trade),
                    "positions": position_snapshots,
                    "positions_recorded": True,
                },
            )
        )

    if not symbol:
        current_positions = _current_position_snapshots(store, account_id)
        current_market_value = sum(float(pos.get("market_value") or 0) for pos in current_positions)
        current_unrealized_pnl = sum(float(pos.get("unrealized_pnl") or 0) for pos in current_positions)
        points.append(
            _asset_point(
                account,
                {
                    "time": account["updated_at"],
                    "cash": round(float(account["cash"]), 2),
                    "market_value": round(current_market_value, 2),
                    "unrealized_pnl": round(current_unrealized_pnl, 2),
                    "total_asset": round(float(account["total_asset"]), 2),
                    "source": "current",
                    "positions": current_positions,
                    "positions_recorded": True,
                },
            )
        )

    points.extend(_valuation_points(store, account, start, effective_end, symbol))
    points.sort(key=lambda point: str(point["time"]))
    start_value = _start_value(start)
    if start_value:
        points = [point for point in points if str(point["time"]) >= start_value]
    if effective_end:
        points = [point for point in points if _time_lte(str(point["time"]), effective_end)]
    return points[-240:]


def _asset_scope_end(
    store: SQLiteStore,
    account: dict[str, Any],
    end: str | None,
    time_scope: str,
) -> str | None:
    if time_scope == "all":
        return end
    clock_end = _end_of_second(ReplayClockService(store).get_clock(str(account["id"])).effective_time)
    return _earlier_time(end, clock_end)


def _earlier_time(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if parse_clock_time(_end_value(left) or left) <= parse_clock_time(_end_value(right) or right) else right


def _time_lte(value: str, end: str) -> bool:
    return parse_clock_time(value) <= parse_clock_time(_end_value(end) or end)


def _end_of_second(value: str) -> str:
    dt = parse_clock_time(value).replace(microsecond=999999)
    return dt.isoformat(timespec="microseconds")


def _valuation_points(
    store: SQLiteStore,
    account: dict[str, Any],
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> list[dict[str, Any]]:
    account_id = str(account["id"])
    clauses = ["simulator_account_id = ?"]
    params: list[Any] = [account_id]
    _append_time_filter(clauses, params, "time", start, end)
    if symbol:
        clauses.append("symbols_json LIKE ?")
        params.append(f"%{symbol}%")
    rows = store.fetch_all(
        f"""
        SELECT *
        FROM account_valuation_points
        WHERE {' AND '.join(clauses)}
        ORDER BY time ASC
        LIMIT 1000
        """,
        params,
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        positions_json = row.get("positions_json")
        position_snapshots = _valuation_position_snapshots(str(positions_json)) if positions_json else None
        points.append(
            _asset_point(
                account,
                {
                    "time": row["time"],
                    "cash": round(float(row["cash"]), 2),
                    "market_value": round(float(row["market_value"]), 2),
                    "unrealized_pnl": round(float(row["unrealized_pnl"]), 2),
                    "total_asset": round(float(row["total_asset"]), 2),
                    "source": row["source"],
                    "symbols": _json_list(str(row.get("symbols_json") or "[]")),
                    "positions": position_snapshots,
                    "positions_recorded": position_snapshots is not None,
                },
            )
        )
    return points


def _asset_point(account: dict[str, Any], point: dict[str, Any]) -> dict[str, Any]:
    initial_cash = float(account["initial_cash"])
    total_asset = float(point["total_asset"])
    pnl = round(total_asset - initial_cash, 2)
    point["pnl"] = pnl
    point["pnl_pct"] = round((pnl / initial_cash * 100), 4) if initial_cash > 0 else 0
    return point


def _asset_trade_summary(trade: dict[str, Any]) -> dict[str, Any]:
    fee = round(float(trade.get("fee") or 0) + float(trade.get("tax") or 0), 2)
    price = float(trade["price"])
    quantity = int(trade["quantity"])
    return {
        "id": trade["id"],
        "side": trade["side"],
        "symbol": trade["symbol"],
        "name": _clean_stock_name(trade.get("name")),
        "price": round(price, 4),
        "quantity": quantity,
        "turnover": round(price * quantity, 2),
        "fee": fee,
        "session_id": trade.get("session_id"),
        "session_name": trade.get("session_name"),
        "model": trade.get("model"),
        "provider_name": trade.get("provider_name"),
        "run_id": trade.get("run_id"),
        "tool_call_id": trade.get("tool_call_id"),
    }


def _asset_position_snapshots(positions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for symbol, pos in sorted(positions.items()):
        quantity = int(pos.get("quantity") or 0)
        if quantity <= 0:
            continue
        avg_cost = float(pos.get("avg_cost") or 0)
        last_price = float(pos.get("last_price") or 0)
        market_value = round(last_price * quantity, 2)
        unrealized_pnl = round(market_value - avg_cost * quantity, 2)
        snapshots.append(
            {
                "symbol": symbol,
                "name": _clean_stock_name(pos.get("name")),
                "quantity": quantity,
                "avg_cost": round(avg_cost, 4),
                "price": round(last_price, 4),
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": _pct(unrealized_pnl, avg_cost * quantity),
            }
        )
    return snapshots


def _current_position_snapshots(store: SQLiteStore, account_id: str) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for pos in _positions(store, account_id):
        quantity = int(pos.get("quantity") or 0)
        avg_cost = float(pos.get("avg_cost") or 0)
        market_value = round(float(pos.get("market_value") or 0), 2)
        unrealized_pnl = round(float(pos.get("unrealized_pnl") or 0), 2)
        snapshots.append(
            {
                "symbol": str(pos.get("symbol") or ""),
                "name": _clean_stock_name(pos.get("name")),
                "quantity": quantity,
                "avg_cost": round(avg_cost, 4),
                "price": round((market_value / quantity), 4) if quantity > 0 else 0,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": _pct(unrealized_pnl, avg_cost * quantity),
            }
        )
    return snapshots


def _valuation_position_snapshots(value: str) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        quantity = int(item.get("quantity") or 0)
        avg_cost = float(item.get("avg_cost") or 0)
        market_value = round(float(item.get("market_value") or 0), 2)
        unrealized_pnl = round(float(item.get("unrealized_pnl") or 0), 2)
        snapshots.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "name": _clean_stock_name(item.get("name")),
                "quantity": quantity,
                "avg_cost": round(avg_cost, 4),
                "price": round((market_value / quantity), 4) if quantity > 0 else 0,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": round(float(item.get("unrealized_pnl_pct")), 4)
                if item.get("unrealized_pnl_pct") is not None
                else _pct(unrealized_pnl, avg_cost * quantity),
            }
        )
    return snapshots


def _pct(value: float, base: float) -> float:
    return round((value / base * 100), 4) if base > 0 else 0


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
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["tc.tool_name IN ('order_buy', 'order_sell')"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_session_model_filter(clauses, params, "tc", "s", "r", session_id, model)
    _append_time_filter(clauses, params, "tc.started_at", start, end)
    if symbol:
        clauses.append("(tc.arguments_json LIKE ? OR tr.result_json LIKE ?)")
        like = f"%{symbol}%"
        params.extend([like, like])
    if side:
        tool_name = "order_buy" if side == "buy" else "order_sell" if side == "sell" else None
        if tool_name:
            clauses.append("tc.tool_name = ?")
            params.append(tool_name)
    if status_filter:
        clauses.append("tc.status = ?")
        params.append(status_filter)

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
            a.name AS account_name,
            COALESCE(r.provider_id, s.provider_id) AS provider_id,
            p.name AS provider_name,
            p.provider_type,
            COALESCE(r.model, s.model) AS model
        FROM chat_tool_calls tc
        JOIN chat_sessions s ON s.id = tc.session_id
        LEFT JOIN chat_runs r ON r.id = tc.run_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
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
                "provider_id": row.get("provider_id"),
                "provider_name": row.get("provider_name"),
                "provider_type": row.get("provider_type"),
                "model": row.get("model"),
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
    session_id: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_session_model_filter(clauses, params, "m", "s", None, session_id, model)
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
            s.provider_id AS provider_id,
            p.name AS provider_name,
            p.provider_type,
            s.model AS model,
            m.role,
            m.message_type,
            m.content,
            m.reasoning_content,
            m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        LEFT JOIN llm_providers p ON p.id = s.provider_id
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
    session_id: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    rows = _message_logs(store, account_id, start, end, None, limit, session_id=session_id, model=model)
    return [
        {
            "id": row["id"],
            "type": "message",
            "time": row["created_at"],
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "session_id": row["session_id"],
            "session_name": row["session_name"],
            "provider_id": row.get("provider_id"),
            "provider_name": row.get("provider_name"),
            "provider_type": row.get("provider_type"),
            "model": row.get("model"),
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
    session_id: str | None = None,
    model: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_session_model_filter(clauses, params, "r", "s", "r", session_id, model)
    if status_filter:
        clauses.append("r.status = ?")
        params.append(status_filter)
    _append_time_filter(clauses, params, "r.started_at", start, end)
    rows = store.fetch_all(
        f"""
        SELECT
            r.*,
            s.name AS session_name,
            s.simulator_account_id AS account_id,
            a.name AS account_name,
            COALESCE(r.provider_id, s.provider_id) AS provider_id,
            p.name AS provider_name,
            p.provider_type
        FROM chat_runs r
        JOIN chat_sessions s ON s.id = r.session_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
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
            "provider_id": row.get("provider_id"),
            "provider_name": row.get("provider_name"),
            "provider_type": row.get("provider_type"),
            "model": row.get("model"),
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
    session_id: str | None = None,
    model: str | None = None,
    side: str | None = None,
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
            "provider_id": row.get("provider_id"),
            "provider_name": row.get("provider_name"),
            "provider_type": row.get("provider_type"),
            "model": row.get("model"),
            "run_id": row.get("run_id"),
            "tool_call_id": row.get("tool_call_id"),
            "symbol": row["symbol"],
            "title": f"{row['side']} {row['symbol']}",
            "summary": f"{row['quantity']} shares @ {row['price']}",
            "payload": row,
        }
        for row in _trades(store, account_id, start, end, symbol, limit, session_id=session_id, model=model, side=side)
    ]


def _tool_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
    session_id: str | None = None,
    model: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.simulator_account_id = ?")
        params.append(account_id)
    _append_session_model_filter(clauses, params, "tc", "s", "r", session_id, model)
    if status_filter:
        clauses.append("tc.status = ?")
        params.append(status_filter)
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
            a.name AS account_name,
            COALESCE(r.provider_id, s.provider_id) AS provider_id,
            p.name AS provider_name,
            p.provider_type,
            COALESCE(r.model, s.model) AS model
        FROM chat_tool_calls tc
        JOIN chat_sessions s ON s.id = tc.session_id
        LEFT JOIN chat_runs r ON r.id = tc.run_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
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
            "provider_id": row.get("provider_id"),
            "provider_name": row.get("provider_name"),
            "provider_type": row.get("provider_type"),
            "model": row.get("model"),
            "run_id": row.get("run_id"),
            "tool_call_id": row.get("id"),
            "symbol": _extract_symbol(row),
            "title": row["tool_name"],
            "summary": row.get("error") or row["status"],
            "payload": row,
        }
        for row in rows
    ]


def _error_timeline(
    store: SQLiteStore,
    account_id: str | None,
    start: str | None,
    end: str | None,
    symbol: str | None,
    limit: int,
    session_id: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    run_errors = _run_timeline(
        store,
        account_id,
        start,
        end,
        limit,
        session_id=session_id,
        model=model,
        status_filter="error",
    )
    tool_errors = _tool_timeline(
        store,
        account_id,
        start,
        end,
        symbol,
        limit,
        session_id=session_id,
        model=model,
        status_filter="error",
    )
    rows = [*run_errors, *tool_errors]
    rows.sort(key=lambda row: str(row["time"]), reverse=True)
    return rows[:limit]


def _session_contributions(
    store: SQLiteStore,
    account_id: str,
    start: str | None,
    end: str | None,
    symbol: str | None,
) -> list[dict[str, Any]]:
    clauses, params = _account_time_symbol_clauses("t", "traded_at", account_id, start, end, symbol)
    rows = store.fetch_all(
        f"""
        SELECT
            COALESCE(t.session_id, '') AS session_id,
            COALESCE(s.name, '未绑定 Session') AS session_name,
            COALESCE(r.provider_id, s.provider_id) AS provider_id,
            p.name AS provider_name,
            p.provider_type,
            COALESCE(r.model, s.model, '') AS model,
            COUNT(*) AS trade_count,
            SUM(CASE WHEN t.side = 'buy' THEN 1 ELSE 0 END) AS buy_count,
            SUM(CASE WHEN t.side = 'sell' THEN 1 ELSE 0 END) AS sell_count,
            ROUND(SUM(t.price * t.quantity), 2) AS turnover,
            ROUND(SUM(t.fee + t.tax), 2) AS fees,
            ROUND(SUM(CASE
                WHEN u.total_tokens IS NOT NULL AND tc.run_trade_count > 0
                THEN CAST(u.total_tokens AS REAL) / tc.run_trade_count
                ELSE 0
            END), 2) AS attributed_total_tokens,
            ROUND(SUM(CASE
                WHEN u.latency_ms IS NOT NULL AND tc.run_trade_count > 0
                THEN CAST(u.latency_ms AS REAL) / tc.run_trade_count
                ELSE 0
            END), 1) AS attributed_latency_ms
        FROM trades t
        LEFT JOIN chat_sessions s ON s.id = t.session_id
        LEFT JOIN chat_runs r ON r.id = t.run_id
        LEFT JOIN llm_providers p ON p.id = COALESCE(r.provider_id, s.provider_id)
        LEFT JOIN (
            SELECT
                run_id,
                SUM(total_tokens) AS total_tokens,
                SUM(latency_ms) AS latency_ms
            FROM llm_usage_records
            WHERE run_id IS NOT NULL
            GROUP BY run_id
        ) u ON u.run_id = t.run_id
        LEFT JOIN (
            SELECT run_id, COUNT(*) AS run_trade_count
            FROM trades
            WHERE run_id IS NOT NULL
            GROUP BY run_id
        ) tc ON tc.run_id = t.run_id
        WHERE {' AND '.join(clauses)}
        GROUP BY t.session_id, s.name, COALESCE(r.provider_id, s.provider_id), p.name, p.provider_type, COALESCE(r.model, s.model, '')
        ORDER BY turnover DESC
        """,
        params,
    )
    return rows


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


def _append_session_model_filter(
    clauses: list[str],
    params: list[Any],
    record_alias: str,
    session_alias: str,
    run_alias: str | None,
    session_id: str | None,
    model: str | None,
) -> None:
    if session_id:
        clauses.append(f"{record_alias}.session_id = ?")
        params.append(session_id)
    if model:
        if run_alias:
            clauses.append(f"COALESCE({run_alias}.model, {session_alias}.model) = ?")
        else:
            clauses.append(f"{session_alias}.model = ?")
        params.append(model)


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


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _extract_symbol(row: dict[str, Any]) -> str | None:
    arguments = _json_object(str(row.get("arguments_json") or "{}"))
    if arguments.get("symbol"):
        return str(arguments["symbol"])
    envelope = _json_object(str(row.get("result_json") or "{}"))
    result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
    if isinstance(result, dict) and result.get("symbol"):
        return str(result["symbol"])
    return None


def _clean_stock_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "None", "none", "null", "NULL", "nan", "NaN", "--", "-"}:
        return ""
    return text
