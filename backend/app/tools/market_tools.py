from __future__ import annotations

from typing import Any

from app.tools.registry import ToolSpec


def create_market_tool_specs(market_store: Any, market_provider: Any) -> list[ToolSpec]:
    async def market_quote(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        quote = await market_provider.quote(symbol)
        market_store.insert_quote(quote)
        return quote

    async def market_history(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = str(arguments["symbol"])
        start = _optional_text(arguments.get("start"))
        end = _optional_text(arguments.get("end"))
        interval = str(arguments.get("interval") or "daily")
        adjust = str(arguments.get("adjust") or "")
        allow_fetch_missing = bool(arguments.get("allow_fetch_missing", False))

        bars = market_store.query_history(
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
            fetch_stats = market_store.insert_bars(fetched)
            bars = market_store.query_history(
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
        stats = market_store.insert_bars(fetched)
        return {
            "symbol": symbol,
            "interval": interval,
            "adjust": adjust,
            "fetched": len(fetched),
            **stats,
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
