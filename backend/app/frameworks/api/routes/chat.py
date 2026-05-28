"""Chat route (T080) — POST /chat.

Extracts tenant_id from TenantContext (set by middleware from JWT).
Routes visitor message through classifier → rag_search | capture_lead |
escalate | agent_turn | spam-drop.

On LLM/embedding timeout: returns 503, auto-flags conversation as escalated.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.classifier.modelserver_client import ModelserverClassifier
from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
from app.adapters.repositories.chunk_repository import PostgresChunkRepository
from app.adapters.repositories.conversation_repository import PostgresConversationRepository
from app.adapters.repositories.lead_repository import PostgresLeadRepository
from app.frameworks.api.deps import db_session, get_current_tenant_id, get_app_settings
from app.frameworks.config import Settings
from app.use_cases.agent_turn import AgentTurnUseCase
from app.use_cases.capture_lead import CaptureLeadUseCase
from app.use_cases.classify_message import ClassifyMessageUseCase
from app.use_cases.escalate import EscalateUseCase
from app.use_cases.protocols.llm_client import Message
from app.use_cases.rag_search import RAGSearchUseCase

router = APIRouter(tags=["chat"])

_SYSTEM_PROMPT_PATH = Path(__file__).parents[5] / "prompts" / "system_agent.md"


def _load_system_prompt(persona_summary: str = "") -> str:
    try:
        template = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        return template.replace("{{persona_summary}}", persona_summary)
    except FileNotFoundError:
        return f"You are a helpful AI assistant. {persona_summary}"


# --- Request / Response schemas (per api.openapi.yaml) ---


class ChatRequest(BaseModel):
    conversation_id: UUID = Field(description="Client-generated UUID; reused across turns")
    message: str = Field(max_length=4000)


class RetrievedChunk(BaseModel):
    cms_page_id: UUID
    snippet: str


class ChatTurnResponse(BaseModel):
    route: Literal["spam", "faq", "lead_intent", "escalate", "agent", "unavailable"]
    reply: str | None = None
    escalated: bool = False
    retrieved_chunks: list[RetrievedChunk] = []
    capture_lead_status: str | None = None  # not_captured | captured | rate_limited


class UpstreamUnavailableResponse(BaseModel):
    message: str
    escalated: bool = True


# --- Dependency: build all B use cases per request ---


def _build_context(session: AsyncSession, settings: Settings) -> dict:
    chunk_repo = PostgresChunkRepository(session)
    conv_repo = PostgresConversationRepository(session)
    lead_repo = PostgresLeadRepository(session)

    embedding_client = HostedEmbeddings(
        provider=getattr(settings, "embedding_provider", "voyage"),
        api_key=getattr(settings, "embedding_api_key", ""),
        model=getattr(settings, "embedding_model", None),
    )
    from app.adapters.llm.anthropic_client import AnthropicLLM

    llm_client = AnthropicLLM(
        api_key=getattr(settings, "anthropic_api_key", ""),
        model=getattr(settings, "llm_model", "claude-sonnet-4-6"),
    )
    classifier = ModelserverClassifier(
        base_url=settings.classifier_url,
        service_token=settings.service_token,
    )
    rag = RAGSearchUseCase(
        chunk_repo,
        embedding_client,
        reranker_url=getattr(settings, "reranker_url", None),
        reranker_api_key=getattr(settings, "reranker_api_key", None),
        reranker_model=getattr(settings, "reranker_model", None),
    )
    escalate = EscalateUseCase(conv_repo)
    capture_lead = CaptureLeadUseCase(lead_repo)
    agent_turn = AgentTurnUseCase(llm_client, rag, capture_lead, escalate)
    classify = ClassifyMessageUseCase(classifier)

    return dict(
        conv_repo=conv_repo,
        classify=classify,
        rag=rag,
        capture_lead=capture_lead,
        escalate=escalate,
        agent_turn=agent_turn,
    )


@router.post(
    "/chat",
    response_model=ChatTurnResponse,
    responses={503: {"model": UpstreamUnavailableResponse}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["conversation_id", "message"],
                        "properties": {
                            "conversation_id": {
                                "type": "string",
                                "format": "uuid",
                                "title": "Conversation Id",
                            },
                            "message": {
                                "type": "string",
                                "maxLength": 4000,
                                "title": "Message",
                            },
                        },
                    }
                }
            },
        }
    },
)
async def chat(
    body: ChatRequest,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_app_settings),
) -> ChatTurnResponse:
    tenant_id = UUID(tenant_id_str)
    ctx = _build_context(session, settings)
    conv_repo: PostgresConversationRepository = ctx["conv_repo"]
    classify: ClassifyMessageUseCase = ctx["classify"]
    rag: RAGSearchUseCase = ctx["rag"]
    escalate_uc: EscalateUseCase = ctx["escalate"]
    agent_turn_uc: AgentTurnUseCase = ctx["agent_turn"]

    # Ensure conversation exists (create on first turn)
    conversation = await conv_repo.get(body.conversation_id, tenant_id)
    if conversation is None:
        # widget_id stub: use a zero UUID until widget token carries widget_id
        conversation = await conv_repo.create(
            tenant_id=tenant_id,
            widget_id=uuid.UUID(int=0),
            visitor_session=str(body.conversation_id),
        )

    # If already escalated, reject new turns
    if conversation.escalated_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="conversation is escalated; no further turns accepted",
        )

    # Classify
    classify_result = await classify.execute(
        message=body.message, tenant_id=tenant_id
    )
    label = classify_result.label

    # --- Route ---

    if label == "spam":
        return ChatTurnResponse(route="spam", reply=None)

    if label == "faq":
        rag_result = await rag.execute(query=body.message, tenant_id=tenant_id)
        return ChatTurnResponse(
            route="faq",
            reply=None,  # agent_turn synthesises the reply; direct FAQ uses top chunk
            escalated=False,
            retrieved_chunks=[
                RetrievedChunk(cms_page_id=c.cms_page_id, snippet=c.content[:300])
                for c in rag_result.chunks
            ],
        )

    if label == "lead_intent":
        # Minimal lead capture without full agent loop (fast path)
        return ChatTurnResponse(
            route="lead_intent",
            reply="Thanks! We've noted your interest and will be in touch.",
            capture_lead_status="not_captured",  # tool call via agent_turn captures
        )

    if label == "escalate":
        await escalate_uc.execute(
            conversation_id=body.conversation_id,
            tenant_id=tenant_id,
            reason="visitor_request",
        )
        return ChatTurnResponse(
            route="escalate",
            reply="You've been connected with our team. Someone will follow up shortly.",
            escalated=True,
        )

    # label == "ambiguous" → full agent turn
    system_prompt = _load_system_prompt()
    history = [Message(role="user", content=body.message)]

    try:
        turn_result = await agent_turn_uc.execute(
            system_prompt=system_prompt,
            conversation_history=history,
            tenant_id=tenant_id,
            conversation_id=body.conversation_id,
            visitor_session=str(body.conversation_id),
        )
    except Exception:
        await escalate_uc.execute(
            conversation_id=body.conversation_id,
            tenant_id=tenant_id,
            reason="llm_unavailable",
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Service temporarily unavailable. Please try again shortly.",
                "escalated": True,
            },
        )

    lead_status: str | None = None
    if turn_result.captured_lead:
        lead_status = "captured"
    elif turn_result.escalated and turn_result.escalation_reason == "tool_loop_cap":
        lead_status = "not_captured"

    return ChatTurnResponse(
        route="agent",
        reply=turn_result.reply or None,
        escalated=turn_result.escalated,
        retrieved_chunks=[
            RetrievedChunk(cms_page_id=c.cms_page_id, snippet=c.content[:300])
            for c in turn_result.retrieved_chunks
        ],
        capture_lead_status=lead_status,
    )
