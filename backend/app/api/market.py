from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_market_provider, get_market_store
from app.market.stock_data_logger import write_stock_data_api_log
from app.market.sync_service import MarketSyncService

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/history")
async def history(
    request: Request,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: Literal["daily"] = "daily",
    adjust: str = "",
    allow_fetch_missing: bool = False,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    bars = await market_store.query_history_async(
        symbol=symbol,
        start=start,
        end=end,
        interval=interval,
        adjust=adjust,
    )
    fetch_stats: dict[str, int] | None = None

    if allow_fetch_missing and not _covers_range(bars, start, end):
        if not start or not end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start and end are required when allow_fetch_missing is true.",
            )
        try:
            sync_service = MarketSyncService(request.app.state.store, market_store, market_provider)
            fetch_stats = await sync_service.ensure_history(symbol, start, end, interval, adjust)
            bars = await market_store.query_history_async(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust=adjust,
            )
        except NotImplementedError as exc:
            _log_market_api(
                "api.market.history",
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust=adjust,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(bars),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            _log_market_api(
                "api.market.history",
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust=adjust,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(bars),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    result = {
        "symbol": symbol,
        "interval": interval,
        "adjust": adjust,
        "cache_hit": bool(bars),
        "fetch_stats": fetch_stats,
        "bars": bars,
    }
    _log_market_api(
        "api.market.history",
        symbol=symbol,
        start=start,
        end=end,
        interval=interval,
        adjust=adjust,
        allow_fetch_missing=allow_fetch_missing,
        cache_hit=bool(bars),
        fetch_stats=fetch_stats,
        rows=len(bars),
    )
    return result


@router.get("/quote")
async def quote(
    symbol: str,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    try:
        result = await market_provider.quote(symbol)
        await market_store.insert_quote_async(result)
    except LookupError as exc:
        _log_market_api("api.market.quote", symbol=symbol, ok=False, error=exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        _log_market_api("api.market.quote", symbol=symbol, ok=False, error=exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    _log_market_api(
        "api.market.quote",
        symbol=symbol,
        source=result.get("source"),
        has_price=result.get("price") is not None,
        stored=True,
    )
    return result


@router.get("/minute")
async def minute(
    request: Request,
    symbol: str,
    start: str,
    end: str,
    period: str = "1",
    allow_fetch_missing: bool = False,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    _validate_minute_period(period)
    interval = f"{period}m"
    bars = await market_store.query_history_async(
        symbol=symbol,
        start=start,
        end=end,
        interval=interval,
        adjust="",
    )
    fetch_stats: dict[str, int] | None = None

    if allow_fetch_missing and not _covers_range(bars, start, end):
        try:
            sync_service = MarketSyncService(request.app.state.store, market_store, market_provider)
            fetch_stats = await sync_service.ensure_minute(symbol, start, end, period=period)
            bars = await market_store.query_history_async(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                adjust="",
            )
        except NotImplementedError as exc:
            _log_market_api(
                "api.market.minute",
                symbol=symbol,
                start=start,
                end=end,
                period=period,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(bars),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            _log_market_api(
                "api.market.minute",
                symbol=symbol,
                start=start,
                end=end,
                period=period,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(bars),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            _log_market_api(
                "api.market.minute",
                symbol=symbol,
                start=start,
                end=end,
                period=period,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(bars),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    result = {
        "symbol": symbol,
        "interval": interval,
        "adjust": "",
        "cache_hit": bool(bars),
        "fetch_stats": fetch_stats,
        "bars": bars,
    }
    _log_market_api(
        "api.market.minute",
        symbol=symbol,
        start=start,
        end=end,
        period=period,
        allow_fetch_missing=allow_fetch_missing,
        cache_hit=bool(bars),
        fetch_stats=fetch_stats,
        rows=len(bars),
    )
    return result


@router.get("/announcement")
async def announcement(
    request: Request,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    allow_fetch_missing: bool = False,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    announcements = await market_store.query_announcements_async(
        symbol=symbol,
        start=start,
        end=end,
    )
    fetch_stats: dict[str, int] | None = None

    if not announcements and allow_fetch_missing:
        if not start or not end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start and end are required when allow_fetch_missing is true.",
            )
        try:
            sync_service = MarketSyncService(request.app.state.store, market_store, market_provider)
            fetch_stats = await sync_service.ensure_announcements(symbol, start, end)
            announcements = await market_store.query_announcements_async(
                symbol=symbol,
                start=start,
                end=end,
            )
        except NotImplementedError as exc:
            _log_market_api(
                "api.market.announcement",
                symbol=symbol,
                start=start,
                end=end,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(announcements),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            _log_market_api(
                "api.market.announcement",
                symbol=symbol,
                start=start,
                end=end,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(announcements),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            _log_market_api(
                "api.market.announcement",
                symbol=symbol,
                start=start,
                end=end,
                allow_fetch_missing=allow_fetch_missing,
                cache_hit=bool(announcements),
                fetch_stats=fetch_stats,
                ok=False,
                error=exc,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    result = {
        "symbol": symbol,
        "cache_hit": bool(announcements),
        "fetch_stats": fetch_stats,
        "announcements": announcements,
    }
    _log_market_api(
        "api.market.announcement",
        symbol=symbol,
        start=start,
        end=end,
        allow_fetch_missing=allow_fetch_missing,
        cache_hit=bool(announcements),
        fetch_stats=fetch_stats,
        rows=len(announcements),
    )
    return result


_VALID_MINUTE_PERIODS = {"1", "5", "15", "30", "60"}


def _validate_minute_period(period: str) -> None:
    period = str(period).strip()
    if period not in _VALID_MINUTE_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported period: {period!r}. Choose from {sorted(_VALID_MINUTE_PERIODS)}.",
        )


def _covers_range(rows: list[dict[str, object]], start: str | None, end: str | None) -> bool:
    if not rows or not start or not end:
        return bool(rows)
    first = str(rows[0].get("datetime") or "")
    last = str(rows[-1].get("datetime") or "")
    return first <= start and last >= end


def _log_market_api(event: str, ok: bool = True, error: object = None, **payload: object) -> None:
    write_stock_data_api_log(event, payload, ok=ok, error=error)
