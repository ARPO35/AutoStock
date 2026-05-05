from __future__ import annotations

import json
from uuid import uuid4

from app.llm.base import ChatResponse, ToolCall
from app.sessions.runtime import SessionRunManager
from app.tools.executor import ToolExecutor

from test_mvp import make_client


def test_tavily_config_roundtrip_and_usage_empty(monkeypatch) -> None:
    client = make_client(monkeypatch)

    initial = client.get("/api/tavily/config")
    assert initial.status_code == 200
    assert initial.json()["configured"] is False

    updated = client.put(
        "/api/tavily/config",
        json={
            "api_key": "tvly-test-123456789",
            "default_search_depth": "advanced",
            "default_topic": "news",
            "default_max_results": 7,
            "cache_ttl_seconds": 60,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["configured"] is True
    assert body["api_key_masked"].startswith("tvly-t")
    assert "123456789" not in body["api_key_masked"]
    assert body["default_search_depth"] == "advanced"
    assert body["default_topic"] == "news"
    assert body["default_max_results"] == 7
    assert body["cache_ttl_seconds"] == 60

    usage = client.get("/api/tavily/usage")
    assert usage.status_code == 200
    assert usage.json()["total_calls"] == 0


def test_tavily_search_tool_caches_and_records_usage(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app
    client.put(
        "/api/tavily/config",
        json={
            "api_key": "tvly-test-123456789",
            "default_search_depth": "basic",
            "default_topic": "finance",
            "default_max_results": 5,
            "cache_ttl_seconds": 300,
        },
    )
    calls: list[dict[str, object]] = []

    async def fake_client_call(method, api_key, request):
        calls.append({"method": method, "api_key": api_key, "request": request})
        return {
            "query": request["query"],
            "results": [
                {
                    "title": "平安银行公告",
                    "url": "https://example.com/news",
                    "content": "公告摘要",
                    "score": 0.91,
                }
            ],
            "response_time": 0.12,
            "request_id": "req-test",
        }

    monkeypatch.setattr(app.state.tavily_service, "_client_call", fake_client_call)
    executor = ToolExecutor(app.state.tool_registry)

    first = _run_async(
        executor.execute(
            "tavily_search",
            json.dumps({"query": "平安银行 最新公告"}, ensure_ascii=False),
            runtime_context={
                "session_id": "session-under-test",
                "run_id": "run-under-test",
                "tool_call_id": "tool-call-under-test",
            },
        )
    )
    assert first.ok is True
    assert first.result["kind"] == "tavily_search"
    assert first.result["cache_hit"] is False
    assert first.result["credits_estimated"] == 1.0
    assert first.result["result_count"] == 1

    second = _run_async(
        executor.execute(
            "tavily_search",
            json.dumps({"query": "平安银行 最新公告"}, ensure_ascii=False),
            runtime_context={
                "session_id": "session-under-test",
                "run_id": "run-under-test",
                "tool_call_id": "tool-call-under-test-2",
            },
        )
    )
    assert second.ok is True
    assert second.result["cache_hit"] is True
    assert second.result["credits_estimated"] == 0.0
    assert len(calls) == 1

    usage = client.get("/api/tavily/usage").json()
    assert usage["total_calls"] == 2
    assert usage["cache_hits"] == 1
    assert usage["credits_estimated"] == 1.0
    assert usage["recent"][0]["tool_call_id"] == "tool-call-under-test-2"


def test_session_run_can_chain_tavily_search_and_extract(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app
    client.put(
        "/api/tavily/config",
        json={
            "api_key": "tvly-test-123456789",
            "default_search_depth": "basic",
            "default_topic": "finance",
            "default_max_results": 5,
            "cache_ttl_seconds": 0,
        },
    )

    async def fake_client_call(method, api_key, request):
        if method == "search":
            return {
                "query": request["query"],
                "results": [
                    {
                        "title": "招商银行新闻",
                        "url": "https://example.com/cmb",
                        "content": "新闻摘要",
                    }
                ],
                "response_time": 0.1,
                "request_id": uuid4().hex,
            }
        return {
            "results": [
                {
                    "url": request["urls"][0],
                    "raw_content": "招商银行新闻正文",
                }
            ],
            "failed_results": [],
            "response_time": 0.1,
            "request_id": uuid4().hex,
        }

    class ChainTavilyProvider:
        async def chat(self, config, messages, tools):
            return ChatResponse(content="unused")

        async def chat_stream(self, config, messages, tools):
            if not messages or messages[-1].role != "tool":
                yield _tool_delta("provider-search", "tavily_search", '{"query":"招商银行 新闻"}')
                return
            payload = json.loads(messages[-1].content)
            result = payload["result"]
            if result["operation"] == "search":
                url = result["results"][0]["url"]
                yield _tool_delta("provider-extract", "tavily_extract", json.dumps({"urls": [url]}))
                return
            yield {"choices": [{"delta": {"content": "done"}}]}

    monkeypatch.setattr(app.state.tavily_service, "_client_call", fake_client_call)
    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: ChainTavilyProvider(),
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
    session = client.post(
        "/api/sessions",
        json={"name": "Tavily Chain", "provider_id": provider["id"], "model": "deepseek-v4-flash"},
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "搜索并抽取新闻"})
    assert run.status_code == 200
    assert run.json()["status"] == "finished"

    timeline = client.get(f"/api/sessions/{session['id']}/timeline").json()
    tool_names = [item["tool_name"] for item in timeline if item["type"] == "tool_call"]
    assert tool_names == ["tavily_search", "tavily_extract"]
    usage = client.get("/api/tavily/usage").json()
    assert usage["total_calls"] == 2
    assert usage["credits_estimated"] == 2.0


def _tool_delta(call_id: str, name: str, arguments: str) -> dict[str, object]:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": call_id,
                            "function": {"name": name, "arguments": arguments},
                        }
                    ]
                }
            }
        ]
    }


def _run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
