from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.simulator.engine import SimulatorEngine
from app.simulator.replay_clock import ReplayClockService
from app.simulator.rules import TradingRuleError
from app.storage.duckdb import MarketDuckDBStore
from app.storage.sqlite import SQLiteStore
from app.tools.executor import ToolExecutor
from app.tools.registry import create_default_registry


def _test_dir() -> Path:
    path = Path("pytemp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sqlite_store() -> SQLiteStore:
    path = os.path.join(tempfile.gettempdir(), f"test_replay_{uuid4().hex}.db")
    store = SQLiteStore(path)
    store.initialize()
    return store


def _quote(symbol="000001", price=12.5):
    return {
        "symbol": symbol,
        "name": "Ping An",
        "price": price,
        "previous_close": price,
        "open": price,
        "high": price,
        "low": price,
        "volume": 1000,
        "amount": price * 1000,
    }


def _engine(store: SQLiteStore, enforce_trading_hours: bool = False) -> SimulatorEngine:
    provider = MagicMock()
    provider.quote = AsyncMock(return_value=_quote())
    provider.quotes_batch = AsyncMock(return_value={"000001": _quote()})
    return SimulatorEngine(store, provider, enforce_trading_hours=enforce_trading_hours)


def test_replay_clock_live_pause_advance_and_restore() -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Replay Account")
    service = ReplayClockService(store)

    live = service.get_clock(str(account["id"]))
    assert live.mode == "live"
    assert live.replay_time is None

    paused = service.set_replay(str(account["id"]), "2026-04-27T10:15:00+08:00", speed=0)
    assert paused.mode == "replay"
    assert paused.speed == 0
    assert paused.effective_time.startswith("2026-04-27T10:15:00")

    moving = service.set_replay(str(account["id"]), "2026-04-27T10:15:00+08:00", speed=2)
    assert moving.mode == "replay"
    assert moving.speed == 2
    assert moving.effective_time >= "2026-04-27T10:15:00"

    restored = service.set_live(str(account["id"]))
    assert restored.mode == "live"
    assert restored.replay_time is None


def test_replay_clock_api_is_account_level(monkeypatch) -> None:
    path = _test_dir()
    monkeypatch.setenv("AUTOSTOCK_SQLITE_PATH", str(path / "app.db"))
    monkeypatch.setenv("AUTOSTOCK_MARKET_DUCKDB_PATH", str(path / "market.duckdb"))
    monkeypatch.setenv("AUTOSTOCK_FRONTEND_DIST_PATH", str(path / "frontend_dist"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    account = client.post("/api/simulator/accounts", json={"name": "Replay API"}).json()
    account_id = account["id"]

    set_clock = client.put(
        f"/api/simulator/accounts/{account_id}/replay-clock",
        json={"mode": "replay", "replay_time": "2026-04-27T10:15:00+08:00", "speed": 0},
    )
    assert set_clock.status_code == 200
    assert set_clock.json()["mode"] == "replay"
    assert set_clock.json()["speed"] == 0

    fetched = client.get(f"/api/simulator/accounts/{account_id}/replay-clock")
    assert fetched.status_code == 200
    assert fetched.json()["effective_time"].startswith("2026-04-27T10:15:00")

    live = client.post(f"/api/simulator/accounts/{account_id}/replay-clock/live")
    assert live.status_code == 200
    assert live.json()["mode"] == "live"


def test_replay_market_tools_clamp_and_do_not_fetch() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    market_store.insert_bars(
        [
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "1m",
                "datetime": "2026-04-27 09:35:00",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.2,
                "volume": 500,
                "amount": 5100,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-04-27T01:35:00+00:00",
                "raw_hash": "m1",
            },
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "1m",
                "datetime": "2026-04-27 09:40:00",
                "open": 10.2,
                "high": 10.6,
                "low": 10.1,
                "close": 10.5,
                "volume": 800,
                "amount": 8400,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-04-27T01:40:00+00:00",
                "raw_hash": "m2",
            },
        ]
    )
    provider = MagicMock()
    provider.quote = AsyncMock()
    provider.minute = AsyncMock()
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)
    context = {
        "time_mode": "replay",
        "effective_time": "2026-04-27T09:36:00+08:00",
    }

    quote = asyncio.run(executor.execute("market_quote", '{"symbol":"600000"}', context))
    assert quote.ok is True
    assert quote.result["price"] == 10.2
    assert provider.quote.await_count == 0

    minute = asyncio.run(
        executor.execute(
            "market_minute",
            '{"symbol":"600000","start":"2026-04-27 09:30:00","end":"2026-04-27 09:45:00","allow_fetch_missing":true}',
            context,
        )
    )
    assert minute.ok is True
    assert [bar["datetime"] for bar in minute.result["bars"]] == ["2026-04-27 09:35:00"]
    assert provider.minute.await_count == 0

    fetch = asyncio.run(
        executor.execute(
            "data_fetch_history",
            '{"symbol":"600000","start":"2026-04-27","end":"2026-04-27"}',
            context,
        )
    )
    assert fetch.ok is False
    assert "disabled during replay" in (fetch.error or "")


def test_replay_market_tools_fetch_missing_only_to_effective_time() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.history = AsyncMock(
        return_value=[
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "daily",
                "datetime": "2026-05-06",
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "volume": 1000,
                "amount": 10200,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-06T08:00:00+00:00",
                "raw_hash": "daily-1",
            }
        ]
    )
    provider.minute = AsyncMock(
        return_value=[
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "1m",
                "datetime": "2026-05-06 09:35:00",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.2,
                "volume": 500,
                "amount": 5100,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-06T01:35:00+00:00",
                "raw_hash": "minute-1",
            }
        ]
    )
    provider.announcement = AsyncMock(
        return_value=[
            {
                "symbol": "600000",
                "name": "SPDB",
                "title": "Replay-safe notice",
                "type": "notice",
                "published_at": "2026-05-06",
                "url": "https://example.com/notice",
                "source": "test",
                "fetch_time": "2026-05-06T08:00:00+00:00",
                "raw_hash": "ann-1",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)
    context = {
        "time_mode": "replay",
        "effective_time": "2026-05-06T19:15:35+08:00",
    }

    history = asyncio.run(
        executor.execute(
            "market_history",
            '{"symbol":"600000","start":"2026-04-01","end":"2026-12-31"}',
            context,
        )
    )
    assert history.ok is True
    assert history.result["fetch_stats"] == {"inserted": 1, "skipped": 0, "conflicted": 0}
    assert provider.history.await_args.kwargs["end"] == "2026-05-06"

    minute = asyncio.run(
        executor.execute(
            "market_minute",
            '{"symbol":"600000","start":"2026-05-06 09:30:00","end":"2026-12-31 15:00:00","period":"1","allow_fetch_missing":false}',
            context,
        )
    )
    assert minute.ok is True
    assert provider.minute.await_args.kwargs["end"] == "2026-05-06 19:15:35"

    announcement = asyncio.run(
        executor.execute(
            "market_announcement",
            '{"symbol":"600000","start":"2026-04-01","end":"2026-12-31"}',
            context,
        )
    )
    assert announcement.ok is True
    assert provider.announcement.await_args.kwargs["end"] == "2026-05-06"


def test_replay_market_history_defaults_to_180_day_lookback() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.history = AsyncMock(
        return_value=[
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "daily",
                "datetime": "2026-05-06",
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "volume": 1000,
                "amount": 10200,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-06T08:00:00+00:00",
                "raw_hash": "daily-default",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            "market_history",
            '{"symbol":"600000"}',
            {"time_mode": "replay", "effective_time": "2026-05-06T19:15:35+08:00"},
        )
    )

    assert result.ok is True
    assert provider.history.await_args.kwargs["start"] == "2025-11-07"
    assert provider.history.await_args.kwargs["end"] == "2026-05-06"


def test_replay_market_minute_defaults_to_market_open_and_effective_time() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.minute = AsyncMock(
        return_value=[
            {
                "symbol": "600000",
                "name": "SPDB",
                "interval": "1m",
                "datetime": "2026-05-06 09:35:00",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.2,
                "volume": 500,
                "amount": 5100,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-06T01:35:00+00:00",
                "raw_hash": "minute-default",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            "market_minute",
            '{"symbol":"600000"}',
            {"time_mode": "replay", "effective_time": "2026-05-06T19:15:35+08:00"},
        )
    )

    assert result.ok is True
    assert provider.minute.await_args.kwargs["start"] == "2026-05-06 09:30:00"
    assert provider.minute.await_args.kwargs["end"] == "2026-05-06 19:15:35"


def test_session_market_history_fetches_missing_without_allow_flag() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.history = AsyncMock(
        return_value=[
            {
                "symbol": "000858",
                "name": "Wuliangye",
                "interval": "daily",
                "datetime": "2026-05-06",
                "open": 128.0,
                "high": 132.0,
                "low": 127.5,
                "close": 130.0,
                "volume": 1000,
                "amount": 130000,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-06T08:00:00+00:00",
                "raw_hash": "live-session-fetch",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            "market_history",
            '{"symbol":"000858","start":"20260101","end":"20260513"}',
            {"session_id": "session-under-test", "run_id": "run-under-test"},
        )
    )

    assert result.ok is True
    assert result.result["fetch_stats"] == {"inserted": 1, "skipped": 0, "conflicted": 0}
    assert len(result.result["bars"]) == 1
    assert provider.history.await_args.kwargs["symbol"] == "000858"


def test_simulator_uses_injected_time_for_order_and_t1() -> None:
    store = _sqlite_store()
    engine = _engine(store, enforce_trading_hours=True)
    account = engine.create_account("Replay Trading")
    account_id = str(account["id"])

    buy = asyncio.run(
        engine.place_buy(
            "",
            account_id,
            "000001",
            100,
            current_time="2026-04-27T10:00:00+08:00",
            quote=_quote(),
        )
    )
    assert buy["order"]["created_at"].startswith("2026-04-27T10:00:00")

    try:
        asyncio.run(
            engine.place_sell(
                "",
                account_id,
                "000001",
                100,
                current_time="2026-04-27T14:00:00+08:00",
                quote=_quote(),
            )
        )
        assert False, "same-day sell should fail T+1"
    except TradingRuleError as exc:
        assert "T+1" in str(exc)

    sell = asyncio.run(
        engine.place_sell(
            "",
            account_id,
            "000001",
            100,
            current_time="2026-04-28T10:00:00+08:00",
            quote=_quote(),
        )
    )
    assert sell["trade"]["traded_at"].startswith("2026-04-28T10:00:00")

    try:
        asyncio.run(
            engine.place_buy(
                "",
                account_id,
                "000001",
                100,
                current_time="2026-04-28T12:00:00+08:00",
                quote=_quote(),
            )
        )
        assert False, "lunch break should fail"
    except TradingRuleError:
        pass
