from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.llm.base import ChatResponse, ToolCall
from app.main import create_app
from app.sessions.runtime import SessionRunManager


def make_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("AUTOSTOCK_SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("AUTOSTOCK_FRONTEND_DIST_PATH", str(tmp_path / "frontend_dist"))
    get_settings.cache_clear()
    return TestClient(create_app())


def test_session_crud(monkeypatch, tmp_path) -> None:
    client = make_client(monkeypatch, tmp_path)

    created = client.post("/api/sessions", json={"name": "MVP Session"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    message = client.post(f"/api/sessions/{session_id}/messages", json={"content": "hello"})
    assert message.status_code == 201
    assert message.json()["content"] == "hello"

    messages = client.get(f"/api/sessions/{session_id}/messages")
    assert messages.status_code == 200
    assert [item["content"] for item in messages.json()] == ["hello"]


def test_provider_account_and_key_mask(monkeypatch, tmp_path) -> None:
    client = make_client(monkeypatch, tmp_path)

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "DeepSeek",
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
        json={"name": "Paper", "provider_id": body["id"], "initial_cash": 1000000},
    )
    assert account.status_code == 201
    assert account.json()["provider_id"] == body["id"]


def test_echo_tool(monkeypatch, tmp_path) -> None:
    client = make_client(monkeypatch, tmp_path)

    tools = client.get("/api/tools")
    assert tools.status_code == 200
    assert [tool["name"] for tool in tools.json()] == ["system_echo"]

    result = client.post("/api/tools/system_echo/test", json={"arguments": {"message": "ping"}})
    assert result.status_code == 200
    assert result.json()["ok"] is True
    assert result.json()["result"] == {"echo": "ping"}


def test_session_run_loop_and_websocket_events(monkeypatch, tmp_path) -> None:
    client = make_client(monkeypatch, tmp_path)
    app = client.app

    class FakeProvider:
        async def chat(self, config, messages, tools):
            if messages and messages[-1].role == "tool":
                return ChatResponse(content="done")
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="system_echo",
                        arguments='{"message":"ping"}',
                    )
                ],
            )

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: FakeProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "DeepSeek",
            "api_key": "sk-test",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post(
        "/api/accounts",
        json={"name": "Paper", "provider_id": provider["id"]},
    ).json()
    session = client.post(
        "/api/sessions",
        json={"name": "Trading Session", "llm_account_id": account["id"]},
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
