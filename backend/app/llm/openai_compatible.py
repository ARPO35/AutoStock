from __future__ import annotations

from typing import Any

from app.llm.base import ChatMessage, ChatResponse, LLMProviderConfig, ToolCall, ToolDefinition


class OpenAICompatibleProvider:
    async def chat(
        self,
        config: LLMProviderConfig,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
    ) -> ChatResponse:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError("The openai package is required for LLM provider calls.") from exc

        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

        request: dict[str, Any] = {
            "model": config.model,
            "messages": [self._message_to_payload(message) for message in messages],
            "temperature": config.temperature,
        }
        if config.max_tokens is not None:
            request["max_tokens"] = config.max_tokens
        if tools and config.supports_tools:
            request["tools"] = [self._tool_to_payload(tool) for tool in tools]
            request["parallel_tool_calls"] = config.supports_parallel_tool_calls

        response = await client.chat.completions.create(**request)
        choice = response.choices[0]
        message = choice.message
        calls = []
        for call in message.tool_calls or []:
            calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=call.function.arguments,
                )
            )

        raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        usage = raw.get("usage") or {}
        return ChatResponse(content=message.content, tool_calls=calls, raw=raw, usage=usage)

    def _message_to_payload(self, message: ChatMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role}
        if message.content is not None:
            payload["content"] = message.content
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls is not None:
            payload["tool_calls"] = message.tool_calls
        return payload

    def _tool_to_payload(self, tool: ToolDefinition) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        if tool.strict:
            payload["function"]["strict"] = True
        return payload
