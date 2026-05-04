from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_store
from app.simulator.engine import SimulatorEngine
from app.simulator.rules import TradingRuleError
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_simulator_engine(request: Request) -> SimulatorEngine:
    return request.app.state.simulator_engine


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    initial_cash: float = Field(default=1_000_000, ge=0)
    commission_rate: float = Field(default=0.00025, ge=0, le=0.01)
    min_commission: float = Field(default=5.0, ge=0)


class AccountUpdate(BaseModel):
    name: str | None = None
    commission_rate: float | None = Field(default=None, ge=0, le=0.01)
    min_commission: float | None = Field(default=None, ge=0)


@router.get("/accounts")
async def list_accounts(
    store: SQLiteStore = Depends(get_store),
) -> list[dict[str, object]]:
    return store.fetch_all(
        """
        SELECT *
        FROM simulator_accounts
        ORDER BY created_at DESC
        """
    )


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> dict[str, object]:
    try:
        return engine.create_account(
            name=payload.name,
            initial_cash=payload.initial_cash,
            commission_rate=payload.commission_rate,
            min_commission=payload.min_commission,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> dict[str, object]:
    return _get_account_or_404(engine, account_id)


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: str,
    payload: AccountUpdate,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> dict[str, object]:
    try:
        return engine.update_account(
            account_id=account_id,
            name=payload.name,
            commission_rate=payload.commission_rate,
            min_commission=payload.min_commission,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: str,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> None:
    _get_account_or_404(engine, account_id)
    engine.delete_account(account_id)


@router.get("/accounts/{account_id}/positions")
async def account_positions(
    account_id: str,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> list[dict[str, object]]:
    _get_account_or_404(engine, account_id)
    return engine.get_positions(account_id)


@router.get("/accounts/{account_id}/orders")
async def account_orders(
    account_id: str,
    status_filter: str | None = None,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> list[dict[str, object]]:
    _get_account_or_404(engine, account_id)
    return engine.get_orders(account_id, status_filter)


@router.get("/accounts/{account_id}/trades")
async def account_trades(
    account_id: str,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> list[dict[str, object]]:
    _get_account_or_404(engine, account_id)
    return engine.get_trades(account_id)


@router.post("/accounts/{account_id}/reset")
async def reset_account(
    account_id: str,
    engine: SimulatorEngine = Depends(get_simulator_engine),
) -> dict[str, object]:
    _get_account_or_404(engine, account_id)
    return engine.reset_account(account_id)


def _get_account_or_404(engine: SimulatorEngine, account_id: str) -> dict[str, object]:
    try:
        return engine.get_account(account_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
