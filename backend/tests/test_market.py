from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.market.akshare_provider import AKShareMarketProvider
from app.market.normalizer import normalize_history_rows, normalize_spot_rows
from app.storage.duckdb import MarketDuckDBStore
from app.tools.executor import ToolExecutor


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeMarketProvider:
    def __init__(self) -> None:
        self.history_calls = 0
        self.quote_calls = 0

    async def history(self, symbol, start, end, interval="daily", adjust=""):
        self.history_calls += 1
        return normalize_history_rows(
            FakeFrame(
                [
                    {
                        "日期": "2026-04-27",
                        "开盘": 10.0,
                        "最高": 11.0,
                        "最低": 9.5,
                        "收盘": 10.5,
                        "成交量": 1000,
                        "成交额": 10500,
                    }
                ]
            ),
            symbol=symbol,
            interval=interval,
            adjust=adjust,
            name="浦发银行",
            fetch_time="2026-04-27T08:00:00+00:00",
        )

    async def quote(self, symbol):
        self.quote_calls += 1
        return normalize_spot_rows(
            FakeFrame(
                [
                    {
                        "代码": symbol,
                        "名称": "浦发银行",
                        "最新价": 10.8,
                        "今开": 10.1,
                        "最高": 10.9,
                        "最低": 10.0,
                        "昨收": 10.2,
                        "成交量": 2000,
                        "成交额": 21600,
                    }
                ]
            ),
            fetch_time="2026-04-27T09:35:00+00:00",
        )[0]


class BlockingFakeAKShare:
    def __init__(self, release_event: threading.Event) -> None:
        self.release_event = release_event
        self.timed_out = False

    def stock_zh_a_hist(self, **kwargs):
        if not self.release_event.wait(timeout=0.2):
            self.timed_out = True
        return FakeFrame(
            [
                {
                    "日期": "2026-04-27",
                    "开盘": 10.0,
                    "最高": 11.0,
                    "最低": 9.5,
                    "收盘": 10.5,
                    "成交量": 1000,
                    "成交额": 10500,
                }
            ]
        )


def _test_dir() -> Path:
    path = Path("pytemp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_client(monkeypatch):
    path = _test_dir()
    monkeypatch.setenv("AUTOSTOCK_SQLITE_PATH", str(path / "app.db"))
    monkeypatch.setenv("AUTOSTOCK_MARKET_DUCKDB_PATH", str(path / "market.duckdb"))
    monkeypatch.setenv("AUTOSTOCK_FRONTEND_DIST_PATH", str(path / "frontend_dist"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    provider = FakeMarketProvider()
    client.app.state.market_provider = provider
    from app.tools.registry import create_default_registry

    client.app.state.tool_registry = create_default_registry(
        market_store=client.app.state.market_store,
        market_provider=provider,
    )
    return client, provider


def test_duckdb_insert_skip_and_conflict() -> None:
    store = MarketDuckDBStore(str(_test_dir() / "market.duckdb"))
    store.initialize()
    bars = normalize_history_rows(
        [{"日期": "2026-04-27", "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5}],
        symbol="600000",
        interval="daily",
        adjust="",
        fetch_time="2026-04-27T08:00:00+00:00",
    )

    assert store.insert_bars(bars) == {"inserted": 1, "skipped": 0, "conflicted": 0}
    assert store.insert_bars(bars) == {"inserted": 0, "skipped": 1, "conflicted": 0}

    changed = [{**bars[0], "close": 10.6, "raw_hash": "different"}]
    assert store.insert_bars(changed) == {"inserted": 0, "skipped": 0, "conflicted": 1}
    conflicts = store.list_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "open"


def test_normalizers_accept_chinese_columns() -> None:
    bars = normalize_history_rows(
        FakeFrame([{"日期": "2026-04-27", "开盘": "10", "最高": "11", "最低": "9", "收盘": "10.5"}]),
        symbol="1",
        interval="daily",
        adjust="qfq",
        fetch_time="2026-04-27T08:00:00+00:00",
    )
    assert bars[0]["symbol"] == "000001"
    assert bars[0]["open"] == 10.0
    assert bars[0]["adjust"] == "qfq"

    quotes = normalize_spot_rows(
        FakeFrame([{"代码": "600000", "名称": "浦发银行", "最新价": "10.8"}]),
        fetch_time="2026-04-27T09:35:00+00:00",
    )
    assert quotes[0]["symbol"] == "600000"
    assert quotes[0]["name"] == "浦发银行"
    assert quotes[0]["price"] == 10.8


def test_akshare_provider_does_not_block_event_loop(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    release_event = threading.Event()
    fake_ak = BlockingFakeAKShare(release_event)
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    async def release_soon() -> None:
        await asyncio.sleep(0.01)
        release_event.set()

    async def run() -> list[dict[str, object]]:
        started = time.perf_counter()
        history, _ = await asyncio.gather(
            provider.history("600000", "2026-04-27", "2026-04-27"),
            release_soon(),
        )
        assert time.perf_counter() - started < 0.15
        return history

    history = asyncio.run(run())

    assert fake_ak.timed_out is False
    assert history[0]["symbol"] == "600000"


def test_fetch_history_api_and_cache_hit(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    payload = {"symbol": "600000", "start": "2026-04-27", "end": "2026-04-27"}

    fetched = client.post("/api/data/fetch-history", json=payload)
    assert fetched.status_code == 200
    assert fetched.json()["inserted"] == 1

    history = client.get("/api/market/history", params=payload)
    assert history.status_code == 200
    assert history.json()["cache_hit"] is True
    assert provider.history_calls == 1


def test_history_api_fetches_when_allowed(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)

    history = client.get(
        "/api/market/history",
        params={
            "symbol": "600000",
            "start": "2026-04-27",
            "end": "2026-04-27",
            "allow_fetch_missing": "true",
        },
    )
    assert history.status_code == 200
    assert history.json()["fetch_stats"] == {"inserted": 1, "skipped": 0, "conflicted": 0}
    assert len(history.json()["bars"]) == 1
    assert provider.history_calls == 1


def test_market_tools_return_json(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    executor = ToolExecutor(client.app.state.tool_registry)

    import asyncio

    quote = asyncio.run(executor.execute("market_quote", '{"symbol": "600000"}'))
    assert quote.ok is True
    assert quote.result["symbol"] == "600000"

    history = asyncio.run(
        executor.execute(
            "market_history",
            (
                '{"symbol": "600000", "start": "2026-04-27", '
                '"end": "2026-04-27", "allow_fetch_missing": true}'
            ),
        )
    )
    assert history.ok is True
    assert len(history.result["bars"]) == 1
    assert provider.quote_calls == 1
    assert provider.history_calls == 1
