from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from app.market.stock_data_logger import write_stock_data_api_log
from app.simulator.replay_clock import ReplayClockService, ReplayClockSnapshot
from app.simulator.valuation import PortfolioValuationService
from app.storage.sqlite import SQLiteStore

LIVE_VALUATION_INTERVAL_SECONDS = 60.0
REPLAY_VALUATION_INTERVAL_SECONDS = 60.0
MIN_REPLAY_VALUATION_INTERVAL_SECONDS = 5.0
VALUATION_LOOP_SLEEP_SECONDS = 1.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AccountValuationRefreshService:
    def __init__(
        self,
        store: SQLiteStore,
        market_store: Any,
        market_provider: Any,
        quote_coordinator: Any | None = None,
        websocket_manager: Any | None = None,
        live_interval_seconds: float = LIVE_VALUATION_INTERVAL_SECONDS,
        replay_interval_seconds: float = REPLAY_VALUATION_INTERVAL_SECONDS,
        min_replay_interval_seconds: float = MIN_REPLAY_VALUATION_INTERVAL_SECONDS,
        loop_sleep_seconds: float = VALUATION_LOOP_SLEEP_SECONDS,
    ) -> None:
        self.store = store
        self.market_store = market_store
        self.market_provider = market_provider
        self.websocket_manager = websocket_manager
        self.live_interval_seconds = live_interval_seconds
        self.replay_interval_seconds = replay_interval_seconds
        self.min_replay_interval_seconds = min_replay_interval_seconds
        self.loop_sleep_seconds = loop_sleep_seconds
        self.valuation_service = PortfolioValuationService(
            store=store,
            market_store=market_store,
            market_provider=market_provider,
            quote_coordinator=quote_coordinator,
        )
        self._next_due: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def refresh_due_accounts(self, now: float | None = None) -> list[dict[str, Any]]:
        current = now if now is not None else asyncio.get_running_loop().time()
        refreshed: list[dict[str, Any]] = []
        active_account_ids = set(self._account_ids_with_positions())
        for stale_account_id in set(self._next_due) - active_account_ids:
            self._next_due.pop(stale_account_id, None)

        for account_id in sorted(active_account_ids):
            clock = ReplayClockService(self.store).get_clock(account_id)
            interval = self.interval_for_clock(clock)
            if interval is None:
                self._next_due.pop(account_id, None)
                continue
            due_at = self._next_due.get(account_id)
            if due_at is not None and current < due_at:
                continue
            try:
                refreshed.append(await self.refresh_account(account_id, source="valuation"))
            except Exception as exc:
                write_stock_data_api_log(
                    "account_valuation.refresh.error",
                    {
                        "account_id": account_id,
                        "clock": clock.as_dict(),
                        "interval_seconds": interval,
                    },
                    ok=False,
                    error=exc,
                )
            finally:
                self._next_due[account_id] = current + interval
        return refreshed

    async def refresh_account(self, account_id: str, source: str = "valuation") -> dict[str, Any]:
        result = await self.valuation_service.refresh_account(account_id, source=source)
        clock = ReplayClockService(self.store).get_clock(account_id)
        payload = {
            "type": "portfolio_updated",
            "account_id": account_id,
            "source": source,
            "symbols": result.get("symbols", []),
            "total_asset": result.get("total_asset"),
            "market_value": result.get("market_value"),
            "unrealized_pnl": result.get("unrealized_pnl"),
            "valuation_point": result.get("valuation_point"),
            "clock": clock.as_dict(),
            "generated_at": utc_now(),
        }
        if self.websocket_manager is not None:
            await self.websocket_manager.send_account_event(account_id, payload)
        return {
            **result,
            "source": source,
            "clock": clock.as_dict(),
            "generated_at": payload["generated_at"],
        }

    def interval_for_clock(self, clock: ReplayClockSnapshot) -> float | None:
        if clock.mode == "live":
            return self.live_interval_seconds
        if clock.speed <= 0:
            return None
        return max(self.min_replay_interval_seconds, self.replay_interval_seconds / clock.speed)

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.refresh_due_accounts()
            except Exception as exc:
                write_stock_data_api_log(
                    "account_valuation.loop.error",
                    {},
                    ok=False,
                    error=exc,
                )
            await asyncio.sleep(self.loop_sleep_seconds)

    def _account_ids_with_positions(self) -> list[str]:
        rows = self.store.fetch_all(
            """
            SELECT DISTINCT simulator_account_id
            FROM positions
            WHERE quantity > 0
            ORDER BY simulator_account_id ASC
            """
        )
        return [str(row["simulator_account_id"]) for row in rows]
