from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolTestRequest(BaseModel):
    arguments: dict[str, Any]


class ToolTestResponse(BaseModel):
    ok: bool
    content: str
    result: dict[str, Any] | None = None
    error: str | None = None


def get_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry


@router.get("")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    return [tool.public_schema() for tool in get_registry(request).list()]


@router.post("/{tool_name}/test", response_model=ToolTestResponse)
async def test_tool(tool_name: str, payload: ToolTestRequest, request: Request) -> ToolTestResponse:
    executor = ToolExecutor(get_registry(request))
    result = await executor.execute(tool_name, json.dumps(payload.arguments, ensure_ascii=False))
    return ToolTestResponse(
        ok=result.ok,
        content=result.content(),
        result=result.result,
        error=result.error,
    )
