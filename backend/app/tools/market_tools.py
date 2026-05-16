from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.market.replay import clamp_end_to_effective, effective_datetime, is_replay_context, replay_quote_from_cache
from app.tools.registry import ToolSpec

REPLAY_HISTORY_LOOKBACK_DAYS = 180
MARKET_OPEN_TIME = "09:30:00"


def create_market_tool_specs(market_store: Any, market_provider: Any) -> list[ToolSpec]:
    async def market_quote(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        if is_replay_context(runtime_context):
            return await replay_quote_from_cache(market_store, symbol, runtime_context, market_provider)
        quote = await market_provider.quote(symbol)
        await market_store.insert_quote_async(quote)
        return quote

    async def market_history(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        interval = str(arguments.get("interval") or "daily")
        start = _normalize_history_bound(_optional_text(arguments.get("start")), interval=interval)
        end = _normalize_history_bound(_optional_text(arguments.get("end")), interval=interval)
        adjust = str(arguments.get("adjust") or "")
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))
        replay = is_replay_context(runtime_context)
        auto_fetch_missing = replay or _is_session_runtime(runtime_context)
        if replay:
            if not start:
                start = _replay_history_start(runtime_context)
            end = clamp_end_to_effective(end, runtime_context, date_only=interval == "daily")

        bars = await market_store.query_history_async(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            adjust=adjust,
        )
        fetch_stats = None
        should_fetch = not bars if replay else not _covers_range(bars, start, end)
        if (allow_fetch_missing or auto_fetch_missing) and should_fetch:
            if not start or not end:
                raise ValueError("start and end are required when allow_fetch_missing is true.")
            fetched = await market_provider.history(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust=adjust,
            )
            fetch_stats = await market_store.insert_bars_async(fetched)
            bars = await market_store.query_history_async(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust=adjust,
            )
        if replay and not bars:
            raise ValueError(f"No cached history for {symbol} before replay time {end}.")

        return {
            "symbol": symbol,
            "interval": interval,
            "adjust": adjust,
            "cache_hit": bool(bars),
            "fetch_stats": fetch_stats,
            "bars": bars,
        }

    async def data_fetch_history(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if is_replay_context(runtime_context):
            raise ValueError("data_fetch_history is disabled during replay runs.")
        symbol = str(arguments["symbol"])
        start = str(arguments["start"])
        end = str(arguments["end"])
        interval = str(arguments.get("interval") or "daily")
        adjust = str(arguments.get("adjust") or "")
        fetched = await market_provider.history(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            adjust=adjust,
        )
        stats = await market_store.insert_bars_async(fetched)
        return {
            "symbol": symbol,
            "interval": interval,
            "adjust": adjust,
            "fetched": len(fetched),
            **stats,
        }

    async def market_minute(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = _normalize_datetime_text(_optional_text(arguments.get("start")))
        end = _normalize_datetime_text(_optional_text(arguments.get("end")))
        period = str(arguments.get("period") or "1")
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))
        replay = is_replay_context(runtime_context)
        auto_fetch_missing = replay or _is_session_runtime(runtime_context)
        if replay:
            if not start:
                start = _replay_minute_start(runtime_context)
            end = clamp_end_to_effective(end, runtime_context)
        if not start or not end:
            raise ValueError("start and end are required.")

        bars = await market_store.query_history_async(
            symbol=symbol,
            start=start,
            end=end,
            interval=f"{period}m",
            adjust="",
        )
        fetch_stats = None
        should_fetch = not bars if replay else not _covers_range(bars, start, end)
        if (allow_fetch_missing or auto_fetch_missing) and should_fetch:
            fetched = await market_provider.minute(
                symbol=symbol,
                start=start,
                end=end,
                period=period,
            )
            fetch_stats = await market_store.insert_bars_async(fetched)
            bars = await market_store.query_history_async(
                symbol=symbol,
                start=start,
                end=end,
                interval=f"{period}m",
                adjust="",
            )
        if replay and not bars:
            raise ValueError(f"No cached minute history for {symbol} before replay time {end}.")

        return {
            "symbol": symbol,
            "interval": f"{period}m",
            "adjust": "",
            "cache_hit": bool(bars),
            "fetch_stats": fetch_stats,
            "bars": bars,
        }

    async def market_announcement(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = _normalize_date_text(_optional_text(arguments.get("start")))
        end = _normalize_date_text(_optional_text(arguments.get("end")))
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))
        replay = is_replay_context(runtime_context)
        auto_fetch_missing = replay or _is_session_runtime(runtime_context)
        if replay:
            end = clamp_end_to_effective(end, runtime_context, date_only=True)

        announcements = await market_store.query_announcements_async(
            symbol=symbol,
            start=start,
            end=end,
        )
        fetch_stats = None
        if not announcements and (allow_fetch_missing or auto_fetch_missing):
            if not start or not end:
                raise ValueError("start and end are required for announcement lookup.")
            fetched = await market_provider.announcement(
                symbol=symbol,
                start=start,
                end=end,
            )
            fetch_stats = await market_store.insert_announcements_async(fetched)
            announcements = await market_store.query_announcements_async(
                symbol=symbol,
                start=start,
                end=end,
            )
        if replay and not announcements:
            raise ValueError(f"No cached announcements for {symbol} before replay time {end}.")

        return {
            "symbol": symbol,
            "cache_hit": bool(announcements),
            "fetch_stats": fetch_stats,
            "announcements": announcements,
        }

    return [
        ToolSpec(
            name="market_quote",
            display_name="market.quote",
            description="Get the latest A-share quote for a symbol and persist the quote snapshot.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "A-share stock code, e.g. 600000."}
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
            handler=market_quote,
            strict=True,
        ),
        ToolSpec(
            name="market_history",
            display_name="market.history",
            description=(
                "Read historical A-share bars from local cache, optionally fetching missing data. "
                "During replay runs, missing history is prepared automatically only up to the replay time."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "start": {"type": "string", "description": "Start date, YYYY-MM-DD or YYYYMMDD."},
                    "end": {"type": "string", "description": "End date, YYYY-MM-DD or YYYYMMDD."},
                    "interval": {"type": "string", "enum": ["daily"]},
                    "adjust": {"type": "string", "enum": ["", "qfq", "hfq"]},
                    "allow_fetch_missing": {"type": "boolean"},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
            handler=market_history,
            strict=True,
        ),
        ToolSpec(
            name="market_minute",
            display_name="market.minute",
            description=(
                "Read A-share minute K-line bars from local cache, optionally fetching missing data. "
                "During replay runs, missing minute bars are prepared automatically only up to the replay time."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "A-share stock code, e.g. 600000."},
                    "start": {"type": "string", "description": "Start datetime, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."},
                    "end": {"type": "string", "description": "End datetime, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."},
                    "period": {"type": "string", "enum": ["1", "5", "15", "30", "60"]},
                    "allow_fetch_missing": {"type": "boolean"},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
            handler=market_minute,
            strict=True,
        ),
        ToolSpec(
            name="market_announcement",
            display_name="market.announcement",
            description=(
                "Search A-share company announcements/notices from the local cache, optionally fetching missing data. "
                "During replay runs, missing announcements are prepared automatically only up to the replay date."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "A-share stock code, e.g. 600000."},
                    "start": {"type": "string", "description": "Start date, YYYY-MM-DD or YYYYMMDD."},
                    "end": {"type": "string", "description": "End date, YYYY-MM-DD or YYYYMMDD."},
                    "allow_fetch_missing": {"type": "boolean"},
                },
                "required": ["symbol", "start", "end"],
                "additionalProperties": False,
            },
            handler=market_announcement,
            strict=True,
        ),
        ToolSpec(
            name="data_fetch_history",
            display_name="data.fetch_history",
            description="Fetch historical A-share bars from AKShare and write them into the local cache.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "start": {"type": "string", "description": "Start date, YYYY-MM-DD or YYYYMMDD."},
                    "end": {"type": "string", "description": "End date, YYYY-MM-DD or YYYYMMDD."},
                    "interval": {"type": "string", "enum": ["daily"]},
                    "adjust": {"type": "string", "enum": ["", "qfq", "hfq"]},
                },
                "required": ["symbol", "start", "end"],
                "additionalProperties": False,
            },
            handler=data_fetch_history,
            strict=True,
        ),
    ]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_session_runtime(runtime_context: dict[str, Any] | None) -> bool:
    return bool(runtime_context and runtime_context.get("session_id") and runtime_context.get("run_id"))


def _normalize_history_bound(value: str | None, *, interval: str) -> str | None:
    if interval == "daily":
        return _normalize_date_text(value)
    return _normalize_datetime_text(value)


def _normalize_date_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if "T" in text:
        return text.split("T", 1)[0]
    return text[:10]


def _normalize_datetime_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if "T" in text:
        text = text.replace("T", " ")
    return text[:19]


def _covers_range(rows: list[dict[str, Any]], start: str | None, end: str | None) -> bool:
    if not rows or not start or not end:
        return bool(rows)
    first = str(rows[0].get("datetime") or "")
    last = str(rows[-1].get("datetime") or "")
    return first <= start and last >= end


def _replay_history_start(runtime_context: dict[str, Any] | None) -> str:
    effective = effective_datetime(runtime_context)
    return (effective.date() - timedelta(days=REPLAY_HISTORY_LOOKBACK_DAYS)).isoformat()


def _replay_minute_start(runtime_context: dict[str, Any] | None) -> str:
    effective = effective_datetime(runtime_context)
    return f"{effective.date().isoformat()} {MARKET_OPEN_TIME}"
