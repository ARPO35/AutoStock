from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

from starlette.concurrency import run_in_threadpool


def _pad_date_if_needed(value: str, pad: str) -> str:
    text = value.strip()
    if " " in text:
        return text
    return text + pad


class MarketDuckDBStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._connection: Any | None = None

    def connect(self) -> None:
        try:
            import duckdb
        except ModuleNotFoundError as exc:
            raise RuntimeError("The duckdb package is required for market cache storage.") from exc

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(str(self.path))

    @property
    def connection(self) -> Any:
        if self._connection is None:
            self.connect()
        return self._connection

    def initialize(self) -> None:
        with self._lock:
            self.connection.execute(SCHEMA_SQL)

    def insert_bars(self, bars: list[dict[str, Any]]) -> dict[str, int]:
        stats = {"inserted": 0, "skipped": 0, "conflicted": 0}
        if not bars:
            return stats

        with self._lock:
            self.connection.execute("BEGIN TRANSACTION")
            try:
                for bar in bars:
                    existing = self._fetch_bar_key(bar)
                    if existing is None:
                        self._insert_bar(bar)
                        stats["inserted"] += 1
                    elif existing["raw_hash"] == bar["raw_hash"]:
                        stats["skipped"] += 1
                    else:
                        self._insert_conflict(existing=existing, new_value=bar)
                        stats["conflicted"] += 1
                self._refresh_cache_status()
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
        return stats

    async def insert_bars_async(self, bars: list[dict[str, Any]]) -> dict[str, int]:
        return await run_in_threadpool(self.insert_bars, bars)

    def insert_quote(self, quote: dict[str, Any]) -> None:
        with self._lock:
            self._insert_quote(quote)

    async def insert_quote_async(self, quote: dict[str, Any]) -> None:
        await run_in_threadpool(self.insert_quote, quote)

    def insert_quotes(self, quotes: list[dict[str, Any]]) -> dict[str, int]:
        stats = {"inserted": 0, "skipped": 0, "conflicted": 0}
        if not quotes:
            return stats
        with self._lock:
            self.connection.execute("BEGIN TRANSACTION")
            try:
                for quote in quotes:
                    self._insert_quote(quote)
                    stats["inserted"] += 1
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
        return stats

    async def insert_quotes_async(self, quotes: list[dict[str, Any]]) -> dict[str, int]:
        return await run_in_threadpool(self.insert_quotes, quotes)

    def query_history(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        interval: str = "daily",
        adjust: str = "",
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT *
            FROM market_bars
            WHERE symbol = ?
              AND interval = ?
              AND adjust = ?
        """
        params: list[Any] = [symbol, interval, adjust]
        if start:
            sql += " AND datetime >= ?"
            params.append(start)
        if end:
            sql += " AND datetime <= ?"
            params.append(_pad_date_if_needed(end, pad=" 23:59:59"))
        sql += " ORDER BY datetime ASC"
        return self._rows(sql, params)

    async def query_history_async(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        interval: str = "daily",
        adjust: str = "",
    ) -> list[dict[str, Any]]:
        return await run_in_threadpool(
            self.query_history,
            symbol,
            start,
            end,
            interval,
            adjust,
        )

    def latest_bar(
        self,
        symbol: str,
        end: str,
        interval: str | None = None,
        interval_like: str | None = None,
        adjust: str | None = None,
    ) -> dict[str, Any] | None:
        sql = """
            SELECT *
            FROM market_bars
            WHERE symbol = ?
              AND datetime <= ?
        """
        params: list[Any] = [symbol, end]
        if interval is not None:
            sql += " AND interval = ?"
            params.append(interval)
        if interval_like is not None:
            sql += " AND interval LIKE ?"
            params.append(interval_like)
        if adjust is not None:
            sql += " AND adjust = ?"
            params.append(adjust)
        sql += " ORDER BY datetime DESC LIMIT 1"
        return self._row(sql, params)

    async def latest_bar_async(
        self,
        symbol: str,
        end: str,
        interval: str | None = None,
        interval_like: str | None = None,
        adjust: str | None = None,
    ) -> dict[str, Any] | None:
        return await run_in_threadpool(
            self.latest_bar,
            symbol,
            end,
            interval,
            interval_like,
            adjust,
        )

    def cache_status(
        self,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM market_cache_status WHERE 1 = 1"
        params: list[Any] = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if interval:
            sql += " AND interval = ?"
            params.append(interval)
        sql += " ORDER BY symbol, interval, adjust"
        return self._rows(sql, params)

    async def cache_status_async(
        self,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> list[dict[str, Any]]:
        return await run_in_threadpool(self.cache_status, symbol, interval)

    def list_conflicts(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM data_conflicts"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY fetch_time DESC"
        return self._rows(sql, params)

    async def list_conflicts_async(self, status: str | None = None) -> list[dict[str, Any]]:
        return await run_in_threadpool(self.list_conflicts, status)

    def resolve_conflict(self, conflict_id: str, status: str) -> dict[str, Any] | None:
        with self._lock:
            self.connection.execute(
                """
                UPDATE data_conflicts
                SET status = ?
                WHERE id = ?
                """,
                [status, conflict_id],
            )
            return self._row("SELECT * FROM data_conflicts WHERE id = ?", [conflict_id])

    async def resolve_conflict_async(
        self,
        conflict_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        return await run_in_threadpool(self.resolve_conflict, conflict_id, status)

    def insert_announcements(self, announcements: list[dict[str, Any]]) -> dict[str, int]:
        stats = {"inserted": 0, "skipped": 0, "conflicted": 0}
        if not announcements:
            return stats

        with self._lock:
            self.connection.execute("BEGIN TRANSACTION")
            try:
                for ann in announcements:
                    existing = self._fetch_announcement_key(ann)
                    if existing is None:
                        self._insert_announcement(ann)
                        stats["inserted"] += 1
                    elif existing["raw_hash"] == ann["raw_hash"]:
                        stats["skipped"] += 1
                    else:
                        self._insert_announcement_conflict(existing=existing, new_value=ann)
                        stats["conflicted"] += 1
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
        return stats

    async def insert_announcements_async(self, announcements: list[dict[str, Any]]) -> dict[str, int]:
        return await run_in_threadpool(self.insert_announcements, announcements)

    def query_announcements(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT *
            FROM market_announcements
            WHERE symbol = ?
        """
        params: list[Any] = [symbol]
        if start:
            sql += " AND published_at >= ?"
            params.append(start)
        if end:
            sql += " AND published_at <= ?"
            params.append(end)
        sql += " ORDER BY published_at DESC, title ASC"
        return self._rows(sql, params)

    async def query_announcements_async(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        return await run_in_threadpool(
            self.query_announcements,
            symbol,
            start,
            end,
        )

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _fetch_bar_key(self, bar: dict[str, Any]) -> dict[str, Any] | None:
        return self._row(
            """
            SELECT *
            FROM market_bars
            WHERE symbol = ?
              AND interval = ?
              AND datetime = ?
              AND adjust = ?
            """,
            [bar["symbol"], bar["interval"], bar["datetime"], bar["adjust"]],
        )

    def _insert_bar(self, bar: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO market_bars (
                symbol, name, interval, datetime, open, high, low, close,
                volume, amount, adjust, source, fetch_time, raw_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                bar.get("symbol"),
                bar.get("name"),
                bar.get("interval"),
                bar.get("datetime"),
                bar.get("open"),
                bar.get("high"),
                bar.get("low"),
                bar.get("close"),
                bar.get("volume"),
                bar.get("amount"),
                bar.get("adjust"),
                bar.get("source"),
                bar.get("fetch_time"),
                bar.get("raw_hash"),
            ],
        )

    def _insert_quote(self, quote: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO market_quotes (
                id, symbol, name, price, open, high, low, previous_close,
                volume, amount, source, fetch_time, raw_hash, snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                uuid4().hex,
                quote.get("symbol"),
                quote.get("name"),
                quote.get("price"),
                quote.get("open"),
                quote.get("high"),
                quote.get("low"),
                quote.get("previous_close"),
                quote.get("volume"),
                quote.get("amount"),
                quote.get("source"),
                quote.get("fetch_time"),
                quote.get("raw_hash"),
                json.dumps(quote, ensure_ascii=False, sort_keys=True),
            ],
        )

    def _insert_conflict(self, existing: dict[str, Any], new_value: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO data_conflicts (
                id, symbol, interval, datetime, adjust, existing_value_json,
                new_value_json, source, fetch_time, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            [
                uuid4().hex,
                new_value.get("symbol"),
                new_value.get("interval"),
                new_value.get("datetime"),
                new_value.get("adjust"),
                json.dumps(existing, ensure_ascii=False, sort_keys=True, default=str),
                json.dumps(new_value, ensure_ascii=False, sort_keys=True, default=str),
                new_value.get("source"),
                new_value.get("fetch_time"),
            ],
        )

    def _refresh_cache_status(self) -> None:
        self.connection.execute("DELETE FROM market_cache_status")
        self.connection.execute(
            """
            INSERT INTO market_cache_status (
                symbol, name, interval, adjust, start_datetime,
                end_datetime, bar_count, updated_at
            )
            SELECT
                symbol,
                any_value(name),
                interval,
                adjust,
                min(datetime),
                max(datetime),
                count(*),
                max(fetch_time)
            FROM market_bars
            GROUP BY symbol, interval, adjust
            """
        )

    def _fetch_announcement_key(self, ann: dict[str, Any]) -> dict[str, Any] | None:
        return self._row(
            """
            SELECT *
            FROM market_announcements
            WHERE symbol = ?
              AND published_at = ?
              AND title = ?
            """,
            [ann["symbol"], ann.get("published_at"), ann.get("title")],
        )

    def _insert_announcement(self, ann: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO market_announcements (
                symbol, name, title, type, published_at, url,
                source, fetch_time, raw_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ann.get("symbol"),
                ann.get("name"),
                ann.get("title"),
                ann.get("type"),
                ann.get("published_at"),
                ann.get("url"),
                ann.get("source"),
                ann.get("fetch_time"),
                ann.get("raw_hash"),
            ],
        )

    def _insert_announcement_conflict(
        self,
        existing: dict[str, Any],
        new_value: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO data_conflicts (
                id, symbol, interval, datetime, adjust, existing_value_json,
                new_value_json, source, fetch_time, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            [
                uuid4().hex,
                new_value.get("symbol"),
                "announcement",
                new_value.get("published_at", ""),
                "",
                json.dumps(existing, ensure_ascii=False, sort_keys=True, default=str),
                json.dumps(new_value, ensure_ascii=False, sort_keys=True, default=str),
                new_value.get("source"),
                new_value.get("fetch_time"),
            ],
        )

    def _row(self, sql: str, params: Iterable[Any]) -> dict[str, Any] | None:
        cursor = self.connection.execute(sql, list(params))
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row, strict=False)) if row else None

    def _rows(self, sql: str, params: Iterable[Any]) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, list(params))
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS market_bars (
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    interval VARCHAR NOT NULL,
    datetime VARCHAR NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    adjust VARCHAR NOT NULL DEFAULT '',
    source VARCHAR NOT NULL,
    fetch_time VARCHAR NOT NULL,
    raw_hash VARCHAR NOT NULL,
    PRIMARY KEY (symbol, interval, datetime, adjust)
);

CREATE TABLE IF NOT EXISTS market_quotes (
    id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    price DOUBLE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    previous_close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    source VARCHAR NOT NULL,
    fetch_time VARCHAR NOT NULL,
    raw_hash VARCHAR NOT NULL,
    snapshot_json VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS data_conflicts (
    id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    datetime VARCHAR NOT NULL,
    adjust VARCHAR NOT NULL DEFAULT '',
    existing_value_json VARCHAR NOT NULL,
    new_value_json VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    fetch_time VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS market_cache_status (
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    interval VARCHAR NOT NULL,
    adjust VARCHAR NOT NULL DEFAULT '',
    start_datetime VARCHAR NOT NULL,
    end_datetime VARCHAR NOT NULL,
    bar_count BIGINT NOT NULL,
    updated_at VARCHAR NOT NULL,
    PRIMARY KEY (symbol, interval, adjust)
);

CREATE TABLE IF NOT EXISTS market_announcements (
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    title VARCHAR NOT NULL,
    type VARCHAR,
    published_at VARCHAR NOT NULL,
    url VARCHAR,
    source VARCHAR NOT NULL,
    fetch_time VARCHAR NOT NULL,
    raw_hash VARCHAR NOT NULL,
    PRIMARY KEY (symbol, published_at, title)
);
"""
