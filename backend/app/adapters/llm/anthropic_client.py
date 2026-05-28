"""AnthropicLLM (T044) — Layer 3 adapter implementing LLMClient.

Stub for Phase 2; full tool-calling implementation lives in Slice B / US1.
Uses the Anthropic Python SDK. Model is configurable; default is
claude-sonnet-4-6 per plan.md (hosted API, no torch).
"""

from __future__ import annotations

import anthropic

from app.use_cases.protocols.llm_client import LLMResponse, LLMClient, Message, ToolSpec


class AnthropicLLM:
    """Implements use_cases.protocols.llm_client.LLMClient."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def call(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> LLMResponse:
        sdk_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

        sdk_tools = None
        if tools:
            sdk_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]

        kwargs: dict = dict(
            model=self._model,
            system=system,
            messages=sdk_messages,
            max_tokens=max_tokens,
        )
        if sdk_tools:
            kwargs["tools"] = sdk_tools

        response = await self._client.messages.create(**kwargs)

        text_content = ""
        tool_calls: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
        )
