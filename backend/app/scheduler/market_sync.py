from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.market.sync_service import MarketSyncService, is_trading_time

logger = logging.getLogger(__name__)


def create_market_sync_scheduler(sync_service: MarketSyncService) -> Any | None:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ModuleNotFoundError:
        logger.warning("APScheduler is not installed; market sync scheduling is disabled.")
        return None

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    scheduler.add_job(
        _run_trading_job,
        IntervalTrigger(seconds=60),
        args=[sync_service.sync_quotes, "positions"],
        id="market-positions-quote",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_trading_job,
        IntervalTrigger(seconds=120),
        args=[sync_service.sync_quotes, "watchlist"],
        id="market-watchlist-quote",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_trading_job,
        IntervalTrigger(minutes=5),
        args=[sync_service.sync_minutes, "positions"],
        kwargs={"period": "5"},
        id="market-positions-minute",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_trading_job,
        IntervalTrigger(minutes=15),
        args=[sync_service.sync_minutes, "watchlist"],
        kwargs={"period": "5"},
        id="market-watchlist-minute",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_job,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0),
        args=[sync_service.sync_daily, "all"],
        id="market-daily-close-fill",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    for hour, minute, job_id in [(8, 45, "open"), (12, 35, "midday"), (16, 10, "close")]:
        scheduler.add_job(
            _run_job,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute),
            args=[sync_service.sync_announcements, "all"],
            id=f"market-announcement-{job_id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        _run_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=30),
        args=[sync_service.sync_all_a_quotes],
        id="market-all-a-close-quote",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    return scheduler


async def _run_trading_job(func: Any, *args: Any, **kwargs: Any) -> None:
    if not is_trading_time():
        return
    await _run_job(func, *args, **kwargs)


async def _run_job(func: Any, *args: Any, **kwargs: Any) -> None:
    try:
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        logger.exception("Market sync job failed.")
