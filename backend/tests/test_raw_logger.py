from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.base import ChatMessage, LLMProviderConfig
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.raw_logger import write_raw_llm_log
from app.market.stock_data_logger import write_stock_data_api_log
from app.sessions.runtime import SessionRunManager
from test_mvp import make_client


def _config() -> LLMProviderConfig:
    return LLMProviderConfig(
        provider_type="openai_compatible",
        name="Raw Provider",
        base_url="https://llm.example.test/v1",
        api_key="sk-raw-secret",
        model="raw-model",
    )


def _context() -> dict[str, Any]:
    return {
        "session_id": "session-under-test",
        "run_id": "run-under-test",
        "call_index": 7,
        "round_index": 3,
        "provider_type": "openai_compatible",
        "provider_name": "Raw Provider",
        "provider_id": "provider-under-test",
        "model": "raw-model",
        "session_created_at": "2026-05-15T12:34:56+00:00",
    }


def _read_jsonl(log_dir: str | Path) -> list[dict[str, Any]]:
    paths = sorted((Path(log_dir) / "llm").glob("*.jsonl"))
    assert paths
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return rows


def _read_stock_data_log(log_root: str | Path) -> list[dict[str, Any]]:
    paths = sorted((Path(log_root) / "stock_data_api").glob("*.log"))
    assert paths
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return rows


def test_raw_logger_creates_jsonl_and_keeps_api_key(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    path = write_raw_llm_log(
        context=_context(),
        direction="outbound",
        event="request",
        payload={"provider_config": {"api_key": "sk-raw-secret"}},
    )

    assert path is not None
    assert path.parent == log_dir / "llm"
    assert path.name == "session-under-test-2026-05-15--12-34-56.jsonl"
    rows = _read_jsonl(log_dir)
    assert rows[0]["session_id"] == "session-under-test"
    assert rows[0]["session_created_at"] == "2026-05-15T12:34:56+00:00"
    assert rows[0]["call_index"] == 7
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["event"] == "request"
    assert rows[0]["payload"]["provider_config"]["api_key"] == "sk-raw-secret"


def test_raw_logger_splits_logs_by_session(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    first_context = {**_context(), "session_id": "session-one"}
    second_context = {**_context(), "session_id": "session-two"}

    first_path = write_raw_llm_log(
        context=first_context,
        direction="outbound",
        event="request",
        payload={"session": "one"},
    )
    second_path = write_raw_llm_log(
        context=second_context,
        direction="outbound",
        event="request",
        payload={"session": "two"},
    )

    assert first_path is not None
    assert second_path is not None
    assert first_path != second_path
    assert first_path.name == "session-one-2026-05-15--12-34-56.jsonl"
    assert second_path.name == "session-two-2026-05-15--12-34-56.jsonl"
    assert [path.name for path in sorted((log_dir / "llm").glob("*.jsonl"))] == [
        "session-one-2026-05-15--12-34-56.jsonl",
        "session-two-2026-05-15--12-34-56.jsonl",
    ]


def test_raw_logger_appends_same_session_to_one_file(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    first_path = write_raw_llm_log(
        context=_context(),
        direction="outbound",
        event="request",
        payload={"step": 1},
    )
    second_path = write_raw_llm_log(
        context=_context(),
        direction="inbound",
        event="response",
        payload={"step": 2},
    )

    assert first_path == second_path
    assert first_path is not None
    rows = [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["request", "response"]
    assert [row["payload"]["step"] for row in rows] == [1, 2]


def test_stock_data_logger_writes_daily_log_jsonl(monkeypatch, tmp_path) -> None:
    log_root = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_STOCK_DATA_API_LOG_ROOT", str(log_root))

    path = write_stock_data_api_log(
        "api.market.quote",
        {"symbol": "600000", "rows": 1},
        ok=True,
    )

    assert path is not None
    assert path.parent == log_root / "stock_data_api"
    assert path.name == f"{datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()}.log"
    rows = _read_stock_data_log(log_root)
    assert rows == [
        {
            "timestamp": rows[0]["timestamp"],
            "event": "api.market.quote",
            "ok": True,
            "payload": {"symbol": "600000", "rows": 1},
            "error": None,
        }
    ]


def test_stock_data_logger_captures_error_and_swallows_write_failure(monkeypatch, tmp_path) -> None:
    log_root = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_STOCK_DATA_API_LOG_ROOT", str(log_root))

    path = write_stock_data_api_log(
        "akshare.quote",
        {"symbol": "600000"},
        ok=False,
        error=RuntimeError("provider failed"),
    )

    assert path is not None
    rows = _read_stock_data_log(log_root)
    assert rows[0]["ok"] is False
    assert rows[0]["error"] == {"type": "RuntimeError", "message": "provider failed"}

    blocked_root = tmp_path / "not-a-directory"
    blocked_root.write_text("block mkdir", encoding="utf-8")
    monkeypatch.setenv("AUTOSTOCK_STOCK_DATA_API_LOG_ROOT", str(blocked_root))

    assert write_stock_data_api_log("api.market.quote", {"symbol": "600000"}) is None


def test_openai_compatible_chat_logs_request_and_response(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    class FakeResponse:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content="hello",
                    tool_calls=[],
                )
            )
        ]

        def model_dump(self, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {
                "id": "response-under-test",
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeCompletions:
        async def create(self, **request):
            return FakeResponse()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))

    response = asyncio.run(
        OpenAICompatibleProvider().chat(
            _config(),
            [ChatMessage(role="user", content="ping")],
            [],
            log_context=_context(),
        )
    )

    assert response.content == "hello"
    rows = _read_jsonl(log_dir)
    assert [row["event"] for row in rows] == ["request", "response"]
    assert rows[0]["payload"]["provider_config"]["api_key"] == "sk-raw-secret"
    assert rows[0]["payload"]["request"]["messages"][0]["content"] == "ping"
    assert rows[1]["payload"]["id"] == "response-under-test"


def test_openai_compatible_stream_logs_single_aggregated_response(
    monkeypatch, tmp_path
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    class FakeChunk:
        def __init__(self, raw: dict[str, Any]) -> None:
            self.raw = raw

        def model_dump(self, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return self.raw

    class SuccessfulStream:
        async def __aiter__(self):
            yield FakeChunk({"choices": [{"delta": {"reasoning_content": "think "}}]})
            yield FakeChunk({"choices": [{"delta": {"content": "Hel"}}]})
            yield FakeChunk(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-under-test",
                                        "function": {
                                            "name": "system_echo",
                                            "arguments": '{"text"',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
            yield FakeChunk(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "lo",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": ': "hi"}'},
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
            yield FakeChunk(
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                }
            )

    class FakeCompletions:
        async def create(self, **request):
            assert request["stream"] is True
            return SuccessfulStream()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))

    async def collect() -> list[dict[str, Any]]:
        chunks = []
        async for chunk in OpenAICompatibleProvider().chat_stream(
            _config(),
            [ChatMessage(role="user", content="ping")],
            [],
            log_context=_context(),
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())

    assert len(chunks) == 5
    rows = _read_jsonl(log_dir)
    assert [row["event"] for row in rows] == ["request", "stream_response"]
    assert rows[1]["payload"] == {
        "content": "Hello",
        "reasoning_content": "think ",
        "tool_calls": [
            {
                "index": 0,
                "id": "call-under-test",
                "name": "system_echo",
                "arguments": '{"text": "hi"}',
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        "partial": False,
    }


def test_openai_compatible_stream_logs_partial_response_and_stream_error(
    monkeypatch, tmp_path
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1")
    monkeypatch.setenv("AUTOSTOCK_LLM_RAW_LOG_DIR", str(log_dir))

    class FakeChunk:
        def __init__(self, content: str) -> None:
            self.content = content

        def model_dump(self, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"choices": [{"delta": {"content": self.content}}]}

    class FailingStream:
        async def __aiter__(self):
            yield FakeChunk("A")
            raise RuntimeError("stream dropped")

    class FakeCompletions:
        async def create(self, **request):
            assert request["stream"] is True
            return FailingStream()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))

    async def collect() -> list[dict[str, Any]]:
        chunks = []
        async for chunk in OpenAICompatibleProvider().chat_stream(
            _config(),
            [ChatMessage(role="user", content="ping")],
            [],
            log_context=_context(),
        ):
            chunks.append(chunk)
        return chunks

    try:
        asyncio.run(collect())
    except RuntimeError as exc:
        assert str(exc) == "stream dropped"
    else:
        raise AssertionError("stream should fail")

    rows = _read_jsonl(log_dir)
    assert [row["event"] for row in rows] == ["request", "stream_response", "stream_error"]
    assert rows[1]["payload"]["content"] == "A"
    assert rows[1]["payload"]["partial"] is True
    assert rows[2]["payload"]["exception"]["message"] == "stream dropped"


def test_run_logs_tool_error_and_next_llm_request(monkeypatch) -> None:
    client = make_client(monkeypatch)
    app = client.app

    class ToolErrorThenProviderError:
        def __init__(self) -> None:
            self.calls = 0

        async def chat_stream(self, config, messages, tools, log_context=None):
            self.calls += 1
            write_raw_llm_log(
                context=log_context,
                direction="outbound",
                event="request",
                payload={"message_roles": [message.role for message in messages]},
            )
            if self.calls == 1:
                yield {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "tool-call-under-test",
                                        "function": {"name": "system_echo", "arguments": "{"},
                                    }
                                ]
                            }
                        }
                    ]
                }
                return
            raise RuntimeError("provider failed after tool error")

    provider = ToolErrorThenProviderError()
    app.state.run_manager = SessionRunManager(
        store=app.state.store,
        tool_registry=app.state.tool_registry,
        websocket_manager=app.state.websocket_manager,
        provider_factory=lambda config: provider,
    )

    provider_row = client.post(
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
        json={
            "name": "Raw Log Session",
            "provider_id": provider_row["id"],
            "model": "deepseek-v4-flash",
        },
    ).json()

    run = client.post(f"/api/sessions/{session['id']}/run", json={"message": "hello"})
    assert run.status_code == 502
    assert "provider failed after tool error" in run.json()["detail"]

    rows = _read_jsonl(os.environ["AUTOSTOCK_LLM_RAW_LOG_DIR"])
    events = [(row["call_index"], row["direction"], row["event"], row["payload"]) for row in rows]
    assert [event[:3] for event in events] == [
        (1, "outbound", "request"),
        (1, "internal", "tool_result"),
        (2, "outbound", "request"),
    ]
    assert events[1][3]["tool_name"] == "system_echo"
    assert events[1][3]["ok"] is False
    assert "Invalid JSON arguments" in events[1][3]["error"]
    assert events[2][3]["message_roles"][-1] == "tool"
