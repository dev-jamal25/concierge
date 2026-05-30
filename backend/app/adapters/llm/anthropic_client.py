"""AnthropicLLM (T044) — Layer 3 adapter implementing LLMClient.

Stub for Phase 2; full tool-calling implementation lives in Slice B / US1.
Uses the Anthropic Python SDK. Model is configurable; default is
claude-sonnet-4-6 per plan.md (hosted API, no torch).
"""

from __future__ import annotations

import anthropic

from app.use_cases.protocols.llm_client import LLMResponse, Message, ToolSpec


def _build_sdk_messages(messages: list[Message]) -> list[dict]:
    """Convert internal Message list to Anthropic SDK message format.

    Handles three cases that the naive {"role": m.role, "content": m.content}
    mapping misses:
      1. Assistant messages with tool_calls → content array with tool_use blocks.
      2. Messages with role="tool" → role="user" with tool_result blocks.
      3. Consecutive tool messages → batched into a single user message.
    """
    sdk: list[dict] = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.tool_calls:
            content: list[dict] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            sdk.append({"role": "assistant", "content": content})
        elif m.role == "tool":
            tool_results: list[dict] = []
            while i < len(messages) and messages[i].role == "tool":
                tr = messages[i]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tr.tool_call_id,
                    "content": tr.content,
                })
                i += 1
            sdk.append({"role": "user", "content": tool_results})
            continue
        else:
            sdk.append({"role": m.role, "content": m.content})
        i += 1
    return sdk


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
        sdk_messages = _build_sdk_messages(messages)

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
