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
    bars = market_store.query_history(symbol=symbol, start=start, end=end, interval=interval, adjust=adjust)
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
            fetch_stats = market_store.insert_bars(fetched)
            bars = market_store.query_history(
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
        market_store.insert_quote(result)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result
