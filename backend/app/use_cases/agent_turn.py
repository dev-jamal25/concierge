"""AgentTurnUseCase (T077) — Layer 2.

Bounded tool-calling loop:
  - max_iterations = 5 (tool_loop_cap on breach)
  - max_tokens = 2048
  - tools: rag_search, capture_lead, escalate

Loop terminates on stop_reason == "end_turn", max_iterations, or a stop token.
On LLM timeout, auto-escalates with reason="llm_unavailable" and returns 503.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from uuid import UUID

from app.entities.chunk import Chunk
from app.entities.lead import Lead
from app.use_cases.capture_lead import CaptureLeadUseCase
from app.use_cases.escalate import EscalateUseCase
from app.use_cases.protocols.embedding_client import EmbeddingClient
from app.use_cases.protocols.llm_client import LLMClient, Message, ToolSpec
from app.use_cases.rag_search import RAGSearchUseCase

_MAX_ITERATIONS = 5
_MAX_TOKENS = 2048
_OSCILLATION_THRESHOLD = 0.95


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

_TOOL_SPECS = [
    ToolSpec(
        name="rag_search",
        description="Search the tenant's published knowledge base for relevant content.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="capture_lead",
        description="Capture a visitor's contact details and stated intent.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "contact": {"type": "string"},
                "intent": {"type": "string"},
            },
            "required": ["contact", "intent"],
        },
    ),
    ToolSpec(
        name="escalate",
        description="Flag this conversation for human follow-up.",
        input_schema={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    ),
]


@dataclass
class AgentTurnResult:
    reply: str
    escalated: bool = False
    escalation_reason: str | None = None
    retrieved_chunks: list[Chunk] = field(default_factory=list)
    captured_lead: Lead | None = None
    iterations: int = 0


class AgentTurnUseCase:
    def __init__(
        self,
        llm_client: LLMClient,
        rag_search: RAGSearchUseCase,
        capture_lead: CaptureLeadUseCase,
        escalate: EscalateUseCase,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._llm = llm_client
        self._rag = rag_search
        self._capture_lead = capture_lead
        self._escalate = escalate
        self._embedder = embedding_client

    async def execute(
        self,
        *,
        system_prompt: str,
        conversation_history: list[Message],
        tenant_id: UUID,
        conversation_id: UUID,
        visitor_session: str,
    ) -> AgentTurnResult:
        messages = list(conversation_history)
        result = AgentTurnResult(reply="")
        all_chunks: list[Chunk] = []
        last_rag_embedding: list[float] | None = None

        for iteration in range(_MAX_ITERATIONS):
            result.iterations = iteration + 1
            try:
                response = await self._llm.call(
                    system=system_prompt,
                    messages=messages,
                    tools=_TOOL_SPECS,
                    max_tokens=_MAX_TOKENS,
                )
            except Exception:
                await self._escalate.execute(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    reason="llm_unavailable",
                )
                result.escalated = True
                result.escalation_reason = "llm_unavailable"
                return result

            if response.stop_reason == "end_turn" or not response.tool_calls:
                result.reply = response.content
                result.retrieved_chunks = all_chunks
                return result

            # Process tool calls
            tool_results: list[dict] = []
            for call in response.tool_calls:
                tool_name = call["name"]
                tool_input = call["input"]
                call_id = call["id"]

                if tool_name == "rag_search":
                    # Oscillation detection (T186): consecutive near-identical queries → force-escalate
                    if self._embedder is not None and last_rag_embedding is not None:
                        current_emb = (await self._embedder.embed([tool_input["query"]]))[0]
                        if _cosine(last_rag_embedding, current_emb) >= _OSCILLATION_THRESHOLD:
                            await self._escalate.execute(
                                conversation_id=conversation_id,
                                tenant_id=tenant_id,
                                reason="tool_loop_cap",
                            )
                            result.escalated = True
                            result.escalation_reason = "tool_loop_cap"
                            result.retrieved_chunks = all_chunks
                            return result
                        last_rag_embedding = current_emb
                    elif self._embedder is not None:
                        last_rag_embedding = (await self._embedder.embed([tool_input["query"]]))[0]

                    rag_result = await self._rag.execute(
                        query=tool_input["query"], tenant_id=tenant_id
                    )
                    all_chunks.extend(rag_result.chunks)
                    tool_results.append({
                        "id": call_id,
                        "content": json.dumps([
                            {"content": c.content, "cms_page_id": str(c.cms_page_id)}
                            for c in rag_result.chunks
                        ]),
                    })

                elif tool_name == "capture_lead":
                    capture_result = await self._capture_lead.execute(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        visitor_session=visitor_session,
                        name=tool_input.get("name"),
                        contact=tool_input["contact"],
                        intent=tool_input["intent"],
                    )
                    if capture_result.lead:
                        result.captured_lead = capture_result.lead
                    tool_results.append({
                        "id": call_id,
                        "content": json.dumps({"status": capture_result.status}),
                    })

                elif tool_name == "escalate":
                    await self._escalate.execute(
                        conversation_id=conversation_id,
                        tenant_id=tenant_id,
                        reason="visitor_request",
                    )
                    result.escalated = True
                    result.escalation_reason = "visitor_request"
                    tool_results.append({
                        "id": call_id,
                        "content": json.dumps({"escalated": True}),
                    })

            # Append assistant + tool results to message history
            messages.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for tr in tool_results:
                messages.append(Message(role="tool", content=tr["content"], tool_call_id=tr["id"]))

        # Hit iteration cap
        await self._escalate.execute(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            reason="tool_loop_cap",
        )
        result.escalated = True
        result.escalation_reason = "tool_loop_cap"
        result.retrieved_chunks = all_chunks
        return result
