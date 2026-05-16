from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from test_mvp import make_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_trade(client):
    account = client.post(
        "/api/simulator/accounts",
        json={"name": "View Account", "initial_cash": 100000},
    ).json()
    session = client.post(
        "/api/sessions",
        json={
            "name": "View Session",
            "simulator_account_id": account["id"],
            "model": "deepseek-v4-pro",
        },
    ).json()
    store = client.app.state.store
    now = _now()
    order_id = uuid4().hex
    trade_id = uuid4().hex
    run_id = uuid4().hex
    tool_call_id = uuid4().hex
    store.execute(
        """
        INSERT INTO orders (
            id, session_id, simulator_account_id, symbol, name,
            side, order_type, price, quantity, filled_quantity,
            status, run_id, tool_call_id, created_at, updated_at
        )
        VALUES (?, ?, ?, '000001', 'Ping An Bank', 'buy', 'market', 10, 1000, 1000, 'filled', ?, ?, ?, ?)
        """,
        (order_id, session["id"], account["id"], run_id, tool_call_id, now, now),
    )
    store.execute(
        """
        INSERT INTO trades (
            id, order_id, session_id, simulator_account_id,
            symbol, side, price, quantity, fee, tax, run_id, tool_call_id, traded_at
        )
        VALUES (?, ?, ?, ?, '000001', 'buy', 10, 1000, 5, 0, ?, ?, ?)
        """,
        (trade_id, order_id, session["id"], account["id"], run_id, tool_call_id, now),
    )
    store.execute(
        """
        INSERT INTO positions (
            id, simulator_account_id, symbol, name, quantity,
            available_quantity, avg_cost, market_value, unrealized_pnl, updated_at
        )
        VALUES (?, ?, '000001', 'Ping An Bank', 1000, 1000, 10, 11000, 1000, ?)
        """,
        (uuid4().hex, account["id"], now),
    )
    store.execute(
        """
        UPDATE simulator_accounts
        SET cash = 89995, total_asset = 100995, updated_at = ?
        WHERE id = ?
        """,
        (now, account["id"]),
    )
    client.post(f"/api/sessions/{session['id']}/messages", json={"content": "review 000001"})
    store.execute(
        """
        INSERT INTO chat_runs (
            id, session_id, provider_id, model, status,
            started_at, finished_at
        )
        VALUES (?, ?, NULL, 'deepseek-v4-pro', 'finished', ?, ?)
        """,
        (run_id, session["id"], now, now),
    )
    store.execute(
        """
        INSERT INTO chat_tool_calls (
            id, run_id, session_id, provider_call_id,
            tool_name, arguments_json, status, started_at, finished_at
        )
        VALUES (?, ?, ?, 'provider-call', 'order_buy', ?, 'finished', ?, ?)
        """,
        (
            tool_call_id,
            run_id,
            session["id"],
            json.dumps(
                {
                    "symbol": "000001",
                    "quantity": 1000,
                    "trade_reason": "放量突破短期平台，使用小仓位试探买入。",
                },
                ensure_ascii=False,
            ),
            now,
            now,
        ),
    )
    store.execute(
        """
        INSERT INTO chat_tool_results (
            id, run_id, session_id, tool_call_id, result_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            run_id,
            session["id"],
            tool_call_id,
            json.dumps(
                {
                    "ok": True,
                    "result": {
                        "kind": "order_result",
                        "order_id": order_id,
                        "trade_id": trade_id,
                        "symbol": "000001",
                        "quantity": 1000,
                        "price": 10,
                        "status": "filled",
                        "trade_reason": "放量突破短期平台，使用小仓位试探买入。",
                    },
                },
                ensure_ascii=False,
            ),
            now,
        ),
    )
    return account, session


def test_view_account_snapshot_uses_simulator_account口径(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, _ = _seed_trade(client)

    response = client.get(f"/api/view/accounts/{account['id']}/snapshot")
    assert response.status_code == 200
    body = response.json()

    assert body["account"]["id"] == account["id"]
    assert body["metrics"]["cash"] == 89995
    assert body["metrics"]["total_asset"] == 100995
    assert body["metrics"]["market_value"] == 11000
    assert body["metrics"]["floating_pnl"] == 1000
    assert body["positions"][0]["symbol"] == "000001"
    assert body["positions"][0]["name"] == "Ping An Bank"
    assert body["recent_trades"][0]["name"] == "Ping An Bank"
    assert body["recent_trades"][0]["turnover"] == 10000
    assert body["asset_points"][-1]["source"] == "current"


def test_view_assets_include_persisted_valuation_points(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, _ = _seed_trade(client)
    store = client.app.state.store
    valuation_time = "2026-05-16T10:00:00+08:00"
    store.execute(
        """
        INSERT INTO account_valuation_points (
            id, simulator_account_id, time, cash, market_value,
            unrealized_pnl, total_asset, source, symbols_json
        )
        VALUES (?, ?, ?, 89995, 11200, 1200, 101195, 'valuation', ?)
        """,
        (uuid4().hex, account["id"], valuation_time, json.dumps(["000001"])),
    )

    snapshot = client.get(f"/api/view/accounts/{account['id']}/snapshot").json()
    assets = client.get("/api/view/assets", params={"account_id": account["id"]}).json()

    assert "valuation" in [point["source"] for point in snapshot["asset_points"]]
    series_points = assets["series"][0]["points"]
    valuation = [point for point in series_points if point["source"] == "valuation"][0]
    assert valuation["time"] == valuation_time
    assert valuation["total_asset"] == 101195
    assert valuation["symbols"] == ["000001"]


def test_view_trades_filters_by_account_and_symbol(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, _ = _seed_trade(client)

    hit = client.get("/api/view/trades", params={"account_id": account["id"], "symbol": "000001"})
    miss = client.get("/api/view/trades", params={"account_id": account["id"], "symbol": "600000"})

    assert hit.status_code == 200
    assert hit.json()["summary"]["trade_count"] == 1
    assert hit.json()["trades"][0]["account_name"] == "View Account"
    assert hit.json()["trades"][0]["name"] == "Ping An Bank"
    assert miss.status_code == 200
    assert miss.json()["summary"]["trade_count"] == 0


def test_view_trades_filters_by_session_model_and_side(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, session = _seed_trade(client)

    hit = client.get(
        "/api/view/trades",
        params={
            "account_id": account["id"],
            "session_id": session["id"],
            "model": "deepseek-v4-pro",
            "side": "buy",
        },
    )
    wrong_side = client.get(
        "/api/view/trades",
        params={
            "account_id": account["id"],
            "session_id": session["id"],
            "model": "deepseek-v4-pro",
            "side": "sell",
        },
    )

    assert hit.status_code == 200
    row = hit.json()["trades"][0]
    assert row["session_id"] == session["id"]
    assert row["model"] == "deepseek-v4-pro"
    assert row["side"] == "buy"
    assert row["run_id"]
    assert row["tool_call_id"]
    assert wrong_side.status_code == 200
    assert wrong_side.json()["summary"]["trade_count"] == 0


def test_view_timeline_combines_messages_and_trades(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, session = _seed_trade(client)

    response = client.get("/api/view/timeline", params={"account_id": account["id"]})
    assert response.status_code == 200
    body = response.json()
    types = {row["type"] for row in body["items"]}

    assert {"message", "trade"}.issubset(types)
    assert any(row["session_id"] == session["id"] for row in body["items"])
    assert any(row.get("run_id") for row in body["items"] if row["type"] == "trade")


def test_order_tools_require_trade_reason(monkeypatch) -> None:
    client = make_client(monkeypatch)

    tools = client.get("/api/tools").json()
    by_name = {tool["name"]: tool for tool in tools}

    for tool_name in ("order_buy", "order_sell"):
        schema = by_name[tool_name]["parameters"]
        assert "trade_reason" in schema["properties"]
        assert "trade_reason" in schema["required"]


def test_view_logs_are_trade_reasons_not_chat_messages(monkeypatch) -> None:
    client = make_client(monkeypatch)
    account, _ = _seed_trade(client)

    response = client.get("/api/view/logs", params={"account_id": account["id"]})
    assert response.status_code == 200
    body = response.json()

    assert body["summary"]["log_count"] == 1
    log = body["logs"][0]
    assert log["tool_name"] == "order_buy"
    assert log["trade_reason"] == "放量突破短期平台，使用小仓位试探买入。"
    assert log["symbol"] == "000001"
    assert "review 000001" not in json.dumps(body, ensure_ascii=False)
