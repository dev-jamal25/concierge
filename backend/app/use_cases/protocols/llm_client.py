"""LLMClient protocol (T025) — Layer 2 interface.

Owner B publishes this seam. The concrete adapter (AnthropicLLM) lives in
adapters/llm/; no use case imports it directly.

ToolSpec mirrors the Anthropic tool schema shape so adapters can pass it
through without translation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema object


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]]  # raw tool-call payloads from the model
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"


class LLMClient(Protocol):
    async def call(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> LLMResponse: ...
