from __future__ import annotations

from app.llm.base import ChatResponse, ToolCall
from app.sessions.runtime import SessionRunManager
from app.usage import normalize_usage
from test_mvp import make_client


def test_usage_normalizer_handles_provider_variants() -> None:
    openai_usage = normalize_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 7,
            "total_tokens": 17,
            "completion_tokens_details": {"reasoning_tokens": 3},
        }
    )
    assert openai_usage.prompt_tokens == 10
    assert openai_usage.completion_tokens == 7
    assert openai_usage.thinking_tokens == 3
    assert openai_usage.total_tokens == 17

    deepseek_usage = normalize_usage(
        {
            "input_tokens": 12,
            "output_tokens": 8,
            "output_tokens_details": {"thinking_tokens": 4},
        }
    )
    assert deepseek_usage.prompt_tokens == 12
    assert deepseek_usage.completion_tokens == 8
    assert deepseek_usage.thinking_tokens == 4
    assert deepseek_usage.total_tokens == 20


def test_session_run_records_token_usage_and_cap_warning(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class UsageProvider:
        async def chat(self, config, messages, tools):
            return ChatResponse(content="ok")

        async def chat_stream(self, config, messages, tools):
            yield {"choices": [{"delta": {"content": "ok"}}]}
            yield {
                "choices": [],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                    "total_tokens": 16,
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            }

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: UsageProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Usage Provider",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
            "run_token_limit": 10,
        },
    ).json()
    session = client.post(
        "/api/sessions",
        json={
            "name": "Usage Session",
            "provider_id": provider["id"],
            "model": "deepseek-v4-flash",
        },
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
    assert run.status_code == 200
    assert run.json()["usage"]["total_tokens"] == 16
    assert run.json()["usage"]["cap_exceeded"] is True

    session_usage = client.get(f"/api/sessions/{session['id']}/usage")
    assert session_usage.status_code == 200
    assert session_usage.json()["summary"]["total_tokens"] == 16
    assert session_usage.json()["summary"]["cap_exceeded_count"] == 1

    provider_usage = client.get(f"/api/providers/{provider['id']}/usage")
    assert provider_usage.status_code == 200
    assert provider_usage.json()["total_tokens"] == 16
    assert provider_usage.json()["llm_calls"] == 1


def test_auto_title_llm_call_is_recorded_as_session_usage(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class TitleUsageProvider:
        async def chat(self, config, messages, tools):
            return ChatResponse(
                content="自动标题",
                usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            )

        async def chat_stream(self, config, messages, tools):
            yield {"choices": [{"delta": {"content": "ok"}}]}
            yield {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}}

    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: TitleUsageProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Title Usage Provider",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    session = client.post(
        "/api/sessions",
        json={
            "name": "新会话",
            "provider_id": provider["id"],
            "model": "deepseek-v4-flash",
        },
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
    assert run.status_code == 200

    usage = client.get(f"/api/sessions/{session['id']}/usage").json()
    assert usage["summary"]["llm_calls"] == 2
    assert usage["summary"]["total_tokens"] == 16
    assert usage["summary"]["avg_latency_ms"] >= 0

    title_record = app.state.store.fetch_one(
        "SELECT purpose, run_id, total_tokens FROM llm_usage_records WHERE purpose = ?",
        ("session_title",),
    )
    assert title_record == {"purpose": "session_title", "run_id": None, "total_tokens": 5}


def test_tool_order_trades_carry_run_tool_and_usage_context(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class OrderProvider:
        async def chat(self, config, messages, tools):
            if messages and messages[-1].role == "tool":
                return ChatResponse(content="done")
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="tool-call-order-buy",
                        name="order_buy",
                        arguments='{"symbol":"000001","quantity":100,"trade_reason":"token归因测试"}',
                    ),
                    ToolCall(
                        id="tool-call-order-buy-2",
                        name="order_buy",
                        arguments='{"symbol":"000001","quantity":100,"trade_reason":"token归因测试2"}',
                    ),
                ],
            )

        async def chat_stream(self, config, messages, tools):
            result = await self.chat(config, messages, tools)
            if result.tool_calls:
                yield {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": index,
                                        "id": tc.id,
                                        "function": {"name": tc.name, "arguments": tc.arguments},
                                    }
                                    for index, tc in enumerate(result.tool_calls)
                                ]
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24},
                }
            else:
                yield {
                    "choices": [{"delta": {"content": result.content}}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 6, "total_tokens": 36},
                }

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
        provider_factory=lambda config: OrderProvider(),
    )

    provider = client.post(
        "/api/providers",
        json={
            "provider_type": "deepseek",
            "name": "Order Usage Provider",
            "api_key": "sk-test-123456",
            "model": "deepseek-v4-flash",
        },
    ).json()
    account = client.post("/api/simulator/accounts", json={"name": "Usage Account"}).json()
    session = client.post(
        "/api/sessions",
        json={
            "name": "Usage Order Session",
            "simulator_account_id": account["id"],
            "provider_id": provider["id"],
            "model": "deepseek-v4-flash",
        },
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "buy"})
    assert run.status_code == 200

    trades = client.get("/api/view/trades", params={"account_id": account["id"]})
    assert trades.status_code == 200
    trade = trades.json()["trades"][0]
    assert trade["run_id"] == run.json()["run_id"]
    assert trade["tool_call_id"]
    assert trade["run_total_tokens"] == 60
    assert trade["run_trade_count"] == 2
    assert trade["attributed_total_tokens"] == 30
    assert trade["attributed_prompt_tokens"] == 25
