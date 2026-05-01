from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.llm.base import ChatResponse, ToolCall
from app.main import create_app
from app.sessions.runtime import SessionRunManager


def _test_dir() -> Path:
    path = Path("pytemp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_client(monkeypatch) -> TestClient:
    path = _test_dir()
    monkeypatch.setenv("AUTOSTOCK_SQLITE_PATH", str(path / "app.db"))
    monkeypatch.setenv("AUTOSTOCK_MARKET_DUCKDB_PATH", str(path / "market.duckdb"))
    monkeypatch.setenv("AUTOSTOCK_FRONTEND_DIST_PATH", str(path / "frontend_dist"))
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


def test_provider_account_and_key_mask(monkeypatch) -> None:
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
    assert body["api_key_masked"] == "sk-t...3456"
    assert "api_key" not in body

    account = client.post(
        "/api/accounts",
        json={"name": "Account Under Test", "provider_id": body["id"], "initial_cash": 1000000},
    )
    assert account.status_code == 201
    assert account.json()["provider_id"] == body["id"]


def test_echo_tool(monkeypatch) -> None:
    client = make_client(monkeypatch)

    tools = client.get("/api/tools")
    assert tools.status_code == 200
    assert "system_echo" in [tool["name"] for tool in tools.json()]

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
            "api_key": "sk-test",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post(
        "/api/accounts",
        json={"name": "Account Under Test", "provider_id": provider["id"]},
    ).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Session Under Test", "llm_account_id": account["id"]},
    ).json()

    with client.websocket_connect(f"/ws/sessions/{session['id']}") as websocket:
        run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
        assert run.status_code == 200
        assert run.json()["status"] == "finished"
        events = [websocket.receive_json()["type"] for _ in range(5)]

    assert events == [
        "run_started",
        "tool_call_started",
        "tool_call_finished",
        "assistant_message",
        "run_finished",
    ]
    messages = client.get(f"/api/sessions/{session['id']}/messages").json()
    assert [message["message_type"] for message in messages] == [
        "user",
        "tool_call_request",
        "assistant",
    ]


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
            "api_key": "sk-test",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post(
        "/api/accounts",
        json={"name": "Account Under Test", "provider_id": provider["id"]},
    ).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Session Under Test", "llm_account_id": account["id"]},
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
