from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.llm.base import ChatResponse, ToolCall
from app.main import create_app
from app.sessions.runtime import SessionRunManager
from app.tools.executor import ToolExecutor


def _test_dir() -> Path:
    path = Path("pytemp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_client(monkeypatch) -> TestClient:
    path = _test_dir()
    monkeypatch.setenv("AUTOSTOCK_SQLITE_PATH", str(path / "app.db"))
    monkeypatch.setenv("AUTOSTOCK_MARKET_DUCKDB_PATH", str(path / "market.duckdb"))
    monkeypatch.setenv("AUTOSTOCK_FRONTEND_DIST_PATH", str(path / "frontend_dist"))
    monkeypatch.setenv("AUTOSTOCK_SIMULATOR_ENFORCE_TRADING_HOURS", "0")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_session_crud(monkeypatch) -> None:
    client = make_client(monkeypatch)

    created = client.post("/api/sessions", json={"name": "Session Under Test"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    message = client.post(f"/api/sessions/{session_id}/messages", json={"content": "hello"})
    assert message.status_code == 201
    assert message.json()["content"] == "hello"

    messages = client.get(f"/api/sessions/{session_id}/messages")
    assert messages.status_code == 200
    assert [item["content"] for item in messages.json()] == ["hello"]


def test_prompt_role_crud_and_session_binding(monkeypatch) -> None:
    client = make_client(monkeypatch)

    roles = client.get("/api/prompt-roles")
    assert roles.status_code == 200
    default_role = roles.json()[0]
    assert default_role["id"] == "default"
    assert [entry["ref_name"] for entry in default_role["entries"][:2]] == ["system", "UserInput"]

    created = client.post("/api/prompt-roles", json={"name": "短线角色"})
    assert created.status_code == 201
    role = created.json()

    updated = client.put(
        f"/api/prompt-roles/{role['id']}",
        json={
            "name": "短线角色",
            "entries": [
                {
                    "id": role["entries"][0]["id"],
                    "name": "should be locked",
                    "ref_name": "system",
                    "content": "你是交易助手",
                    "enabled": True,
                    "builtin": True,
                },
                {
                    "id": role["entries"][1]["id"],
                    "name": "should be locked",
                    "ref_name": "UserInput",
                    "content": "{UserInput}{time}{risk}",
                    "enabled": True,
                    "builtin": True,
                },
                {
                    "name": "风控",
                    "ref_name": "risk",
                    "content": "严格止损",
                    "enabled": True,
                    "builtin": False,
                },
            ],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["entries"][0]["name"] == "系统提示词"
    assert body["entries"][1]["name"] == "用户输入"
    assert body["entries"][2]["ref_name"] == "risk"

    bad = client.put(
        f"/api/prompt-roles/{role['id']}",
        json={
            "name": "bad",
            "entries": [
                {"name": "系统提示词", "ref_name": "system", "content": "", "enabled": True},
                {"name": "用户输入", "ref_name": "UserInput", "content": "", "enabled": True},
                {"name": "非法", "ref_name": "time", "content": "", "enabled": True},
            ],
        },
    )
    assert bad.status_code == 400

    session = client.post(
        "/api/sessions",
        json={"name": "Prompt Bound Session", "prompt_role_id": role["id"]},
    )
    assert session.status_code == 201
    assert session.json()["prompt_role_id"] == role["id"]


def test_session_timeline_empty_and_messages(monkeypatch) -> None:
    client = make_client(monkeypatch)

    created = client.post("/api/sessions", json={"name": "Session Under Test"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    empty = client.get(f"/api/sessions/{session_id}/timeline")
    assert empty.status_code == 200
    assert empty.json() == []

    client.post(f"/api/sessions/{session_id}/messages", json={"content": "timeline entry"})
    timeline = client.get(f"/api/sessions/{session_id}/timeline")
    assert timeline.status_code == 200
    assert timeline.json()[0]["type"] == "message"
    assert timeline.json()[0]["content"] == "timeline entry"


def test_provider_and_simulator_account_and_key_mask(monkeypatch) -> None:
    client = make_client(monkeypatch)

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Provider Under Test",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    )
    assert provider.status_code == 201
    body = provider.json()
    assert body["base_url"] == "https://api.deepseek.com"
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "sk-tes****123456"
    assert "api_key" not in body

    account = client.post(
        "/api/simulator/accounts",
        json={"name": "Account Under Test", "initial_cash": 1000000},
    )
    assert account.status_code == 201


def test_account_api_creates_bindable_simulator_session(monkeypatch) -> None:
    client = make_client(monkeypatch)

    account = client.post(
        "/api/accounts",
        json={"name": "Bindable Account", "initial_cash": 1000000},
    )
    assert account.status_code == 201
    account_id = account.json()["id"]
    simulator_account = client.get(f"/api/simulator/accounts/{account_id}")
    assert simulator_account.status_code == 200

    session = client.post(
        "/api/sessions",
        json={"name": "Bound Session", "simulator_account_id": account_id},
    )
    assert session.status_code == 201
    assert session.json()["simulator_account_id"] == account_id

    legacy_session = client.post(
        "/api/sessions",
        json={"name": "Legacy Bound Session", "llm_account_id": account_id},
    )
    assert legacy_session.status_code == 201
    assert legacy_session.json()["simulator_account_id"] == account_id

    missing = client.post(
        "/api/sessions",
        json={"name": "Missing Account", "simulator_account_id": "missing"},
    )
    assert missing.status_code == 400


def test_echo_tool(monkeypatch) -> None:
    client = make_client(monkeypatch)

    tools = client.get("/api/tools")
    assert tools.status_code == 200
    tool_names = {tool["name"] for tool in tools.json()}
    assert {
        "system_echo",
        "order_buy",
        "order_sell",
        "order_cancel",
        "portfolio_get_state",
        "portfolio_get_positions",
        "portfolio_get_orders",
        "portfolio_get_trades",
    }.issubset(tool_names)

    result = client.post("/api/tools/system_echo/test", json={"arguments": {"message": "ping"}})
    assert result.status_code == 200
    assert result.json()["ok"] is True
    assert result.json()["result"] == {"echo": "ping"}


def test_session_run_loop_and_websocket_events(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class StubChatProvider:
        async def chat(self, config, messages, tools):
            if messages and messages[-1].role == "tool":
                return ChatResponse(content="done")
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tool-call-under-test",
                        name="system_echo",
                        arguments='{"message":"ping"}',
                    )
                ],
            )

        async def chat_stream(self, config, messages, tools):
            result = await self.chat(config, messages, tools)
            if result.tool_calls:
                for tc in result.tool_calls:
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tc.id,
                                            "function": {"name": tc.name, "arguments": tc.arguments},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
            elif result.content:
                yield {"choices": [{"delta": {"content": result.content}}]}

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: StubChatProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Provider Under Test",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post(
        "/api/simulator/accounts",
        json={"name": "Account Under Test"},
    ).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Session Under Test", "simulator_account_id": account["id"], "provider_id": provider["id"], "model": "deepseek-v4-flash"},
    ).json()

    with client.websocket_connect(f"/ws/sessions/{session['id']}") as websocket:
        run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
        assert run.status_code == 200
        assert run.json()["status"] == "finished"
        events = [websocket.receive_json()["type"] for _ in range(6)]

        assert events == [
            "run_started",
            "tool_call_started",
            "tool_call_finished",
            "assistant_token",
            "assistant_message",
            "run_finished",
        ]
    messages = client.get(f"/api/sessions/{session['id']}/messages").json()
    assert [message["message_type"] for message in messages] == [
        "user",
        "tool_call_request",
        "assistant",
    ]


def test_session_run_applies_prompt_role_templates(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app
    captured_messages = []

    class CapturePromptProvider:
        async def chat_stream(self, config, messages, tools):
            captured_messages.append([(message.role, message.content) for message in messages])
            yield {"choices": [{"delta": {"content": "ok"}}]}

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: CapturePromptProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Provider Under Test",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    role = client.post("/api/prompt-roles", json={"name": "Prompt Role"}).json()
    updated_role = client.put(
        f"/api/prompt-roles/{role['id']}",
        json={
            "name": "Prompt Role",
            "entries": [
                {
                    "id": role["entries"][0]["id"],
                    "name": "系统提示词",
                    "ref_name": "system",
                    "content": "系统规则：{risk}",
                    "enabled": True,
                    "builtin": True,
                },
                {
                    "id": role["entries"][1]["id"],
                    "name": "用户输入",
                    "ref_name": "UserInput",
                    "content": "问题：{UserInput}\n时间：{time}\n{risk}",
                    "enabled": True,
                    "builtin": True,
                },
                {
                    "name": "风控",
                    "ref_name": "risk",
                    "content": "严格止损",
                    "enabled": True,
                    "builtin": False,
                },
            ],
        },
    ).json()

    session = client.post(
        "/api/sessions",
        json={
            "name": "Prompted Session",
            "provider_id": provider["id"],
            "model": "deepseek-v4-flash",
            "prompt_role_id": updated_role["id"],
        },
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "分析持仓"})
    assert run.status_code == 200
    assert captured_messages[0][0] == ("system", "系统规则：严格止损")
    assert captured_messages[0][1][0] == "user"
    assert "问题：分析持仓" in captured_messages[0][1][1]
    assert "严格止损" in captured_messages[0][1][1]

    stored = client.get(f"/api/sessions/{session['id']}/messages").json()
    assert [message["message_type"] for message in stored] == ["system_prompt", "user", "assistant"]

    second = client.post(f"/api/sessions/{session['id']}/run", json={"message": "再次分析"})
    assert second.status_code == 200
    stored_again = client.get(f"/api/sessions/{session['id']}/messages").json()
    assert [message["message_type"] for message in stored_again].count("system_prompt") == 1


def test_session_timeline_includes_tool_calls_and_results(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class StubChatProvider:
        async def chat(self, config, messages, tools):
            if messages and messages[-1].role == "tool":
                return ChatResponse(content="done")
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tool-call-under-test",
                        name="system_echo",
                        arguments='{"message":"ping"}',
                    )
                ],
            )

        async def chat_stream(self, config, messages, tools):
            result = await self.chat(config, messages, tools)
            if result.tool_calls:
                for tc in result.tool_calls:
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tc.id,
                                            "function": {"name": tc.name, "arguments": tc.arguments},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
            elif result.content:
                yield {"choices": [{"delta": {"content": result.content}}]}

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: StubChatProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Provider Under Test",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post(
        "/api/simulator/accounts",
        json={"name": "Account Under Test"},
    ).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Session Under Test", "simulator_account_id": account["id"], "provider_id": provider["id"], "model": "deepseek-v4-flash"},
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
    assert run.status_code == 200

    timeline = client.get(f"/api/sessions/{session['id']}/timeline")
    assert timeline.status_code == 200
    body = timeline.json()
    assert [item["type"] for item in body] == [
        "message",
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    tool_call = next(item for item in body if item["type"] == "tool_call")
    tool_result = next(item for item in body if item["type"] == "tool_result")
    assert tool_call["tool_name"] == "system_echo"
    assert tool_call["arguments_json"] == '{"message":"ping"}'
    assert tool_result["tool_call_id"] == tool_call["id"]
    assert '"echo": "ping"' in tool_result["result_json"]


def test_tool_order_attribution_uses_session_context(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class StubChatProvider:
        async def chat(self, config, messages, tools):
            if messages and messages[-1].role == "tool":
                return ChatResponse(content="done")
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tool-call-order-buy",
                        name="order_buy",
                        arguments='{"symbol":"000001","quantity":100}',
                    )
                ],
            )

        async def chat_stream(self, config, messages, tools):
            result = await self.chat(config, messages, tools)
            if result.tool_calls:
                for tc in result.tool_calls:
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tc.id,
                                            "function": {"name": tc.name, "arguments": tc.arguments},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
            elif result.content:
                yield {"choices": [{"delta": {"content": result.content}}]}

    app.state.simulator_engine.market_provider.quote = lambda symbol: None
    app.state.simulator_engine.market_provider.quotes_batch = lambda symbols: {}
    from unittest.mock import AsyncMock
    app.state.simulator_engine.market_provider.quote = AsyncMock(
        return_value={"symbol": "000001", "name": "平安银行", "price": 12.0, "previous_close": 11.8, "volume": 1000}
    )
    app.state.simulator_engine.market_provider.quotes_batch = AsyncMock(
        return_value={"000001": {"symbol": "000001", "name": "平安银行", "price": 12.0}}
    )
    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: StubChatProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Provider Under Test",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post("/api/simulator/accounts", json={"name": "Account Under Test"}).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Session Under Test", "simulator_account_id": account["id"], "provider_id": provider["id"], "model": "deepseek-v4-flash"},
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "buy"})
    assert run.status_code == 200
    stored_result = app.state.store.fetch_one(
        """
        SELECT result_json
        FROM chat_tool_results
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (session["id"],),
    )
    assert stored_result is not None
    order_result = json.loads(stored_result["result_json"])["result"]
    assert order_result["kind"] == "order_result"
    assert order_result["order_price"] == 12.0
    assert order_result["trade_price"] == 12.0
    assert order_result["filled_price"] == 12.0
    assert order_result["turnover"] == 1200.0
    assert order_result["commission"] == 5.0
    assert order_result["tax"] == 0.0
    assert order_result["fee"] == 5.0
    assert order_result["total_cost"] == 1205.0

    orders = client.get(f"/api/simulator/accounts/{account['id']}/orders").json()
    trades = client.get(f"/api/simulator/accounts/{account['id']}/trades").json()
    assert len(orders) == 1
    assert len(trades) == 1
    assert orders[0]["session_id"] == session["id"]
    assert trades[0]["session_id"] == session["id"]

    executor = ToolExecutor(app.state.tool_registry)
    import asyncio
    trade_result = asyncio.run(
        executor.execute(
            "portfolio_get_trades",
            "{}",
            runtime_context={
                "session_id": session["id"],
                "simulator_account_id": account["id"],
            },
        )
    )
    assert trade_result.ok is True
    assert trade_result.result["kind"] == "portfolio_trades"
    assert trade_result.result["trade_count"] == 1
    assert trade_result.result["trades"][0]["session_id"] == session["id"]
    assert trade_result.result["trades"][0]["name"] == "平安银行"
