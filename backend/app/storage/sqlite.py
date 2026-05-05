from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        self._connection = connection

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.connect()
        assert self._connection is not None
        return self._connection

    def initialize(self) -> None:
        with self._lock:
            self.connection.executescript(SCHEMA_SQL)
            try:
                self.connection.execute(
                    "ALTER TABLE chat_messages ADD COLUMN reasoning_content TEXT"
                )
            except sqlite3.OperationalError:
                pass
            try:
                self.connection.execute(
                    "ALTER TABLE chat_runs ADD COLUMN token_usage TEXT"
                )
            except sqlite3.OperationalError:
                pass
            try:
                self.connection.execute(
                    "ALTER TABLE chat_sessions ADD COLUMN prompt_role_id TEXT"
                )
            except sqlite3.OperationalError:
                pass
            self._seed_default_prompt_role()
            self.connection.commit()

    def _seed_default_prompt_role(self) -> None:
        exists = self.connection.execute(
            "SELECT id FROM prompt_roles WHERE id = ?",
            ("default",),
        ).fetchone()
        if exists:
            return

        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO prompt_roles (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("default", "默认角色", now, now),
        )
        self.connection.executemany(
            """
            INSERT INTO prompt_entries (
                id, role_id, name, ref_name, content, enabled, builtin,
                sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "default-system",
                    "default",
                    "系统提示词",
                    "system",
                    "",
                    1,
                    1,
                    0,
                    now,
                    now,
                ),
                (
                    "default-userinput",
                    "default",
                    "用户输入",
                    "UserInput",
                    "{UserInput}{time}",
                    1,
                    1,
                    1,
                    now,
                    now,
                ),
            ],
        )

    def execute(
        self,
        sql: str,
        parameters: Iterable[Any] | dict[str, Any] = (),
    ) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.connection.execute(sql, parameters)
            self.connection.commit()
            return cursor

    def fetch_one(
        self,
        sql: str,
        parameters: Iterable[Any] | dict[str, Any] = (),
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(sql, parameters).fetchone()
            return dict(row) if row else None

    def fetch_all(
        self,
        sql: str,
        parameters: Iterable[Any] | dict[str, Any] = (),
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(sql, parameters).fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    llm_account_id TEXT,
    skill_id TEXT,
    simulator_account_id TEXT,
    provider_id TEXT,
    model TEXT,
    prompt_role_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS prompt_roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_entries (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL REFERENCES prompt_roles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ref_name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    builtin INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_entries_role_ref
    ON prompt_entries(role_id, ref_name);

CREATE INDEX IF NOT EXISTS idx_prompt_entries_role_order
    ON prompt_entries(role_id, sort_order);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'user',
    trigger_id TEXT,
    parent_message_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER,
    timeout_seconds REAL NOT NULL DEFAULT 60,
    supports_tools INTEGER NOT NULL DEFAULT 1,
    supports_parallel_tool_calls INTEGER NOT NULL DEFAULT 0,
    supports_strict_schema INTEGER NOT NULL DEFAULT 0,
    thinking_mode TEXT,
    strict_tool_schema INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_providers_name
    ON llm_providers(name);

CREATE TABLE IF NOT EXISTS llm_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    initial_cash REAL NOT NULL DEFAULT 1000000,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_accounts_name
    ON llm_accounts(name);

CREATE TABLE IF NOT EXISTS simulator_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    cash REAL NOT NULL,
    frozen_cash REAL NOT NULL DEFAULT 0,
    total_asset REAL NOT NULL,
    commission_rate REAL NOT NULL DEFAULT 0.00025,
    min_commission REAL NOT NULL DEFAULT 5.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_simulator_accounts_created
    ON simulator_accounts(created_at);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    simulator_account_id TEXT NOT NULL REFERENCES simulator_accounts(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    market_value REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_account_symbol
    ON positions(simulator_account_id, symbol);

CREATE INDEX IF NOT EXISTS idx_positions_symbol
    ON positions(symbol);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    simulator_account_id TEXT NOT NULL REFERENCES simulator_accounts(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    filled_quantity INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_account_created
    ON orders(simulator_account_id, created_at);

CREATE INDEX IF NOT EXISTS idx_orders_session
    ON orders(session_id);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    simulator_account_id TEXT NOT NULL REFERENCES simulator_accounts(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    traded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_account_traded
    ON trades(simulator_account_id, traded_at);

CREATE INDEX IF NOT EXISTS idx_trades_order
    ON trades(order_id);

CREATE INDEX IF NOT EXISTS idx_trades_session
    ON trades(session_id);

CREATE TABLE IF NOT EXISTS chat_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    provider_id TEXT,
    model TEXT,
    status TEXT NOT NULL,
    event_message_id TEXT,
    max_tool_rounds INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    final_message_id TEXT,
    error TEXT,
    token_usage TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_runs_session_started
    ON chat_runs(session_id, started_at);

CREATE TABLE IF NOT EXISTS chat_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES chat_runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id TEXT,
    provider_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_tool_calls_run
    ON chat_tool_calls(run_id);

CREATE TABLE IF NOT EXISTS chat_tool_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES chat_runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    tool_call_id TEXT NOT NULL REFERENCES chat_tool_calls(id) ON DELETE CASCADE,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tavily_config (
    id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL DEFAULT '',
    default_search_depth TEXT NOT NULL DEFAULT 'basic',
    default_topic TEXT NOT NULL DEFAULT 'finance',
    default_max_results INTEGER NOT NULL DEFAULT 5,
    cache_ttl_seconds INTEGER NOT NULL DEFAULT 1800,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tavily_cache (
    cache_key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tavily_cache_operation
    ON tavily_cache(operation, created_at);

CREATE TABLE IF NOT EXISTS tavily_usage_records (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    run_id TEXT,
    tool_call_id TEXT,
    operation TEXT NOT NULL,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    request_json TEXT NOT NULL,
    response_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    latency_ms REAL,
    result_count INTEGER NOT NULL DEFAULT 0,
    credits_estimated REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tavily_usage_created
    ON tavily_usage_records(created_at);

CREATE INDEX IF NOT EXISTS idx_tavily_usage_session
    ON tavily_usage_records(session_id, created_at);
"""
