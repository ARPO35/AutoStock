from fastapi import Request

from app.storage.sqlite import SQLiteStore


def get_store(request: Request) -> SQLiteStore:
    return request.app.state.store
