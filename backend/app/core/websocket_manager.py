from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(channel)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(channel, None)

    async def send_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        await self._send_event(session_id, event)

    async def connect_account(self, account_id: str, websocket: WebSocket) -> None:
        await self.connect(_account_channel(account_id), websocket)

    async def disconnect_account(self, account_id: str, websocket: WebSocket) -> None:
        await self.disconnect(_account_channel(account_id), websocket)

    async def send_account_event(self, account_id: str, event: dict[str, Any]) -> None:
        await self._send_event(_account_channel(account_id), event)

    async def _send_event(self, channel: str, event: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(channel, set()))

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                connections = self._connections.get(channel)
                if connections:
                    for websocket in stale:
                        connections.discard(websocket)


def _account_channel(account_id: str) -> str:
    return f"account:{account_id}"
