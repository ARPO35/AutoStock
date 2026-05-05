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
from app.market.normalizer import normalize_announcement_rows, normalize_bid_ask_quote, normalize_history_rows, normalize_minute_rows, normalize_spot_rows
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
        self.minute_calls = 0
        self.announcement_calls = 0

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

    async def minute(self, symbol, start, end, period="1", adjust=""):
        self.minute_calls += 1
        return normalize_minute_rows(
            FakeFrame(
                [
                    {
                        "时间": "2026-04-27 09:35:00",
                        "开盘": 10.0,
                        "收盘": 10.2,
                        "最高": 10.3,
                        "最低": 9.9,
                        "成交量": 500,
                        "成交额": 5100,
                    },
                    {
                        "时间": "2026-04-27 09:40:00",
                        "开盘": 10.2,
                        "收盘": 10.5,
                        "最高": 10.6,
                        "最低": 10.1,
                        "成交量": 800,
                        "成交额": 8400,
                    },
                ]
            ),
            symbol=symbol,
            period=period,
            adjust=adjust,
            name="浦发银行",
            fetch_time="2026-04-27T08:00:00+00:00",
        )

    async def announcement(self, symbol, start, end):
        self.announcement_calls += 1
        return normalize_announcement_rows(
            FakeFrame(
                [
                    {
                        "代码": symbol,
                        "名称": "浦发银行",
                        "公告标题": "浦发银行:2026年第一季度报告",
                        "公告类型": "一季度报告全文",
                        "公告日期": "2026-04-30",
                        "网址": "https://example.com/notice/1",
                    },
                    {
                        "代码": symbol,
                        "名称": "浦发银行",
                        "公告标题": "浦发银行:董事会决议公告",
                        "公告类型": "董事会决议",
                        "公告日期": "2026-04-28",
                        "网址": "https://example.com/notice/2",
                    },
                ]
            ),
            symbol=symbol,
            fetch_time="2026-04-27T08:00:00+00:00",
        )


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


class SingleQuoteFakeAKShare:
    def __init__(self) -> None:
        self.bid_ask_calls: list[str] = []
        self.spot_calls = 0

    def stock_bid_ask_em(self, symbol):
        self.bid_ask_calls.append(symbol)
        if symbol == "000002":
            raise RuntimeError("quote unavailable")
        return FakeFrame(
            [
                {"item": "最新", "value": "10.8"},
                {"item": "今开", "value": "10.1"},
                {"item": "最高", "value": "10.9"},
                {"item": "最低", "value": "10.0"},
                {"item": "昨收", "value": "10.2"},
                {"item": "总手", "value": "2000"},
                {"item": "金额", "value": "21600"},
            ]
        )

    def stock_zh_a_spot_em(self):
        self.spot_calls += 1
        raise AssertionError("market_quote must not fetch full-market spot data")


class BlockingCacheStatusStore(MarketDuckDBStore):
    def __init__(self, release_event: threading.Event) -> None:
        super().__init__(":memory:")
        self.release_event = release_event
        self.timed_out = False

    def cache_status(self, symbol=None, interval=None):
        if not self.release_event.wait(timeout=0.2):
            self.timed_out = True
        return []


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

    quote = normalize_bid_ask_quote(
        FakeFrame(
            [
                {"item": "最新", "value": "10.8"},
                {"item": "今开", "value": "10.1"},
                {"item": "最高", "value": "10.9"},
                {"item": "最低", "value": "10.0"},
                {"item": "昨收", "value": "10.2"},
                {"item": "总手", "value": "2,000"},
                {"item": "金额", "value": "21,600"},
            ]
        ),
        symbol="600000",
        fetch_time="2026-04-27T09:35:00+00:00",
    )
    assert quote["symbol"] == "600000"
    assert quote["price"] == 10.8
    assert quote["previous_close"] == 10.2
    assert quote["volume"] == 2000.0
    assert quote["amount"] == 21600.0
    assert quote["source"] == "akshare.stock_bid_ask_em"


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


def test_akshare_quote_uses_single_symbol_lookup(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = SingleQuoteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    quote = asyncio.run(provider.quote("600000"))

    assert quote["symbol"] == "600000"
    assert quote["price"] == 10.8
    assert fake_ak.bid_ask_calls == ["600000"]
    assert fake_ak.spot_calls == 0


def test_akshare_quotes_batch_skips_failed_symbols(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = SingleQuoteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    quotes = asyncio.run(provider.quotes_batch(["600000", "000002", "600000"]))

    assert list(quotes) == ["600000"]
    assert quotes["600000"]["price"] == 10.8
    assert fake_ak.bid_ask_calls.count("600000") == 1
    assert fake_ak.bid_ask_calls.count("000002") == 1


def test_market_store_async_methods_do_not_block_event_loop() -> None:
    release_event = threading.Event()
    store = BlockingCacheStatusStore(release_event)

    async def release_soon() -> None:
        await asyncio.sleep(0.01)
        release_event.set()

    async def run() -> list[dict[str, object]]:
        started = time.perf_counter()
        status, _ = await asyncio.gather(store.cache_status_async(), release_soon())
        assert time.perf_counter() - started < 0.15
        return status

    status = asyncio.run(run())

    assert store.timed_out is False
    assert status == []


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


def test_minute_normalizer_accepts_chinese_columns() -> None:
    bars = normalize_minute_rows(
        FakeFrame(
            [
                {
                    "时间": "2026-04-27 09:35:00",
                    "开盘": "10.0",
                    "最高": "10.3",
                    "最低": "9.9",
                    "收盘": "10.2",
                    "成交量": "500",
                    "成交额": "5100",
                }
            ]
        ),
        symbol="1",
        period="5",
        adjust="qfq",
        fetch_time="2026-04-27T08:00:00+00:00",
    )
    assert bars[0]["symbol"] == "000001"
    assert bars[0]["open"] == 10.0
    assert bars[0]["close"] == 10.2
    assert bars[0]["interval"] == "5m"
    assert bars[0]["adjust"] == "qfq"
    assert bars[0]["datetime"] == "2026-04-27 09:35:00"


def test_announcement_normalizer_accepts_chinese_columns() -> None:
    announcements = normalize_announcement_rows(
        FakeFrame(
            [
                {
                    "代码": "600000",
                    "名称": "浦发银行",
                    "公告标题": "浦发银行:2026年一季度报告",
                    "公告类型": "一季度报告全文",
                    "公告日期": "2026-04-30",
                    "网址": "https://example.com/notice/1",
                }
            ]
        ),
        symbol="600000",
        fetch_time="2026-04-27T08:00:00+00:00",
    )
    assert announcements[0]["symbol"] == "600000"
    assert announcements[0]["name"] == "浦发银行"
    assert announcements[0]["title"] == "浦发银行:2026年一季度报告"
    assert announcements[0]["type"] == "一季度报告全文"
    assert "raw_hash" in announcements[0]


def test_minute_tool_returns_json(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    executor = ToolExecutor(client.app.state.tool_registry)

    import asyncio

    result = asyncio.run(
        executor.execute(
            "market_minute",
            (
                '{"symbol": "600000", "start": "2026-04-27", '
                '"end": "2026-04-27", "period": "5", '
                '"allow_fetch_missing": true}'
            ),
        )
    )
    assert result.ok is True
    assert result.result["symbol"] == "600000"
    assert result.result["interval"] == "5m"
    assert len(result.result["bars"]) == 2
    assert provider.minute_calls == 1


def test_announcement_tool_returns_json(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    executor = ToolExecutor(client.app.state.tool_registry)

    import asyncio

    result = asyncio.run(
        executor.execute(
            "market_announcement",
            (
                '{"symbol": "600000", "start": "2026-04-01", '
                '"end": "2026-05-01", "allow_fetch_missing": true}'
            ),
        )
    )
    assert result.ok is True
    assert result.result["symbol"] == "600000"
    assert len(result.result["announcements"]) == 2
    assert result.result["announcements"][0]["published_at"] == "2026-04-30"
    assert provider.announcement_calls == 1


def test_announcement_cache_hit_and_dedup(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    store = client.app.state.market_store

    announcements = [
        {
            "symbol": "600000",
            "name": "浦发银行",
            "title": "公告A",
            "type": "test",
            "published_at": "2026-04-30",
            "url": "https://example.com/a",
            "source": "test",
            "fetch_time": "2026-04-27T08:00:00+00:00",
            "raw_hash": "abc123",
        },
        {
            "symbol": "600000",
            "name": "浦发银行",
            "title": "公告B",
            "type": "test",
            "published_at": "2026-04-29",
            "url": "https://example.com/b",
            "source": "test",
            "fetch_time": "2026-04-27T08:00:00+00:00",
            "raw_hash": "def456",
        },
    ]

    stats = store.insert_announcements(announcements)
    assert stats == {"inserted": 2, "skipped": 0, "conflicted": 0}

    stats = store.insert_announcements(announcements)
    assert stats == {"inserted": 0, "skipped": 2, "conflicted": 0}

    fetched = store.query_announcements(symbol="600000")
    assert len(fetched) == 2
    assert fetched[0]["published_at"] == "2026-04-30"

    fetched_range = store.query_announcements(symbol="600000", start="2026-04-30", end="2026-04-30")
    assert len(fetched_range) == 1
    assert fetched_range[0]["title"] == "公告A"


def test_minute_api_endpoint(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)

    resp = client.get(
        "/api/market/minute",
        params={
            "symbol": "600000",
            "start": "2026-04-27",
            "end": "2026-04-27",
            "period": "5",
            "allow_fetch_missing": "true",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600000"
    assert data["interval"] == "5m"
    assert len(data["bars"]) == 2
    assert provider.minute_calls == 1


def test_announcement_api_endpoint(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)

    resp = client.get(
        "/api/market/announcement",
        params={
            "symbol": "600000",
            "start": "2026-04-01",
            "end": "2026-05-01",
            "allow_fetch_missing": "true",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600000"
    assert len(data["announcements"]) == 2
    assert provider.announcement_calls == 1


def test_minute_rejects_invalid_period(monkeypatch) -> None:
    client, _ = make_client(monkeypatch)

    resp = client.get(
        "/api/market/minute",
        params={
            "symbol": "600000",
            "start": "2026-04-27",
            "end": "2026-04-27",
            "period": "99",
        },
    )
    assert resp.status_code == 400
    assert "Unsupported period" in resp.json()["detail"]


def test_minute_requires_start_and_end(monkeypatch) -> None:
    client, _ = make_client(monkeypatch)
    executor = ToolExecutor(client.app.state.tool_registry)

    import asyncio

    result = asyncio.run(
        executor.execute("market_minute", '{"symbol": "600000"}')
    )
    assert result.ok is False
    assert "start" in (result.error or "").lower()
