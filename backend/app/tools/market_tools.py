from __future__ import annotations

from typing import Any

from app.tools.registry import ToolSpec


def create_market_tool_specs(market_store: Any, market_provider: Any) -> list[ToolSpec]:
    async def market_quote(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        quote = await market_provider.quote(symbol)
        await market_store.insert_quote_async(quote)
        return quote

    async def market_history(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = _optional_text(arguments.get("start"))
        end = _optional_text(arguments.get("end"))
        interval = str(arguments.get("interval") or "daily")
        adjust = str(arguments.get("adjust") or "")
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))

        bars = await market_store.query_history_async(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            adjust=adjust,
        )
        fetch_stats = None
        if not bars and allow_fetch_missing:
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

        return {
            "symbol": symbol,
            "interval": interval,
            "adjust": adjust,
            "cache_hit": bool(bars),
            "fetch_stats": fetch_stats,
            "bars": bars,
        }

    async def data_fetch_history(arguments: dict[str, Any]) -> dict[str, Any]:
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

    async def market_minute(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = str(arguments["start"])
        end = str(arguments["end"])
        period = str(arguments.get("period") or "1")
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))

        bars = await market_store.query_history_async(
            symbol=symbol,
            start=start,
            end=end,
            interval=f"{period}m",
            adjust="",
        )
        fetch_stats = None
        if not bars and allow_fetch_missing:
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

        return {
            "symbol": symbol,
            "interval": f"{period}m",
            "adjust": "",
            "cache_hit": bool(bars),
            "fetch_stats": fetch_stats,
            "bars": bars,
        }

    async def market_announcement(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = _optional_text(arguments.get("start"))
        end = _optional_text(arguments.get("end"))
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))

        announcements = await market_store.query_announcements_async(
            symbol=symbol,
            start=start,
            end=end,
        )
        fetch_stats = None
        if not announcements and allow_fetch_missing:
            if not start or not end:
                raise ValueError("start and end are required when allow_fetch_missing is true.")
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
            description="Read historical A-share bars from local cache, optionally fetching missing data.",
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
            description="Read A-share minute K-line bars from local cache, optionally fetching missing data.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "A-share stock code, e.g. 600000."},
                    "start": {"type": "string", "description": "Start datetime, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."},
                    "end": {"type": "string", "description": "End datetime, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."},
                    "period": {"type": "string", "enum": ["1", "5", "15", "30", "60"]},
                    "allow_fetch_missing": {"type": "boolean"},
                },
                "required": ["symbol", "start", "end"],
                "additionalProperties": False,
            },
            handler=market_minute,
            strict=True,
        ),
        ToolSpec(
            name="market_announcement",
            display_name="market.announcement",
            description="Search A-share company announcements/notices from the local cache, optionally fetching missing data.",
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
