from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_market_provider, get_market_store

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/history")
async def history(
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

    if not bars and allow_fetch_missing:
        if not start or not end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start and end are required when allow_fetch_missing is true.",
            )
        try:
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
        except NotImplementedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": symbol,
        "interval": interval,
        "adjust": adjust,
        "cache_hit": bool(bars),
        "fetch_stats": fetch_stats,
        "bars": bars,
    }


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result


@router.get("/minute")
async def minute(
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

    if not bars and allow_fetch_missing:
        try:
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
                interval=interval,
                adjust="",
            )
        except NotImplementedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": symbol,
        "interval": interval,
        "adjust": "",
        "cache_hit": bool(bars),
        "fetch_stats": fetch_stats,
        "bars": bars,
    }


@router.get("/announcement")
async def announcement(
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
        except NotImplementedError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": symbol,
        "cache_hit": bool(announcements),
        "fetch_stats": fetch_stats,
        "announcements": announcements,
    }


_VALID_MINUTE_PERIODS = {"1", "5", "15", "30", "60"}


def _validate_minute_period(period: str) -> None:
    period = str(period).strip()
    if period not in _VALID_MINUTE_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported period: {period!r}. Choose from {sorted(_VALID_MINUTE_PERIODS)}.",
        )
