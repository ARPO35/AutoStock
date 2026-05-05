from __future__ import annotations

from typing import Any

from app.tavily_service import TavilyService
from app.tools.registry import ToolSpec


def create_tavily_tool_specs(tavily_service: TavilyService) -> list[ToolSpec]:
    async def tavily_search(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await tavily_service.search(arguments, runtime_context=runtime_context)

    async def tavily_extract(
        arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await tavily_service.extract(arguments, runtime_context=runtime_context)

    return [
        ToolSpec(
            name="tavily_search",
            display_name="tavily.search",
            description="搜索实时网页信息，用于股票新闻、政策、行业事件分析。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词。"},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"]},
                    "topic": {"type": "string", "enum": ["general", "news", "finance"]},
                    "time_range": {"type": "string", "enum": ["day", "week", "month", "year", "d", "w", "m", "y"]},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD。"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD。"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=tavily_search,
            strict=True,
        ),
        ToolSpec(
            name="tavily_extract",
            display_name="tavily.extract",
            description="抽取指定网页正文内容，常用于继续阅读 tavily.search 返回的链接。",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 20,
                    },
                    "extract_depth": {"type": "string", "enum": ["basic", "advanced"]},
                    "format": {"type": "string", "enum": ["markdown", "text"]},
                    "query": {"type": "string", "description": "可选的抽取内容重排意图。"},
                },
                "required": ["urls"],
                "additionalProperties": False,
            },
            handler=tavily_extract,
            strict=True,
        ),
    ]
