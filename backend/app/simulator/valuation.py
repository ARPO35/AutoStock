from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.market.normalizer import normalize_symbol
from app.market.replay import is_replay_context, replay_quote_from_cache
from app.simulator.replay_clock import ReplayClockService
from app.storage.sqlite import SQLiteStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PortfolioValuationService:
    def __init__(
        self,
        store: SQLiteStore,
        market_store: Any,
        market_provider: Any,
        quote_coordinator: Any | None = None,
    ) -> None:
        self.store = store
        self.market_store = market_store
        self.market_provider = market_provider
        self.quote_coordinator = quote_coordinator

    async def refresh_accounts_for_symbols(
        self,
        symbols: list[str],
        quote_overrides: dict[str, dict[str, Any]] | None = None,
        source: str = "valuation",
    ) -> list[dict[str, Any]]:
        normalized_symbols = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols if symbol))
        if not normalized_symbols:
            return []
        placeholders = ",".join("?" for _ in normalized_symbols)
        accounts = self.store.fetch_all(
            f"""
            SELECT DISTINCT simulator_account_id
            FROM positions
            WHERE quantity > 0
              AND symbol IN ({placeholders})
            ORDER BY simulator_account_id ASC
            """,
            normalized_symbols,
        )
        refreshed: list[dict[str, Any]] = []
        for row in accounts:
            refreshed.append(
                await self.refresh_account(
                    str(row["simulator_account_id"]),
                    refresh_symbols=normalized_symbols,
                    quote_overrides=quote_overrides,
                    source=source,
                )
            )
        return refreshed

    async def refresh_account(
        self,
        account_id: str,
        refresh_symbols: list[str] | None = None,
        quote_overrides: dict[str, dict[str, Any]] | None = None,
        source: str = "valuation",
    ) -> dict[str, Any]:
        account = self._account_or_raise(account_id)
        positions = self._positions(account_id)
        normalized_refresh = {
            normalize_symbol(symbol)
            for symbol in (refresh_symbols or [str(pos["symbol"]) for pos in positions])
            if symbol
        }
        quotes = await self._quotes_for_account(account_id, positions, normalized_refresh, quote_overrides)
        valuation_time = self._valuation_time(account_id)

        for pos in positions:
            symbol = normalize_symbol(str(pos["symbol"]))
            quote = quotes.get(symbol)
            if quote is None:
                continue
            price = _float(quote.get("price"))
            if price is None:
                continue
            quantity = int(pos["quantity"])
            market_value = round(price * quantity, 2)
            unrealized_pnl = round((price - float(pos["avg_cost"])) * quantity, 2)
            self.store.execute(
                """
                UPDATE positions
                SET name = ?, market_value = ?, unrealized_pnl = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _best_stock_name(quote.get("name"), pos.get("name")),
                    market_value,
                    unrealized_pnl,
                    valuation_time,
                    pos["id"],
                ),
            )

        positions = self._positions(account_id)
        market_value = round(sum(float(pos.get("market_value") or 0) for pos in positions), 2)
        unrealized_pnl = round(sum(float(pos.get("unrealized_pnl") or 0) for pos in positions), 2)
        total_asset = round(float(account["cash"]) + market_value, 2)
        self.store.execute(
            """
            UPDATE simulator_accounts
            SET total_asset = ?, updated_at = ?
            WHERE id = ?
            """,
            (total_asset, valuation_time, account_id),
        )
        valuation_point_id = uuid4().hex
        valuation_point = {
            "id": valuation_point_id,
            "simulator_account_id": account_id,
            "time": valuation_time,
            "cash": float(account["cash"]),
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "total_asset": total_asset,
            "source": source,
            "symbols": sorted(quotes),
        }
        self.store.execute(
            """
            INSERT INTO account_valuation_points (
                id, simulator_account_id, time, cash, market_value,
                unrealized_pnl, total_asset, source, symbols_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                valuation_point_id,
                account_id,
                valuation_time,
                float(account["cash"]),
                market_value,
                unrealized_pnl,
                total_asset,
                source,
                json.dumps(sorted(quotes), ensure_ascii=False),
            ),
        )
        refreshed_account = self._account_or_raise(account_id)
        return {
            "account": refreshed_account,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "total_asset": total_asset,
            "symbols": sorted(quotes),
            "valuation_point": valuation_point,
        }

    async def _quotes_for_account(
        self,
        account_id: str,
        positions: list[dict[str, Any]],
        refresh_symbols: set[str],
        quote_overrides: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        clock = ReplayClockService(self.store).get_clock(account_id)
        runtime_context = clock.runtime_context()
        target_symbols = [
            normalize_symbol(str(pos["symbol"]))
            for pos in positions
            if not refresh_symbols or normalize_symbol(str(pos["symbol"])) in refresh_symbols
        ]
        if is_replay_context(runtime_context):
            result: dict[str, dict[str, Any]] = {}
            for symbol in target_symbols:
                result[symbol] = await replay_quote_from_cache(
                    self.market_store,
                    symbol,
                    runtime_context,
                    self.market_provider,
                )
            return result

        normalized_overrides = {
            normalize_symbol(symbol): quote
            for symbol, quote in (quote_overrides or {}).items()
        }
        result = {symbol: normalized_overrides[symbol] for symbol in target_symbols if symbol in normalized_overrides}
        missing = [symbol for symbol in target_symbols if symbol not in result]
        if missing:
            fetched = (
                await self.quote_coordinator.fetch_quotes(missing, self.market_provider)
                if self.quote_coordinator is not None
                else await self.market_provider.quotes_batch(missing)
            )
            result.update(fetched)
        return result

    def _valuation_time(self, account_id: str) -> str:
        clock = ReplayClockService(self.store).get_clock(account_id)
        if clock.mode == "replay":
            return clock.effective_time
        return utc_now()

    def _account_or_raise(self, account_id: str) -> dict[str, Any]:
        account = self.store.fetch_one("SELECT * FROM simulator_accounts WHERE id = ?", (account_id,))
        if account is None:
            raise LookupError(f"Simulator account not found: {account_id}")
        return account

    def _positions(self, account_id: str) -> list[dict[str, Any]]:
        return self.store.fetch_all(
            """
            SELECT *
            FROM positions
            WHERE simulator_account_id = ?
              AND quantity > 0
            ORDER BY symbol ASC
            """,
            (account_id,),
        )


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_stock_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "None", "none", "null", "NULL", "nan", "NaN", "--", "-"}:
        return ""
    return text


def _best_stock_name(*values: object) -> str:
    for value in values:
        name = _clean_stock_name(value)
        if name:
            return name
    return ""
