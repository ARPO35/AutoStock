from fastapi import Request

from app.storage.sqlite import SQLiteStore


def get_store(request: Request) -> SQLiteStore:
    return request.app.state.store


def get_market_store(request: Request):
    return request.app.state.market_store


def get_market_provider(request: Request):
    return request.app.state.market_provider
