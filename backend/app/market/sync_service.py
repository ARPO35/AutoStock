from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.market.normalizer import normalize_symbol
from app.simulator.valuation import PortfolioValuationService
from app.storage.sqlite import SQLiteStore

SyncScope = Literal["positions", "watchlist", "all"]

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MARKET_OPEN = time(9, 30)
MARKET_MIDDAY_START = time(11, 30)
MARKET_MIDDAY_END = time(13, 0)
MARKET_CLOSE = time(15, 0)
QUOTE_CACHE_TTL_SECONDS = 3.0


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


SSE_2026_CLOSED_RANGES = (
    ("2026-01-01", "2026-01-03"),
    ("2026-02-15", "2026-02-23"),
    ("2026-04-04", "2026-04-06"),
    ("2026-05-01", "2026-05-05"),
    ("2026-06-19", "2026-06-21"),
    ("2026-09-25", "2026-09-27"),
    ("2026-10-01", "2026-10-07"),
)
SSE_2026_CLOSED_DATES = frozenset(
    current.isoformat()
    for start, end in SSE_2026_CLOSED_RANGES
    for current in _date_range(date.fromisoformat(start), date.fromisoformat(end))
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SyncStats:
    fetched: int = 0
    inserted: int = 0
    skipped: int = 0
    conflicted: int = 0

    def add_store_stats(self, stats: dict[str, int] | None, fetched: int = 0) -> None:
        self.fetched += fetched
        self.inserted += int((stats or {}).get("inserted", 0))
        self.skipped += int((stats or {}).get("skipped", 0))
        self.conflicted += int((stats or {}).get("conflicted", 0))

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "conflicted": self.conflicted,
        }


class TradingCalendar:
    def __init__(self, market_provider: Any | None = None) -> None:
        self.market_provider = market_provider
        self._trade_dates: set[str] | None = None
        self._max_trade_date: str | None = None
        self._loaded = False

    def is_trading_day(self, value: date) -> bool:
        if value.weekday() >= 5:
            return False
        text = value.isoformat()
        dates = self._load_trade_dates()
        if dates and self._max_trade_date and text <= self._max_trade_date:
            return text in dates
        if text in SSE_2026_CLOSED_DATES:
            return False
        return True

    def _load_trade_dates(self) -> set[str]:
        if self._loaded:
            return self._trade_dates or set()
        self._loaded = True
        provider = self.market_provider
        sync_func = getattr(provider, "trading_dates_sync", None)
        if sync_func is None:
            return set()
        try:
            dates = {str(item)[:10] for item in sync_func() if item}
        except Exception:
            dates = set()
        self._trade_dates = dates
        self._max_trade_date = max(dates) if dates else None
        return dates


class QuoteSyncCoordinator:
    def __init__(self, ttl_seconds: float = QUOTE_CACHE_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[dict[str, dict[str, Any]]]] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def fetch_quotes(self, symbols: list[str], market_provider: Any) -> dict[str, dict[str, Any]]:
        unique_symbols = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols if symbol))
        if not unique_symbols:
            return {}

        now = asyncio.get_running_loop().time()
        results: dict[str, dict[str, Any]] = {}
        tasks: dict[asyncio.Task[dict[str, dict[str, Any]]], list[str]] = {}
        async with self._lock:
            for symbol in unique_symbols:
                cached = self._cache.get(symbol)
                if cached and cached[0] >= now:
                    results[symbol] = cached[1]
                    continue
                task = self._inflight.get(symbol)
                if task is None:
                    task = asyncio.create_task(self._fetch_batch([symbol], market_provider))
                    self._inflight[symbol] = task
                tasks.setdefault(task, []).append(symbol)

        for task, task_symbols in tasks.items():
            try:
                fetched = await task
            except Exception:
                async with self._lock:
                    for symbol in task_symbols:
                        if self._inflight.get(symbol) is task:
                            self._inflight.pop(symbol, None)
                raise
            expires_at = asyncio.get_running_loop().time() + self.ttl_seconds
            async with self._lock:
                for symbol, quote in fetched.items():
                    self._cache[symbol] = (expires_at, quote)
                for symbol in task_symbols:
                    if self._inflight.get(symbol) is task:
                        self._inflight.pop(symbol, None)
            results.update({symbol: fetched[symbol] for symbol in task_symbols if symbol in fetched})
        return {symbol: results[symbol] for symbol in unique_symbols if symbol in results}

    async def _fetch_batch(self, symbols: list[str], market_provider: Any) -> dict[str, dict[str, Any]]:
        if hasattr(market_provider, "quotes_batch"):
            quotes = await market_provider.quotes_batch(symbols)
            return {normalize_symbol(symbol): quote for symbol, quote in quotes.items()}
        result: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            result[symbol] = await market_provider.quote(symbol)
        return result


class MarketSyncService:
    def __init__(
        self,
        store: SQLiteStore,
        market_store: Any,
        market_provider: Any,
        quote_coordinator: QuoteSyncCoordinator | None = None,
        trading_calendar: TradingCalendar | None = None,
        valuation_service: PortfolioValuationService | None = None,
    ) -> None:
        self.store = store
        self.market_store = market_store
        self.market_provider = market_provider
        self.quote_coordinator = quote_coordinator or QuoteSyncCoordinator()
        self.trading_calendar = trading_calendar or TradingCalendar(market_provider)
        self.valuation_service = valuation_service or PortfolioValuationService(
            store=store,
            market_store=market_store,
            market_provider=market_provider,
            quote_coordinator=self.quote_coordinator,
        )

    def list_watchlist(self) -> list[dict[str, Any]]:
        return self.store.fetch_all(
            """
            SELECT *
            FROM market_watchlist
            ORDER BY enabled DESC, symbol ASC
            """
        )

    def add_watchlist_symbol(
        self,
        symbol: str,
        name: str | None = None,
        note: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        normalized = normalize_symbol(symbol)
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO market_watchlist (id, symbol, name, note, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                note = excluded.note,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (uuid4().hex, normalized, name, note, 1 if enabled else 0, now, now),
        )
        row = self.store.fetch_one("SELECT * FROM market_watchlist WHERE symbol = ?", (normalized,))
        assert row is not None
        return row

    def update_watchlist_symbol(
        self,
        item_id: str,
        name: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        existing = self.store.fetch_one("SELECT * FROM market_watchlist WHERE id = ?", (item_id,))
        if existing is None:
            return None
        self.store.execute(
            """
            UPDATE market_watchlist
            SET name = ?, note = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name if name is not None else existing.get("name"),
                note if note is not None else existing.get("note", ""),
                int(enabled) if enabled is not None else int(existing.get("enabled") or 0),
                utc_now(),
                item_id,
            ),
        )
        return self.store.fetch_one("SELECT * FROM market_watchlist WHERE id = ?", (item_id,))

    def delete_watchlist_symbol(self, item_id: str) -> bool:
        existing = self.store.fetch_one("SELECT id FROM market_watchlist WHERE id = ?", (item_id,))
        if existing is None:
            return False
        self.store.execute("DELETE FROM market_watchlist WHERE id = ?", (item_id,))
        return True

    def recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.store.fetch_all(
            """
            SELECT *
            FROM market_sync_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def sync_quotes(self, scope: SyncScope) -> dict[str, Any]:
        symbols = self.target_symbols(scope)
        return await self._recorded_run("quote", scope, symbols, self._sync_quotes(symbols))

    async def sync_minutes(self, scope: SyncScope, period: str = "5") -> dict[str, Any]:
        symbols = self.target_symbols(scope)
        return await self._recorded_run("minute", scope, symbols, self._sync_minutes(symbols, period))

    async def sync_daily(self, scope: SyncScope = "all") -> dict[str, Any]:
        symbols = self.target_symbols(scope)
        return await self._recorded_run("daily", scope, symbols, self._sync_daily(symbols))

    async def sync_announcements(self, scope: SyncScope = "all") -> dict[str, Any]:
        symbols = self.target_symbols(scope)
        return await self._recorded_run(
            "announcement",
            scope,
            symbols,
            self._sync_announcements(symbols),
        )

    async def sync_all_a_quotes(self) -> dict[str, Any]:
        return await self._recorded_run("all_a_quote", "all", [], self._sync_all_a_quotes())

    def is_trading_time(self, now: datetime | None = None) -> bool:
        return is_trading_time(now, calendar=self.trading_calendar)

    async def ensure_history(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "daily",
        adjust: str = "",
    ) -> dict[str, int] | None:
        bars = await self.market_store.query_history_async(symbol, start, end, interval, adjust)
        if _covers_range(bars, start, end):
            return None
        fetched = await self.market_provider.history(symbol, start, end, interval, adjust)
        return await self.market_store.insert_bars_async(fetched)

    async def ensure_minute(
        self,
        symbol: str,
        start: str,
        end: str,
        period: str = "1",
    ) -> dict[str, int] | None:
        interval = f"{period}m"
        bars = await self.market_store.query_history_async(symbol, start, end, interval, "")
        if _covers_range(bars, start, end):
            return None
        fetched = await self.market_provider.minute(symbol, start, end, period=period)
        return await self.market_store.insert_bars_async(fetched)

    async def ensure_announcements(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> dict[str, int] | None:
        announcements = await self.market_store.query_announcements_async(symbol, start, end)
        if announcements:
            return None
        fetched = await self.market_provider.announcement(symbol, start, end)
        return await self.market_store.insert_announcements_async(fetched)

    def target_symbols(self, scope: SyncScope) -> list[str]:
        symbols: list[str] = []
        if scope in {"positions", "all"}:
            symbols.extend(self._position_symbols())
        if scope in {"watchlist", "all"}:
            symbols.extend(self._watchlist_symbols())
        return list(dict.fromkeys(symbols))

    def _position_symbols(self) -> list[str]:
        rows = self.store.fetch_all(
            """
            SELECT DISTINCT symbol
            FROM positions
            WHERE quantity > 0
            ORDER BY symbol ASC
            """
        )
        return [normalize_symbol(row["symbol"]) for row in rows if row.get("symbol")]

    def _watchlist_symbols(self) -> list[str]:
        rows = self.store.fetch_all(
            """
            SELECT symbol
            FROM market_watchlist
            WHERE enabled = 1
            ORDER BY symbol ASC
            """
        )
        return [normalize_symbol(row["symbol"]) for row in rows if row.get("symbol")]

    async def _sync_quotes(self, symbols: list[str]) -> SyncStats:
        stats = SyncStats()
        if not symbols:
            return stats
        quotes_map = await self.quote_coordinator.fetch_quotes(symbols, self.market_provider)
        quotes = [quotes_map[symbol] for symbol in symbols if symbol in quotes_map]
        store_stats = await self.market_store.insert_quotes_async(quotes)
        await self.valuation_service.refresh_accounts_for_symbols(
            symbols=list(quotes_map),
            quote_overrides=quotes_map,
            source="valuation",
        )
        stats.add_store_stats(store_stats, fetched=len(quotes))
        return stats

    async def _sync_minutes(self, symbols: list[str], period: str) -> SyncStats:
        stats = SyncStats()
        if not symbols:
            return stats
        start, end = _today_minute_range()
        for symbol in symbols:
            fetched = await self.market_provider.minute(symbol, start, end, period=period)
            store_stats = await self.market_store.insert_bars_async(fetched)
            stats.add_store_stats(store_stats, fetched=len(fetched))
        return stats

    async def _sync_daily(self, symbols: list[str]) -> SyncStats:
        stats = SyncStats()
        if not symbols:
            return stats
        today = _today_date()
        for symbol in symbols:
            start = _daily_start_for_symbol(self.market_store, symbol, today)
            if start > today:
                continue
            fetched = await self.market_provider.history(symbol, start, today, interval="daily", adjust="")
            store_stats = await self.market_store.insert_bars_async(fetched)
            stats.add_store_stats(store_stats, fetched=len(fetched))
        return stats

    async def _sync_announcements(self, symbols: list[str]) -> SyncStats:
        stats = SyncStats()
        if not symbols:
            return stats
        end = _today_date()
        start = (_today_local() - timedelta(days=7)).date().isoformat()
        for symbol in symbols:
            fetched = await self.market_provider.announcement(symbol, start, end)
            store_stats = await self.market_store.insert_announcements_async(fetched)
            stats.add_store_stats(store_stats, fetched=len(fetched))
        return stats

    async def _sync_all_a_quotes(self) -> SyncStats:
        if not hasattr(self.market_provider, "all_a_quotes"):
            raise RuntimeError("Market provider does not support all A-share quote snapshots.")
        quotes = await self.market_provider.all_a_quotes()
        store_stats = await self.market_store.insert_quotes_async(quotes)
        stats = SyncStats()
        stats.add_store_stats(store_stats, fetched=len(quotes))
        return stats

    async def _recorded_run(
        self,
        job_type: str,
        scope: str,
        symbols: list[str],
        task: Any,
    ) -> dict[str, Any]:
        run_id = uuid4().hex
        started_at = utc_now()
        self.store.execute(
            """
            INSERT INTO market_sync_runs (
                id, job_type, scope, symbols_json, status, started_at
            )
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (run_id, job_type, scope, json.dumps(symbols), started_at),
        )
        try:
            stats: SyncStats = await task
            finished_at = utc_now()
            self.store.execute(
                """
                UPDATE market_sync_runs
                SET status = 'success',
                    fetched = ?,
                    inserted = ?,
                    skipped = ?,
                    conflicted = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    stats.fetched,
                    stats.inserted,
                    stats.skipped,
                    stats.conflicted,
                    finished_at,
                    run_id,
                ),
            )
        except Exception as exc:
            finished_at = utc_now()
            self.store.execute(
                """
                UPDATE market_sync_runs
                SET status = 'error', error = ?, finished_at = ?
                WHERE id = ?
                """,
                (str(exc), finished_at, run_id),
            )
            raise
        row = self.store.fetch_one("SELECT * FROM market_sync_runs WHERE id = ?", (run_id,))
        assert row is not None
        return row


def is_trading_time(now: datetime | None = None, calendar: TradingCalendar | None = None) -> bool:
    local = now.astimezone(SHANGHAI_TZ) if now else _today_local()
    trading_calendar = calendar or TradingCalendar()
    if not trading_calendar.is_trading_day(local.date()):
        return False
    current = local.time()
    return (MARKET_OPEN <= current <= MARKET_MIDDAY_START) or (
        MARKET_MIDDAY_END <= current <= MARKET_CLOSE
    )


def _today_local() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _today_date() -> str:
    return _today_local().date().isoformat()


def _today_minute_range() -> tuple[str, str]:
    local = _today_local()
    date_text = local.date().isoformat()
    start = f"{date_text} {MARKET_OPEN.strftime('%H:%M:%S')}"
    close_dt = datetime.combine(local.date(), MARKET_CLOSE, tzinfo=SHANGHAI_TZ)
    end_dt = min(local, close_dt)
    return start, end_dt.strftime("%Y-%m-%d %H:%M:%S")


def _daily_start_for_symbol(market_store: Any, symbol: str, today: str) -> str:
    latest = market_store.latest_bar(symbol=symbol, end=today, interval="daily", adjust="")
    if latest is None or not latest.get("datetime"):
        return (_today_local() - timedelta(days=30)).date().isoformat()
    latest_date = _parse_date(str(latest["datetime"]))
    return (latest_date + timedelta(days=1)).isoformat()


def _covers_range(rows: list[dict[str, Any]], start: str, end: str) -> bool:
    if not rows:
        return False
    first = str(rows[0].get("datetime") or "")
    last = str(rows[-1].get("datetime") or "")
    return first <= start and last >= end


def _parse_date(value: str):
    return datetime.fromisoformat(value[:10]).date()
