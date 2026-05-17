from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import app.simulator.replay_clock as replay_clock_module
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.scheduler.account_valuation import AccountValuationRefreshService
from app.simulator.engine import SimulatorEngine
from app.simulator.replay_clock import ReplayClockService, parse_clock_time
from app.simulator.rules import TradingRuleError
from app.simulator.valuation import PortfolioValuationService
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


def _insert_position(
    store: SQLiteStore,
    account_id: str,
    symbol: str = "000001",
    updated_at: str = "2026-04-27T09:30:00+08:00",
) -> None:
    store.execute(
        """
        INSERT INTO positions (
            id, simulator_account_id, symbol, name, quantity,
            available_quantity, avg_cost, market_value, unrealized_pnl, updated_at
        )
        VALUES (?, ?, ?, 'Ping An', 1000, 1000, 10, 10000, 0, ?)
        """,
        (uuid4().hex, account_id, symbol, updated_at),
    )
    store.execute(
        """
        UPDATE simulator_accounts
        SET cash = 90000, total_asset = 100000
        WHERE id = ?
        """,
        (account_id,),
    )


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


def test_replay_clock_advances_from_persisted_base_after_service_restart(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Persistent Replay")
    account_id = str(account["id"])
    current_now = datetime(2026, 4, 27, 2, 0, 0, tzinfo=timezone.utc)

    def fake_utc_now() -> datetime:
        return current_now

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=2)

    current_now = datetime(2026, 4, 27, 2, 0, 30, tzinfo=timezone.utc)
    advanced = ReplayClockService(store).get_clock(account_id)
    assert advanced.effective_time.startswith("2026-04-27T10:01:00")

    db_path = str(store.path)
    store.close()
    restarted_store = SQLiteStore(db_path)
    try:
        restarted_store.initialize()
        current_now = datetime(2026, 4, 27, 2, 0, 45, tzinfo=timezone.utc)
        restarted = ReplayClockService(restarted_store).get_clock(account_id)
        assert restarted.mode == "replay"
        assert restarted.speed == 2
        assert restarted.replay_time.startswith("2026-04-27T10:00:00")
        assert restarted.effective_time.startswith("2026-04-27T10:01:30")
    finally:
        restarted_store.close()


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


def test_replay_market_quote_fetches_missing_minute_bars_to_effective_time() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.quote = AsyncMock()
    provider.history = AsyncMock()
    provider.minute = AsyncMock(
        return_value=[
            {
                "symbol": "600703",
                "name": "三安光电",
                "interval": "1m",
                "datetime": "2026-05-15 15:00:00",
                "open": 13.48,
                "high": 13.5,
                "low": 13.45,
                "close": 13.49,
                "volume": 2000,
                "amount": 26980,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-15T07:00:00+00:00",
                "raw_hash": "minute-600703",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)

    quote = asyncio.run(
        executor.execute(
            "market_quote",
            '{"symbol":"600703"}',
            {"time_mode": "replay", "effective_time": "2026-05-16T01:52:21+08:00"},
        )
    )

    assert quote.ok is True
    assert quote.result["price"] == 13.49
    assert quote.result["datetime"] == "2026-05-15 15:00:00"
    assert quote.result["source"] == "replay.derived.minute"
    assert provider.quote.await_count == 0
    assert provider.minute.await_args.kwargs == {
        "symbol": "600703",
        "start": "2026-05-09 09:30:00",
        "end": "2026-05-16 01:52:21",
        "period": "1",
    }
    assert provider.history.await_count == 0


def test_replay_market_quote_falls_back_to_daily_when_minute_fetch_fails() -> None:
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.quote = AsyncMock()
    provider.minute = AsyncMock(side_effect=RuntimeError("minute unavailable"))
    provider.history = AsyncMock(
        return_value=[
            {
                "symbol": "600703",
                "name": "三安光电",
                "interval": "daily",
                "datetime": "2026-05-15",
                "open": 13.2,
                "high": 13.6,
                "low": 13.1,
                "close": 13.49,
                "volume": 500000,
                "amount": 6745000,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-15T08:00:00+00:00",
                "raw_hash": "daily-600703",
            }
        ]
    )
    registry = create_default_registry(market_store=market_store, market_provider=provider)
    executor = ToolExecutor(registry)

    quote = asyncio.run(
        executor.execute(
            "market_quote",
            '{"symbol":"600703"}',
            {"time_mode": "replay", "effective_time": "2026-05-16T01:52:21+08:00"},
        )
    )

    assert quote.ok is True
    assert quote.result["price"] == 13.49
    assert quote.result["datetime"] == "2026-05-15"
    assert quote.result["source"] == "replay.derived.daily"
    assert provider.quote.await_count == 0
    assert provider.history.await_args.kwargs == {
        "symbol": "600703",
        "start": "2026-05-06",
        "end": "2026-05-16",
        "interval": "daily",
        "adjust": "",
    }


def test_replay_account_valuation_fetches_missing_bars_to_effective_time() -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Replay Valuation", initial_cash=100000)
    account_id = str(account["id"])
    store.execute(
        """
        INSERT INTO positions (
            id, simulator_account_id, symbol, name, quantity,
            available_quantity, avg_cost, market_value, unrealized_pnl, updated_at
        )
        VALUES (?, ?, '600703', '三安光电', 1000, 1000, 13, 13000, 0, ?)
        """,
        (uuid4().hex, account_id, "2026-05-15T15:00:00+08:00"),
    )
    store.execute(
        """
        UPDATE simulator_accounts
        SET cash = 90000, total_asset = 103000
        WHERE id = ?
        """,
        (account_id,),
    )
    ReplayClockService(store).set_replay(account_id, "2026-05-16T01:52:21+08:00", speed=0)
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    provider = MagicMock()
    provider.quote = AsyncMock()
    provider.history = AsyncMock()
    provider.minute = AsyncMock(
        return_value=[
            {
                "symbol": "600703",
                "name": "三安光电",
                "interval": "1m",
                "datetime": "2026-05-15 15:00:00",
                "open": 13.48,
                "high": 13.5,
                "low": 13.45,
                "close": 13.49,
                "volume": 2000,
                "amount": 26980,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-05-15T07:00:00+00:00",
                "raw_hash": "minute-600703",
            }
        ]
    )

    result = asyncio.run(
        PortfolioValuationService(store, market_store, provider).refresh_account(account_id)
    )

    assert result["total_asset"] == 103490
    assert provider.quote.await_count == 0
    assert provider.minute.await_args.kwargs == {
        "symbol": "600703",
        "start": "2026-05-09 09:30:00",
        "end": "2026-05-16 01:52:21",
        "period": "1",
    }
    position = store.fetch_one("SELECT market_value, unrealized_pnl FROM positions WHERE simulator_account_id = ?", (account_id,))
    point = store.fetch_one("SELECT time, total_asset, symbols_json FROM account_valuation_points WHERE simulator_account_id = ?", (account_id,))
    assert position["market_value"] == 13490
    assert position["unrealized_pnl"] == 490
    assert point["time"].startswith("2026-05-16T01:52:21")
    assert point["total_asset"] == 103490
    assert point["symbols_json"] == '["600703"]'


def test_account_valuation_refresh_service_uses_account_clock_intervals() -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Clocked Valuation", initial_cash=100000)
    account_id = str(account["id"])
    _insert_position(store, account_id)
    provider = MagicMock()
    provider.quotes_batch = AsyncMock(return_value={"000001": _quote(price=10.8)})
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    service = AccountValuationRefreshService(store, market_store, provider)

    first = asyncio.run(service.refresh_due_accounts(now=0))
    skipped = asyncio.run(service.refresh_due_accounts(now=59))
    second = asyncio.run(service.refresh_due_accounts(now=60))

    assert len(first) == 1
    assert skipped == []
    assert len(second) == 1
    assert provider.quotes_batch.await_count == 2

    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=2)
    replay_clock = ReplayClockService(store).get_clock(account_id)
    assert service.interval_for_clock(replay_clock) == 60

    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=100)
    fast_clock = ReplayClockService(store).get_clock(account_id)
    assert service.interval_for_clock(fast_clock) == 60

    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=0)
    paused_clock = ReplayClockService(store).get_clock(account_id)
    assert service.interval_for_clock(paused_clock) is None
    assert asyncio.run(service.refresh_due_accounts(now=120)) == []


def test_replay_auto_valuation_uses_simulated_sixty_second_cadence(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Replay Cadence", initial_cash=100000)
    account_id = str(account["id"])
    _insert_position(store, account_id)
    current_now = datetime(2026, 4, 27, 2, 0, 0, tzinfo=timezone.utc)

    def fake_utc_now() -> datetime:
        return current_now

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=5)
    market_store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    market_store.initialize()
    market_store.insert_bars(
        [
            {
                "symbol": "000001",
                "name": "Ping An",
                "interval": "1m",
                "datetime": "2026-04-27 10:00:00",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1000,
                "amount": 10000,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-04-27T02:00:00+00:00",
                "raw_hash": "cadence-1",
            },
            {
                "symbol": "000001",
                "name": "Ping An",
                "interval": "1m",
                "datetime": "2026-04-27 10:01:00",
                "open": 11.0,
                "high": 11.0,
                "low": 11.0,
                "close": 11.0,
                "volume": 1000,
                "amount": 11000,
                "adjust": "",
                "source": "test",
                "fetch_time": "2026-04-27T02:01:00+00:00",
                "raw_hash": "cadence-2",
            },
        ]
    )
    provider = MagicMock()
    provider.quote = AsyncMock()
    provider.minute = AsyncMock()
    provider.history = AsyncMock()
    service = AccountValuationRefreshService(store, market_store, provider)

    first = asyncio.run(service.refresh_due_accounts(now=0))
    current_now = current_now + timedelta(seconds=5)
    skipped = asyncio.run(service.refresh_due_accounts(now=5))
    current_now = current_now + timedelta(seconds=7)
    second = asyncio.run(service.refresh_due_accounts(now=12))

    assert len(first) == 1
    assert skipped == []
    assert len(second) == 1
    points = store.fetch_all(
        """
        SELECT time, total_asset
        FROM account_valuation_points
        WHERE simulator_account_id = ?
        ORDER BY time ASC
        """,
        (account_id,),
    )
    assert [point["time"] for point in points] == [
        "2026-04-27T10:00:00+08:00",
        "2026-04-27T10:01:00+08:00",
    ]
    first_time = parse_clock_time(points[0]["time"])
    second_time = parse_clock_time(points[1]["time"])
    assert (second_time - first_time).total_seconds() == 60
    assert provider.quote.await_count == 0


def test_replay_auto_valuation_schedules_due_accounts_concurrently(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    slow_account = engine.create_account("Slow Replay", initial_cash=100000)
    fast_account = engine.create_account("Fast Replay", initial_cash=100000)
    slow_account_id = str(slow_account["id"])
    fast_account_id = str(fast_account["id"])
    _insert_position(store, slow_account_id)
    _insert_position(store, fast_account_id)
    current_now = datetime(2026, 4, 27, 2, 0, 0, tzinfo=timezone.utc)

    def fake_utc_now() -> datetime:
        return current_now

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(slow_account_id, "2026-04-27T10:00:00+08:00", speed=1)
    ReplayClockService(store).set_replay(fast_account_id, "2026-04-27T10:00:00+08:00", speed=1)
    service = AccountValuationRefreshService(store, MagicMock(), MagicMock())

    async def scenario() -> list[dict]:
        started: list[str] = []
        both_started = asyncio.Event()
        release_slow = asyncio.Event()

        async def fake_refresh(account_id: str, source: str = "valuation", valuation_time: str | None = None) -> dict:
            started.append(account_id)
            if len(started) == 2:
                both_started.set()
            if account_id == slow_account_id:
                await release_slow.wait()
            return {
                "account_id": account_id,
                "symbols": ["000001"],
                "total_asset": 100000,
                "market_value": 10000,
                "unrealized_pnl": 0,
                "valuation_point": {"time": valuation_time},
            }

        service.valuation_service.refresh_account = fake_refresh
        task = asyncio.create_task(service.refresh_due_accounts(now=0))
        await asyncio.wait_for(both_started.wait(), timeout=1)
        assert set(started) == {slow_account_id, fast_account_id}
        release_slow.set()
        return await task

    results = asyncio.run(scenario())
    assert {result["account_id"] for result in results} == {slow_account_id, fast_account_id}


def test_replay_auto_valuation_does_not_repeat_stale_due_after_slow_refresh(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Stale Due Replay", initial_cash=100000)
    account_id = str(account["id"])
    _insert_position(store, account_id)
    current_now = [datetime(2026, 4, 27, 2, 0, 0, tzinfo=timezone.utc)]

    def fake_utc_now() -> datetime:
        return current_now[0]

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=5)
    service = AccountValuationRefreshService(store, MagicMock(), MagicMock())

    async def scenario() -> tuple[list[dict], list[dict], list[str | None]]:
        started = asyncio.Event()
        release = asyncio.Event()
        valuation_times: list[str | None] = []

        async def fake_refresh(account_id: str, source: str = "valuation", valuation_time: str | None = None) -> dict:
            valuation_times.append(valuation_time)
            started.set()
            await release.wait()
            return {
                "symbols": ["000001"],
                "total_asset": 100000,
                "market_value": 10000,
                "unrealized_pnl": 0,
                "valuation_point": {"time": valuation_time},
            }

        service.valuation_service.refresh_account = fake_refresh
        first_task = asyncio.create_task(service.refresh_due_accounts(now=0))
        await asyncio.wait_for(started.wait(), timeout=1)
        current_now[0] = current_now[0] + timedelta(seconds=1)
        release.set()
        first = await first_task
        skipped = await service.refresh_due_accounts(now=1)
        return first, skipped, valuation_times

    first, skipped, valuation_times = asyncio.run(scenario())

    assert len(first) == 1
    assert skipped == []
    assert valuation_times == ["2026-04-27T10:00:00+08:00"]


def test_replay_auto_valuation_limits_catch_up_points(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Replay Catchup", initial_cash=100000)
    account_id = str(account["id"])
    _insert_position(store, account_id)
    current_now = datetime(2026, 4, 27, 2, 10, 0, tzinfo=timezone.utc)

    def fake_utc_now() -> datetime:
        return current_now

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:10:00+08:00", speed=1)
    store.execute(
        """
        INSERT INTO account_valuation_points (
            id, simulator_account_id, time, cash, market_value,
            unrealized_pnl, total_asset, source, symbols_json
        )
        VALUES (?, ?, '2026-04-27T10:00:00+08:00', 90000, 10000, 0, 100000, 'valuation', '["000001"]')
        """,
        (uuid4().hex, account_id),
    )
    service = AccountValuationRefreshService(store, MagicMock(), MagicMock())
    valuation_times: list[str | None] = []

    async def fake_refresh(account_id: str, source: str = "valuation", valuation_time: str | None = None) -> dict:
        valuation_times.append(valuation_time)
        return {
            "symbols": ["000001"],
            "total_asset": 100000,
            "market_value": 10000,
            "unrealized_pnl": 0,
            "valuation_point": {"time": valuation_time},
        }

    service.valuation_service.refresh_account = fake_refresh
    results = asyncio.run(service.refresh_due_accounts(now=0))

    assert len(results) == 2
    assert valuation_times == [
        "2026-04-27T10:01:00+08:00",
        "2026-04-27T10:02:00+08:00",
    ]


def test_replay_auto_valuation_ignores_future_points_after_rewind(monkeypatch) -> None:
    store = _sqlite_store()
    engine = _engine(store)
    account = engine.create_account("Replay Rewind", initial_cash=100000)
    account_id = str(account["id"])
    _insert_position(store, account_id)
    current_now = datetime(2026, 4, 27, 2, 0, 0, tzinfo=timezone.utc)

    def fake_utc_now() -> datetime:
        return current_now

    monkeypatch.setattr(replay_clock_module, "utc_now", fake_utc_now)
    ReplayClockService(store).set_replay(account_id, "2026-04-27T10:00:00+08:00", speed=1)
    store.execute(
        """
        INSERT INTO account_valuation_points (
            id, simulator_account_id, time, cash, market_value,
            unrealized_pnl, total_asset, source, symbols_json
        )
        VALUES (?, ?, '2026-04-27T10:10:00+08:00', 90000, 10000, 0, 100000, 'valuation', '["000001"]')
        """,
        (uuid4().hex, account_id),
    )
    service = AccountValuationRefreshService(store, MagicMock(), MagicMock())
    valuation_times: list[str | None] = []

    async def fake_refresh(account_id: str, source: str = "valuation", valuation_time: str | None = None) -> dict:
        valuation_times.append(valuation_time)
        return {
            "symbols": ["000001"],
            "total_asset": 100000,
            "market_value": 10000,
            "unrealized_pnl": 0,
            "valuation_point": {"time": valuation_time},
        }

    service.valuation_service.refresh_account = fake_refresh
    results = asyncio.run(service.refresh_due_accounts(now=0))

    assert len(results) == 1
    assert valuation_times == ["2026-04-27T10:00:00+08:00"]


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
