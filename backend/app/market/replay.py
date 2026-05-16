from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.simulator.replay_clock import parse_clock_time

REPLAY_QUOTE_MINUTE_LOOKBACK_DAYS = 7
REPLAY_QUOTE_DAILY_LOOKBACK_DAYS = 10
MARKET_OPEN_TIME = "09:30:00"


def is_replay_context(runtime_context: dict[str, Any] | None) -> bool:
    return bool(runtime_context and runtime_context.get("time_mode") == "replay")


def effective_datetime(runtime_context: dict[str, Any] | None) -> datetime:
    if not runtime_context or not runtime_context.get("effective_time"):
        raise ValueError("effective_time is required in replay runtime.")
    return parse_clock_time(str(runtime_context["effective_time"]))


def effective_time_text(runtime_context: dict[str, Any] | None, *, date_only: bool = False) -> str:
    dt = effective_datetime(runtime_context)
    return dt.date().isoformat() if date_only else dt.strftime("%Y-%m-%d %H:%M:%S")


def clamp_end_to_effective(
    end: str | None,
    runtime_context: dict[str, Any] | None,
    *,
    date_only: bool = False,
) -> str:
    effective = effective_time_text(runtime_context, date_only=date_only)
    if not end:
        return effective
    normalized = _normalize_end(end, date_only=date_only)
    return min(normalized, effective)


async def replay_quote_from_cache(
    market_store: Any,
    symbol: str,
    runtime_context: dict[str, Any] | None,
    market_provider: Any | None = None,
) -> dict[str, Any]:
    effective = effective_time_text(runtime_context)
    fetch_errors: list[str] = []
    minute_bar = await _latest_minute_bar(market_store, symbol, effective)
    if minute_bar is not None:
        return _quote_from_bar(minute_bar, effective, "replay.cache.minute")

    if market_provider is not None:
        try:
            await _fetch_replay_minute_bars(market_store, market_provider, symbol, runtime_context)
        except Exception as exc:
            fetch_errors.append(f"minute fetch failed: {exc}")
        minute_bar = await _latest_minute_bar(market_store, symbol, effective)
        if minute_bar is not None:
            return _quote_from_bar(minute_bar, effective, "replay.derived.minute")

    daily_bar = await _latest_daily_bar(market_store, symbol, effective)
    if daily_bar is not None:
        return _quote_from_bar(daily_bar, effective, "replay.cache.daily")

    if market_provider is not None:
        try:
            await _fetch_replay_daily_bars(market_store, market_provider, symbol, runtime_context)
        except Exception as exc:
            fetch_errors.append(f"daily fetch failed: {exc}")
        daily_bar = await _latest_daily_bar(market_store, symbol, effective)
        if daily_bar is not None:
            return _quote_from_bar(daily_bar, effective, "replay.derived.daily")

    reason = f" ({'; '.join(fetch_errors)})" if fetch_errors else ""
    raise ValueError(
        f"No cached quote bar for {symbol} at or before {effective}. "
        "Replay quote requires cached minute/daily bars or a provider that can fetch bars up to the replay time."
        f"{reason}"
    )


async def _latest_minute_bar(market_store: Any, symbol: str, effective: str) -> dict[str, Any] | None:
    return await market_store.latest_bar_async(
        symbol=symbol,
        end=effective,
        interval_like="%m",
        adjust="",
    )


async def _latest_daily_bar(market_store: Any, symbol: str, effective: str) -> dict[str, Any] | None:
    return await market_store.latest_bar_async(
        symbol=symbol,
        end=effective[:10],
        interval="daily",
        adjust="",
    )


async def _fetch_replay_minute_bars(
    market_store: Any,
    market_provider: Any,
    symbol: str,
    runtime_context: dict[str, Any] | None,
) -> None:
    effective = effective_datetime(runtime_context)
    start_date = effective.date() - timedelta(days=REPLAY_QUOTE_MINUTE_LOOKBACK_DAYS)
    fetched = await market_provider.minute(
        symbol=symbol,
        start=f"{start_date.isoformat()} {MARKET_OPEN_TIME}",
        end=effective.strftime("%Y-%m-%d %H:%M:%S"),
        period="1",
    )
    await market_store.insert_bars_async(fetched)


async def _fetch_replay_daily_bars(
    market_store: Any,
    market_provider: Any,
    symbol: str,
    runtime_context: dict[str, Any] | None,
) -> None:
    effective = effective_datetime(runtime_context)
    start_date = effective.date() - timedelta(days=REPLAY_QUOTE_DAILY_LOOKBACK_DAYS)
    fetched = await market_provider.history(
        symbol=symbol,
        start=start_date.isoformat(),
        end=effective.date().isoformat(),
        interval="daily",
        adjust="",
    )
    await market_store.insert_bars_async(fetched)


def _quote_from_bar(bar: dict[str, Any], effective: str, source: str) -> dict[str, Any]:
    close = _float_or_none(bar.get("close"))
    open_price = _float_or_none(bar.get("open"))
    return {
        "symbol": bar.get("symbol"),
        "name": bar.get("name") or "",
        "price": close,
        "open": open_price,
        "high": _float_or_none(bar.get("high")),
        "low": _float_or_none(bar.get("low")),
        "previous_close": open_price if open_price is not None else close,
        "volume": _float_or_none(bar.get("volume")) or 0,
        "amount": _float_or_none(bar.get("amount")) or 0,
        "source": source,
        "fetch_time": effective,
        "datetime": bar.get("datetime"),
        "raw_hash": bar.get("raw_hash") or "",
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_end(value: str, *, date_only: bool) -> str:
    text = str(value).strip()
    if date_only:
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text[:10]
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]} 23:59:59"
    if "T" in text:
        text = text.replace("T", " ")
    if len(text) == 10:
        return f"{text} 23:59:59"
    return text[:19]
