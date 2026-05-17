from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from app.llm.base import ToolCall
from app.sessions.ledger import RunLedger
from app.sessions.prompt_rendering import PromptRenderer
from app.sessions.provider_turn import ProviderTurnAssembler
from app.sessions.runtime_clock import utc_now
from app.sessions.tool_turn import ToolTurnExecutor
from app.storage.sqlite import SQLiteStore
from app.tools.executor import ToolExecutionResult
from app.tools.registry import ToolRegistry, ToolSpec


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(str(tmp_path / "app.db"))
    store.initialize()
    return store


def _create_session(store: SQLiteStore) -> str:
    session_id = uuid4().hex
    now = utc_now()
    store.execute(
        """
        INSERT INTO chat_sessions (id, name, status, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?)
        """,
        (session_id, "Session Under Test", now, now),
    )
    return session_id


def _insert_prompt_entry(
    store: SQLiteStore,
    *,
    role_id: str,
    ref_name: str,
    content: str,
    enabled: bool = True,
    sort_order: int = 0,
) -> None:
    now = utc_now()
    store.execute(
        """
        INSERT INTO prompt_entries (
            id, role_id, name, ref_name, content, enabled, builtin,
            sort_order, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (uuid4().hex, role_id, ref_name, ref_name, content, int(enabled), sort_order, now, now),
    )


def test_prompt_renderer_handles_refs_disabled_cycles_time_user_input_and_fallback(tmp_path) -> None:
    store = _store(tmp_path)
    now = utc_now()
    store.execute(
        "INSERT INTO prompt_roles (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("role-under-test", "Role Under Test", now, now),
    )
    _insert_prompt_entry(
        store,
        role_id="role-under-test",
        ref_name="system",
        content="Hello {Name} {Disabled} {Missing} {LoopA} {time}",
        sort_order=0,
    )
    _insert_prompt_entry(
        store,
        role_id="role-under-test",
        ref_name="UserInput",
        content="Ask: {UserInput} @ {time}",
        sort_order=1,
    )
    _insert_prompt_entry(store, role_id="role-under-test", ref_name="Name", content="Analyst")
    _insert_prompt_entry(
        store,
        role_id="role-under-test",
        ref_name="Disabled",
        content="hidden",
        enabled=False,
    )
    _insert_prompt_entry(store, role_id="role-under-test", ref_name="LoopA", content="{LoopB}")
    _insert_prompt_entry(store, role_id="role-under-test", ref_name="LoopB", content="{LoopA}")

    rendered = PromptRenderer(store).render(
        "role-under-test",
        "ping",
        render_time="2026-05-17T10:00:00+08:00",
    )

    assert rendered.system_content == "Hello Analyst  {Missing}  2026-05-17T10:00:00+08:00"
    assert rendered.user_content == "Ask: ping @ 2026-05-17T10:00:00+08:00"
    fallback = PromptRenderer(store).render(
        "missing-role",
        "hello",
        render_time="2026-05-17T11:00:00+08:00",
    )
    assert fallback.system_content is None
    assert fallback.user_content == "hello2026-05-17T11:00:00+08:00"


def test_provider_turn_assembler_aggregates_stream_without_websocket() -> None:
    async def stream():
        yield {"choices": [{"delta": {"reasoning_content": "think "}}]}
        yield {"choices": [{"delta": {"content": "Hel"}}]}
        yield {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "provider-call",
                                "function": {"name": "system_echo", "arguments": '{"message"'},
                            }
                        ]
                    }
                }
            ]
        }
        yield {
            "choices": [
                {
                    "delta": {
                        "content": "lo",
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": ':"ping"}'}}
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }

    async def run():
        deltas: list[tuple[str, str]] = []

        async def on_delta(kind: str, token: str) -> None:
            deltas.append((kind, token))

        result = await ProviderTurnAssembler().assemble(stream(), on_delta=on_delta)
        return result, deltas

    result, deltas = asyncio.run(run())

    assert result.content == "Hello"
    assert result.reasoning_content == "think "
    assert result.usage == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    assert result.tool_calls == [
        ToolCall(id="provider-call", name="system_echo", arguments='{"message":"ping"}')
    ]
    assert deltas == [("reasoning", "think "), ("content", "Hel"), ("content", "lo")]


def test_run_ledger_persists_run_messages_tool_results_and_usage(tmp_path) -> None:
    store = _store(tmp_path)
    session_id = _create_session(store)
    ledger = RunLedger(store)
    run_id = uuid4().hex

    ledger.create_run(
        run_id=run_id,
        session_id=session_id,
        provider_id="provider-under-test",
        model="model-under-test",
    )
    assistant = ledger.create_message(
        session_id=session_id,
        role="assistant",
        content="answer",
        message_type="assistant",
        reasoning_content="reason",
    )
    tool_call_id = ledger.create_tool_call(
        run_id=run_id,
        session_id=session_id,
        message_id=str(assistant["id"]),
        provider_call=ToolCall(id="provider-call", name="system_echo", arguments='{"message":"ping"}'),
    )
    ledger.save_tool_result(
        run_id=run_id,
        session_id=session_id,
        tool_call_id=tool_call_id,
        result=ToolExecutionResult(
            tool_name="system_echo",
            arguments={"message": "ping"},
            result={"echo": "ping"},
        ),
    )
    usage = ledger.record_provider_usage(
        usage_records=[],
        session_id=session_id,
        run_id=run_id,
        provider_id="provider-under-test",
        provider_type="deepseek",
        provider_name="Provider Under Test",
        model="model-under-test",
        usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        latency_ms=12.0,
        call_index=1,
        token_cap=100,
    )
    ledger.finish_run(run_id, status="finished", final_message_id=str(assistant["id"]), token_usage=usage)

    run = store.fetch_one("SELECT status, final_message_id, token_usage FROM chat_runs WHERE id = ?", (run_id,))
    message = store.fetch_one("SELECT content, reasoning_content FROM chat_messages WHERE id = ?", (assistant["id"],))
    tool_call = store.fetch_one("SELECT status, tool_name FROM chat_tool_calls WHERE id = ?", (tool_call_id,))
    tool_result = store.fetch_one("SELECT result_json FROM chat_tool_results WHERE tool_call_id = ?", (tool_call_id,))
    usage_row = store.fetch_one("SELECT total_tokens FROM llm_usage_records WHERE run_id = ?", (run_id,))

    assert run and run["status"] == "finished"
    assert run["final_message_id"] == assistant["id"]
    assert '"total_tokens": 5' in run["token_usage"]
    assert message == {"content": "answer", "reasoning_content": "reason"}
    assert tool_call == {"status": "finished", "tool_name": "system_echo"}
    assert tool_result and '"echo": "ping"' in tool_result["result_json"]
    assert usage_row == {"total_tokens": 5}


def test_tool_turn_executor_returns_results_errors_and_event_intents() -> None:
    registry = ToolRegistry()

    async def echo(arguments):
        return {"echo": arguments["message"]}

    async def order(arguments, runtime_context):
        return {
            "order_id": "order-1",
            "trade_id": "trade-1",
            "symbol": arguments["symbol"],
            "side": "buy",
        }

    async def portfolio(arguments, runtime_context):
        return {"cash": 1000}

    async def broken(arguments):
        raise RuntimeError("tool failed")

    registry.register(ToolSpec("system_echo", "Echo", "Echo", {}, echo))
    registry.register(ToolSpec("order_buy", "Buy", "Buy", {}, order))
    registry.register(ToolSpec("portfolio_state", "Portfolio", "Portfolio", {}, portfolio))
    registry.register(ToolSpec("broken_tool", "Broken", "Broken", {}, broken))
    executor = ToolTurnExecutor(registry)

    async def run():
        success = await executor.execute(
            call=ToolCall("provider-echo", "system_echo", '{"message":"ping"}'),
            runtime_context={"session_id": "session-1", "run_id": "run-1"},
            tool_call_id="tool-echo",
            run_id="run-1",
            simulator_account_id=None,
        )
        invalid_json = await executor.execute(
            call=ToolCall("provider-bad-json", "system_echo", "{bad"),
            runtime_context={"session_id": "session-1", "run_id": "run-1"},
            tool_call_id="tool-bad-json",
            run_id="run-1",
            simulator_account_id=None,
        )
        failed = await executor.execute(
            call=ToolCall("provider-fail", "broken_tool", "{}"),
            runtime_context={"session_id": "session-1", "run_id": "run-1"},
            tool_call_id="tool-fail",
            run_id="run-1",
            simulator_account_id=None,
        )
        order_result = await executor.execute(
            call=ToolCall("provider-order", "order_buy", '{"symbol":"000001"}'),
            runtime_context={"session_id": "session-1", "run_id": "run-1"},
            tool_call_id="tool-order",
            run_id="run-1",
            simulator_account_id="account-1",
        )
        portfolio_result = await executor.execute(
            call=ToolCall("provider-portfolio", "portfolio_state", "{}"),
            runtime_context={"session_id": "session-1", "run_id": "run-1"},
            tool_call_id="tool-portfolio",
            run_id="run-1",
            simulator_account_id="account-1",
        )
        return success, invalid_json, failed, order_result, portfolio_result

    success, invalid_json, failed, order_result, portfolio_result = asyncio.run(run())

    assert success.execution.ok is True
    assert success.execution.result == {"echo": "ping"}
    assert success.event_intents == []
    assert invalid_json.execution.ok is False
    assert invalid_json.execution.error and invalid_json.execution.error.startswith("Invalid JSON")
    assert failed.execution.ok is False
    assert failed.execution.error == "RuntimeError: tool failed"
    assert [intent.event_type for intent in order_result.event_intents] == [
        "order_created",
        "trade_created",
        "portfolio_updated",
    ]
    assert order_result.event_intents[-1].send_account_event is True
    assert [intent.event_type for intent in portfolio_result.event_intents] == ["portfolio_updated"]
