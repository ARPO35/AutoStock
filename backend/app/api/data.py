from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_market_provider, get_market_store

router = APIRouter(prefix="/api/data", tags=["data"])


class FetchHistoryRequest(BaseModel):
    symbol: str = Field(min_length=1)
    start: str = Field(min_length=8)
    end: str = Field(min_length=8)
    interval: Literal["daily"] = "daily"
    adjust: str = ""


class FetchHistoryResponse(BaseModel):
    symbol: str
    interval: str
    adjust: str
    fetched: int
    inserted: int
    skipped: int
    conflicted: int


class ConflictResolveRequest(BaseModel):
    status: Literal["resolved", "ignored"]


@router.post("/fetch-history", response_model=FetchHistoryResponse)
async def fetch_history(
    payload: FetchHistoryRequest,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    try:
        bars = await market_provider.history(
            symbol=payload.symbol,
            start=payload.start,
            end=payload.end,
            interval=payload.interval,
            adjust=payload.adjust,
        )
        stats = await market_store.insert_bars_async(bars)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": payload.symbol,
        "interval": payload.interval,
        "adjust": payload.adjust,
        "fetched": len(bars),
        **stats,
    }


@router.get("/cache-status")
async def cache_status(
    symbol: str | None = None,
    interval: str | None = None,
    market_store=Depends(get_market_store),
) -> list[dict[str, object]]:
    return await market_store.cache_status_async(symbol=symbol, interval=interval)


@router.get("/conflicts")
async def list_conflicts(
    status_filter: str | None = None,
    market_store=Depends(get_market_store),
) -> list[dict[str, object]]:
    return await market_store.list_conflicts_async(status=status_filter)


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolveRequest,
    market_store=Depends(get_market_store),
) -> dict[str, object]:
    conflict = await market_store.resolve_conflict_async(
        conflict_id=conflict_id,
        status=payload.status,
    )
    if conflict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
    return conflict


class FetchMinuteRequest(BaseModel):
    symbol: str = Field(min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    period: str = "1"


class FetchMinuteResponse(BaseModel):
    symbol: str
    interval: str
    adjust: str
    fetched: int
    inserted: int
    skipped: int
    conflicted: int


class FetchAnnouncementRequest(BaseModel):
    symbol: str = Field(min_length=1)
    start: str = Field(min_length=8)
    end: str = Field(min_length=8)


class FetchAnnouncementResponse(BaseModel):
    symbol: str
    fetched: int
    inserted: int
    skipped: int
    conflicted: int


@router.post("/fetch-minute", response_model=FetchMinuteResponse)
async def fetch_minute(
    payload: FetchMinuteRequest,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    try:
        bars = await market_provider.minute(
            symbol=payload.symbol,
            start=payload.start,
            end=payload.end,
            period=payload.period,
        )
        stats = await market_store.insert_bars_async(bars)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": payload.symbol,
        "interval": f"{payload.period}m",
        "adjust": "",
        "fetched": len(bars),
        **stats,
    }


@router.post("/fetch-announcement", response_model=FetchAnnouncementResponse)
async def fetch_announcement(
    payload: FetchAnnouncementRequest,
    market_store=Depends(get_market_store),
    market_provider=Depends(get_market_provider),
) -> dict[str, object]:
    try:
        announcements = await market_provider.announcement(
            symbol=payload.symbol,
            start=payload.start,
            end=payload.end,
        )
        stats = await market_store.insert_announcements_async(announcements)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "symbol": payload.symbol,
        "fetched": len(announcements),
        **stats,
    }
