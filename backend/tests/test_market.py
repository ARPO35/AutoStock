from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from http.client import RemoteDisconnected
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.market.akshare_provider import AKShareMarketProvider
from app.market.normalizer import (
    normalize_announcement_rows,
    normalize_bid_ask_quote,
    normalize_history_rows,
    normalize_minute_rows,
    normalize_sina_quote_response,
    normalize_spot_rows,
)
from app.market.replay import replay_quote_from_cache
from app.market.sync_service import QuoteSyncCoordinator, is_trading_time
from app.storage.duckdb import MarketDuckDBStore
from app.tools.executor import ToolExecutor

SPDB_NAME = "\u6d66\u53d1\u94f6\u884c"


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
        self.all_a_calls = 0

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

    async def all_a_quotes(self):
        self.all_a_calls += 1
        return normalize_spot_rows(
            FakeFrame(
                [
                    {
                        "代码": "600000",
                        "名称": "浦发银行",
                        "最新价": 10.8,
                    },
                    {
                        "代码": "000001",
                        "名称": "平安银行",
                        "最新价": 12.3,
                    },
                ]
            ),
            fetch_time="2026-04-27T15:30:00+00:00",
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
        self.name_calls = 0
        self.spot_calls = 0

    def stock_info_a_code_name(self):
        self.name_calls += 1
        return FakeFrame([{"code": "600000", "name": SPDB_NAME}])

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


class DisconnectedQuoteFakeAKShare(SingleQuoteFakeAKShare):
    def stock_bid_ask_em(self, symbol):
        import requests

        self.bid_ask_calls.append(symbol)
        raise requests.exceptions.ConnectionError("eastmoney disconnected")


class DisconnectedHistoryFakeAKShare(SingleQuoteFakeAKShare):
    def __init__(self) -> None:
        super().__init__()
        self.hist_calls: list[dict[str, str]] = []
        self.daily_calls: list[dict[str, str]] = []

    def stock_zh_a_hist(self, **kwargs):
        import requests

        self.hist_calls.append(kwargs)
        raise requests.exceptions.ConnectionError("eastmoney disconnected")

    def stock_zh_a_daily(self, **kwargs):
        self.daily_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "date": "2026-05-15",
                    "open": 9.0,
                    "high": 9.22,
                    "low": 8.93,
                    "close": 9.07,
                    "volume": 171982587,
                    "amount": 1559276666,
                }
            ]
        )


class SlowQuoteProvider:
    def __init__(self) -> None:
        self.quote_calls = 0

    async def quote(self, symbol):
        self.quote_calls += 1
        await asyncio.sleep(0.01)
        return normalize_spot_rows(
            FakeFrame(
                [
                    {
                        "代码": symbol,
                        "名称": "浦发银行",
                        "最新价": 10.8,
                    }
                ]
            ),
            fetch_time="2026-04-27T09:35:00+00:00",
        )[0]


class MinuteSuccessFakeAKShare(SingleQuoteFakeAKShare):
    def __init__(self) -> None:
        super().__init__()
        self.hist_min_calls: list[dict[str, str]] = []
        self.sina_minute_calls: list[dict[str, str]] = []

    def stock_zh_a_hist_min_em(self, **kwargs):
        self.hist_min_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "时间": "2026-05-15 09:35:00",
                    "开盘": 10.0,
                    "最高": 10.3,
                    "最低": 9.9,
                    "收盘": 10.2,
                    "成交量": 500,
                    "成交额": 5100,
                }
            ]
        )

    def stock_zh_a_minute(self, **kwargs):
        self.sina_minute_calls.append(kwargs)
        raise AssertionError("Sina minute fallback must not be called after Eastmoney succeeds")


class DisconnectedMinuteFakeAKShare(SingleQuoteFakeAKShare):
    def __init__(self) -> None:
        super().__init__()
        self.hist_min_calls: list[dict[str, str]] = []
        self.sina_minute_calls: list[dict[str, str]] = []

    def stock_zh_a_hist_min_em(self, **kwargs):
        self.hist_min_calls.append(kwargs)
        raise RemoteDisconnected("eastmoney disconnected")

    def stock_zh_a_minute(self, **kwargs):
        self.sina_minute_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "day": "2026-05-15 09:25:00",
                    "open": 9.8,
                    "high": 9.9,
                    "low": 9.7,
                    "close": 9.8,
                    "volume": 300,
                    "amount": 2940,
                },
                {
                    "day": "2026-05-15 09:35:00",
                    "open": 10.0,
                    "high": 10.3,
                    "low": 9.9,
                    "close": 10.2,
                    "volume": 500,
                    "amount": 5100,
                },
                {
                    "day": "2026-05-15 15:01:00",
                    "open": 10.4,
                    "high": 10.4,
                    "low": 10.3,
                    "close": 10.3,
                    "volume": 200,
                    "amount": 2060,
                },
            ]
        )


class FailedMinuteFallbackFakeAKShare(DisconnectedMinuteFakeAKShare):
    def stock_zh_a_minute(self, **kwargs):
        self.sina_minute_calls.append(kwargs)
        raise RuntimeError("sina minute unavailable")


class NameLookupFailureFakeAKShare(SingleQuoteFakeAKShare):
    def stock_info_a_code_name(self):
        self.name_calls += 1
        raise RuntimeError("name lookup unavailable")


class NamedBarsFakeAKShare(SingleQuoteFakeAKShare):
    def stock_zh_a_hist(self, **kwargs):
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

    def stock_zh_a_hist_min_em(self, **kwargs):
        return FakeFrame(
            [
                {
                    "时间": "2026-04-27 09:35:00",
                    "开盘": 10.0,
                    "最高": 10.3,
                    "最低": 9.9,
                    "收盘": 10.2,
                    "成交量": 500,
                    "成交额": 5100,
                }
            ]
        )


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


def test_sina_quote_normalizer_accepts_realtime_payload() -> None:
    payload = (
        'var hq_str_sh600036="招商银行,39.360,39.430,39.810,39.980,39.290,'
        '39.800,39.810,52269354,2075496453.000,29700,39.800,1200,39.790,'
        '5400,39.780,800,39.770,500,39.760,4100,39.810,2300,39.820,'
        '900,39.830,700,39.840,600,39.850,2026-05-15,15:00:00,00,";'
    )

    quote = normalize_sina_quote_response(
        payload,
        fetch_time="2026-05-15T07:00:00+00:00",
    )[0]

    assert quote["symbol"] == "600036"
    assert quote["name"] == "招商银行"
    assert quote["price"] == 39.81
    assert quote["open"] == 39.36
    assert quote["previous_close"] == 39.43
    assert quote["high"] == 39.98
    assert quote["low"] == 39.29
    assert quote["volume"] == 52269354.0
    assert quote["amount"] == 2075496453.0
    assert quote["source"] == "sina.hq.sinajs.cn"


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
    assert quote["name"] == SPDB_NAME
    assert quote["price"] == 10.8
    assert fake_ak.bid_ask_calls == ["600000"]
    assert fake_ak.name_calls == 1
    assert fake_ak.spot_calls == 0


def test_akshare_quote_tolerates_name_lookup_failure(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = NameLookupFailureFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)
    monkeypatch.setattr(
        provider,
        "_sina_response",
        lambda symbols: (
            'var hq_str_sh600000="浦发银行,10.100,10.200,10.800,10.900,'
            '10.000,10.700,10.800,2000,21600.000,0,0,0,0,0,0,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-05-15,15:00:00,00,";'
        ),
    )

    quote = asyncio.run(provider.quote("600000"))

    assert quote["symbol"] == "600000"
    assert quote["name"] == SPDB_NAME
    assert quote["price"] == 10.8
    assert fake_ak.name_calls == 1
    assert fake_ak.spot_calls == 0


def test_akshare_quote_falls_back_to_sina_when_eastmoney_disconnects(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = DisconnectedQuoteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)
    monkeypatch.setattr(
        provider,
        "_sina_response",
        lambda symbols: (
            'var hq_str_sh600036="招商银行,39.360,39.430,39.810,39.980,'
            '39.290,39.800,39.810,52269354,2075496453.000,0,0,0,0,0,0,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-05-15,15:00:00,00,";'
        ),
    )

    quote = asyncio.run(provider.quote("600036"))

    assert quote["symbol"] == "600036"
    assert quote["name"] == "招商银行"
    assert quote["price"] == 39.81
    assert quote["source"] == "sina.hq.sinajs.cn"
    assert fake_ak.bid_ask_calls == ["600036"]
    assert fake_ak.name_calls == 1


def test_akshare_quotes_batch_uses_single_sina_request(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = SingleQuoteFakeAKShare()
    requested: list[list[str]] = []
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    def fake_sina_response(symbols):
        requested.append(symbols)
        return (
            'var hq_str_sh600036="招商银行,39.360,39.430,39.810,39.980,'
            '39.290,39.800,39.810,52269354,2075496453.000,0,0,0,0,0,0,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-05-15,15:00:00,00,";\n'
            'var hq_str_sh601318="中国平安,46.000,45.900,46.550,46.880,'
            '45.800,46.540,46.550,80000000,3700000000.000,0,0,0,0,0,0,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-05-15,15:00:00,00,";'
        )

    monkeypatch.setattr(provider, "_sina_response", fake_sina_response)

    quotes = asyncio.run(provider.quotes_batch(["600036", "601318", "600036"]))

    assert list(quotes) == ["600036", "601318"]
    assert quotes["600036"]["name"] == "招商银行"
    assert quotes["601318"]["price"] == 46.55
    assert requested == [["600036", "601318"]]
    assert fake_ak.bid_ask_calls == []
    assert fake_ak.name_calls == 0


def test_akshare_history_falls_back_to_sina_when_eastmoney_disconnects(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = DisconnectedHistoryFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    history = asyncio.run(provider.history("600000", "2026-05-11", "2026-05-15"))

    assert len(history) == 1
    assert history[0]["symbol"] == "600000"
    assert history[0]["name"] == SPDB_NAME
    assert history[0]["datetime"] == "2026-05-15"
    assert history[0]["open"] == 9.0
    assert history[0]["high"] == 9.22
    assert history[0]["low"] == 8.93
    assert history[0]["close"] == 9.07
    assert history[0]["volume"] == 1719825.87
    assert history[0]["amount"] == 1559276666.0
    assert history[0]["source"] == "akshare.stock_zh_a_daily"
    assert fake_ak.hist_calls == [
        {
            "symbol": "600000",
            "period": "daily",
            "start_date": "20260511",
            "end_date": "20260515",
            "adjust": "",
        }
    ]
    assert fake_ak.daily_calls == [
        {
            "symbol": "sh600000",
            "start_date": "20260511",
            "end_date": "20260515",
            "adjust": "",
        }
    ]


def test_akshare_minute_uses_eastmoney_without_sina_fallback(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = MinuteSuccessFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    minute = asyncio.run(
        provider.minute(
            "600000",
            "2026-05-15 09:30:00",
            "2026-05-15 15:00:00",
            period="1",
        )
    )

    assert len(minute) == 1
    assert minute[0]["source"] == "akshare.stock_zh_a_hist_min_em"
    assert fake_ak.hist_min_calls == [
        {
            "symbol": "600000",
            "start_date": "2026-05-15 09:30:00",
            "end_date": "2026-05-15 15:00:00",
            "period": "1",
            "adjust": "",
        }
    ]
    assert fake_ak.sina_minute_calls == []


def test_akshare_minute_falls_back_to_sina_after_eastmoney_disconnects(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = DisconnectedMinuteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    minute = asyncio.run(provider.minute("600000", "2026-05-15", "2026-05-15", period="1"))

    assert len(minute) == 1
    assert minute[0]["datetime"] == "2026-05-15 09:35:00"
    assert minute[0]["open"] == 10.0
    assert minute[0]["close"] == 10.2
    assert minute[0]["source"] == "akshare.stock_zh_a_minute"
    assert fake_ak.hist_min_calls == [
        {
            "symbol": "600000",
            "start_date": "2026-05-15 09:30:00",
            "end_date": "2026-05-15 15:00:00",
            "period": "1",
            "adjust": "",
        },
        {
            "symbol": "600000",
            "start_date": "2026-05-15 09:30:00",
            "end_date": "2026-05-15 15:00:00",
            "period": "1",
            "adjust": "",
        },
    ]
    assert fake_ak.sina_minute_calls == [
        {
            "symbol": "sh600000",
            "period": "1",
            "adjust": "",
        }
    ]


def test_akshare_minute_reports_clear_error_when_both_providers_fail(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = FailedMinuteFallbackFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    try:
        asyncio.run(provider.minute("600000", "2026-05-15", "2026-05-15", period="1"))
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("minute should fail when both providers are unavailable")

    assert "Minute market data providers are unavailable" in message
    assert "Eastmoney minute data failed after a short retry" in message
    assert "Sina minute fallback failed" in message


def test_replay_quote_derives_from_sina_minute_fallback_when_eastmoney_disconnects(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = DisconnectedMinuteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)
    store = MarketDuckDBStore(":memory:")
    store.initialize()

    quote = asyncio.run(
        replay_quote_from_cache(
            store,
            "600000",
            {"time_mode": "replay", "effective_time": "2026-05-15 10:00:00"},
            provider,
        )
    )

    assert quote["price"] == 10.2
    assert quote["datetime"] == "2026-05-15 09:35:00"
    assert quote["source"] == "replay.derived.minute"
    assert fake_ak.sina_minute_calls == [{"symbol": "sh600000", "period": "1", "adjust": ""}]


def test_akshare_provider_enriches_bars_cache_status_and_replay_quote(monkeypatch) -> None:
    provider = AKShareMarketProvider()
    fake_ak = NamedBarsFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    history = asyncio.run(provider.history("600000", "2026-04-27", "2026-04-27"))
    minute = asyncio.run(provider.minute("600000", "2026-04-27", "2026-04-27", period="5"))

    assert history[0]["name"] == SPDB_NAME
    assert minute[0]["name"] == SPDB_NAME
    assert fake_ak.name_calls == 1

    store = MarketDuckDBStore(":memory:")
    store.initialize()
    assert store.insert_bars(history + minute)["inserted"] == 2

    status = store.cache_status(symbol="600000")
    assert {row["interval"]: row["name"] for row in status} == {"daily": SPDB_NAME, "5m": SPDB_NAME}

    quote = asyncio.run(
        replay_quote_from_cache(
            store,
            "600000",
            {"time_mode": "replay", "effective_time": "2026-04-27 09:40:00"},
        )
    )
    assert quote["name"] == SPDB_NAME


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


def test_data_api_reuses_shared_market_sync_service(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    original_service = client.app.state.market_sync_service
    client.app.state.market_provider = provider

    response = client.get("/api/data/watchlist")

    assert response.status_code == 200
    assert client.app.state.market_sync_service is not original_service
    shared_service = client.app.state.market_sync_service

    response = client.get("/api/data/sync-runs")

    assert response.status_code == 200
    assert client.app.state.market_sync_service is shared_service


def test_trading_time_uses_2026_sse_holiday_fallback() -> None:
    assert is_trading_time(datetime.fromisoformat("2026-05-06T09:35:00+08:00")) is True
    assert is_trading_time(datetime.fromisoformat("2026-05-01T09:35:00+08:00")) is False
    assert is_trading_time(datetime.fromisoformat("2026-05-16T09:35:00+08:00")) is False
    assert is_trading_time(datetime.fromisoformat("2026-05-06T12:00:00+08:00")) is False


def test_quote_sync_coordinator_reuses_inflight_symbol() -> None:
    provider = SlowQuoteProvider()
    coordinator = QuoteSyncCoordinator(ttl_seconds=30)

    async def run():
        return await asyncio.gather(
            coordinator.fetch_quotes(["600000"], provider),
            coordinator.fetch_quotes(["600000"], provider),
        )

    first, second = asyncio.run(run())

    assert first["600000"]["price"] == 10.8
    assert second["600000"]["price"] == 10.8
    assert provider.quote_calls == 1


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


def test_watchlist_and_manual_quote_sync(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)

    added = client.post(
        "/api/data/watchlist",
        json={"symbol": "600000", "name": "SPDB", "note": "track"},
    )
    assert added.status_code == 201
    item = added.json()
    assert item["symbol"] == "600000"

    run = client.post(
        "/api/data/sync/run",
        json={"job_type": "quote", "scope": "watchlist"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "success"
    assert body["inserted"] == 1
    assert provider.quote_calls == 1

    rows = client.get("/api/data/sync-runs").json()
    assert rows[0]["job_type"] == "quote"
    assert rows[0]["scope"] == "watchlist"

    updated = client.put(f"/api/data/watchlist/{item['id']}", json={"enabled": False})
    assert updated.status_code == 200
    assert updated.json()["enabled"] == 0

    deleted = client.delete(f"/api/data/watchlist/{item['id']}")
    assert deleted.status_code == 204


def test_position_quote_sync_refreshes_account_valuation(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)
    account = client.post(
        "/api/simulator/accounts",
        json={"name": "Valuation Account", "initial_cash": 100000},
    ).json()
    now = "2026-04-27T09:30:00+08:00"
    store = client.app.state.store
    store.execute(
        """
        INSERT INTO positions (
            id, simulator_account_id, symbol, name, quantity,
            available_quantity, avg_cost, market_value, unrealized_pnl, updated_at
        )
        VALUES (?, ?, '600000', '浦发银行', 1000, 1000, 10, 10000, 0, ?)
        """,
        (uuid4().hex, account["id"], now),
    )
    store.execute(
        """
        UPDATE simulator_accounts
        SET cash = 90000, total_asset = 100000, updated_at = ?
        WHERE id = ?
        """,
        (now, account["id"]),
    )

    run = client.post(
        "/api/data/sync/run",
        json={"job_type": "quote", "scope": "positions"},
    )

    assert run.status_code == 200
    assert provider.quote_calls == 1
    account_row = store.fetch_one("SELECT total_asset FROM simulator_accounts WHERE id = ?", (account["id"],))
    position_row = store.fetch_one(
        "SELECT market_value, unrealized_pnl FROM positions WHERE simulator_account_id = ?",
        (account["id"],),
    )
    point = store.fetch_one(
        "SELECT source, market_value, total_asset, symbols_json FROM account_valuation_points WHERE simulator_account_id = ?",
        (account["id"],),
    )
    assert account_row["total_asset"] == 100800
    assert position_row["market_value"] == 10800
    assert position_row["unrealized_pnl"] == 800
    assert point["source"] == "valuation"
    assert point["market_value"] == 10800
    assert point["total_asset"] == 100800
    assert json.loads(point["symbols_json"]) == ["600000"]


def test_manual_all_a_quote_snapshot_sync(monkeypatch) -> None:
    client, provider = make_client(monkeypatch)

    run = client.post(
        "/api/data/sync/run",
        json={"job_type": "all_a_quote", "scope": "all"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "success"
    assert body["fetched"] == 2
    assert body["inserted"] == 2
    assert provider.all_a_calls == 1
    rows = client.app.state.market_store._rows(
        "SELECT symbol, name, price FROM market_quotes ORDER BY symbol",
        [],
    )
    assert [row["symbol"] for row in rows] == ["000001", "600000"]
    assert rows[1]["name"] == "浦发银行"


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


def test_minute_normalizer_accepts_sina_day_column() -> None:
    bars = normalize_minute_rows(
        FakeFrame(
            [
                {
                    "day": "2026-05-15 09:35:00",
                    "open": "10.0",
                    "high": "10.3",
                    "low": "9.9",
                    "close": "10.2",
                    "volume": "500",
                    "amount": "5100",
                }
            ]
        ),
        symbol="600000",
        period="1",
        fetch_time="2026-05-15T01:35:00+00:00",
    )

    assert bars[0]["datetime"] == "2026-05-15 09:35:00"
    assert bars[0]["open"] == 10.0
    assert bars[0]["amount"] == 5100.0


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


def test_minute_tool_uses_provider_sina_fallback_when_eastmoney_disconnects(monkeypatch) -> None:
    client, _ = make_client(monkeypatch)
    provider = AKShareMarketProvider()
    fake_ak = DisconnectedMinuteFakeAKShare()
    monkeypatch.setattr(provider, "_akshare", lambda: fake_ak)

    from app.tools.registry import create_default_registry

    client.app.state.market_provider = provider
    client.app.state.tool_registry = create_default_registry(
        market_store=client.app.state.market_store,
        market_provider=provider,
    )
    executor = ToolExecutor(client.app.state.tool_registry)

    result = asyncio.run(
        executor.execute(
            "market_minute",
            (
                '{"symbol": "600000", "start": "2026-05-15", '
                '"end": "2026-05-15", "period": "1", '
                '"allow_fetch_missing": true}'
            ),
        )
    )

    assert result.ok is True
    assert len(result.result["bars"]) == 1
    assert result.result["bars"][0]["source"] == "akshare.stock_zh_a_minute"
    assert fake_ak.sina_minute_calls == [{"symbol": "sh600000", "period": "1", "adjust": ""}]


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
