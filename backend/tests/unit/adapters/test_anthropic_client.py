"""Unit tests for AnthropicLLM SDK message formatting."""

from __future__ import annotations

from app.adapters.llm.anthropic_client import _build_sdk_messages
from app.use_cases.protocols.llm_client import Message


def test_plain_user_and_assistant_messages_pass_through() -> None:
    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there"),
    ]
    result = _build_sdk_messages(messages)
    assert result == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]


def test_assistant_with_tool_calls_becomes_content_array() -> None:
    """Assistant message with tool_calls must use content array with tool_use blocks."""
    messages = [
        Message(
            role="assistant",
            content="Let me search.",
            tool_calls=[{"id": "tc_1", "name": "rag_search", "input": {"query": "coffee"}}],
        )
    ]
    result = _build_sdk_messages(messages)
    assert result == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me search."},
                {"type": "tool_use", "id": "tc_1", "name": "rag_search", "input": {"query": "coffee"}},
            ],
        }
    ]


def test_assistant_with_tool_calls_and_no_text_omits_text_block() -> None:
    """If the assistant sent no text (only tool calls), don't include an empty text block."""
    messages = [
        Message(
            role="assistant",
            content="",
            tool_calls=[{"id": "tc_1", "name": "rag_search", "input": {"query": "coffee"}}],
        )
    ]
    result = _build_sdk_messages(messages)
    assert result == [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tc_1", "name": "rag_search", "input": {"query": "coffee"}},
            ],
        }
    ]


def test_tool_role_becomes_user_with_tool_result_block() -> None:
    """role='tool' must become role='user' with a tool_result content block."""
    messages = [
        Message(role="tool", content='{"chunks":[]}', tool_call_id="tc_1"),
    ]
    result = _build_sdk_messages(messages)
    assert result == [
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tc_1", "content": '{"chunks":[]}'}],
        }
    ]


def test_consecutive_tool_messages_batched_into_single_user_message() -> None:
    """Multiple consecutive tool results must be batched into one user message."""
    messages = [
        Message(role="tool", content="result_a", tool_call_id="tc_1"),
        Message(role="tool", content="result_b", tool_call_id="tc_2"),
    ]
    result = _build_sdk_messages(messages)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert len(result[0]["content"]) == 2
    assert result[0]["content"][0] == {"type": "tool_result", "tool_use_id": "tc_1", "content": "result_a"}
    assert result[0]["content"][1] == {"type": "tool_result", "tool_use_id": "tc_2", "content": "result_b"}


def test_full_multi_turn_tool_use_sequence() -> None:
    """Full realistic sequence: user → assistant+tool_call → tool_result → assistant."""
    messages = [
        Message(role="user", content="What coffees do you sell?"),
        Message(
            role="assistant",
            content="Let me search.",
            tool_calls=[{"id": "tc_1", "name": "rag_search", "input": {"query": "coffees"}}],
        ),
        Message(role="tool", content='[{"content":"We sell espresso"}]', tool_call_id="tc_1"),
    ]
    result = _build_sdk_messages(messages)
    assert len(result) == 3
    assert result[0] == {"role": "user", "content": "What coffees do you sell?"}
    assert result[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in result[1]["content"])
    assert result[2]["role"] == "user"
    assert result[2]["content"][0]["type"] == "tool_result"
