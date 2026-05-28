"""Chat route (T080) — POST /chat.

Extracts tenant_id from TenantContext (set by middleware from JWT).
Routes visitor message through classifier → rag_search | capture_lead |
escalate | agent_turn | spam-drop.

On LLM/embedding timeout: returns 503, auto-flags conversation as escalated.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from jinja2 import Template
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.classifier.modelserver_client import ModelserverClassifier
from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
from app.adapters.llm.anthropic_client import AnthropicLLM
from app.adapters.repositories.chunk_repository import PostgresChunkRepository
from app.adapters.repositories.conversation_repository import PostgresConversationRepository
from app.adapters.repositories.lead_repository import PostgresLeadRepository
from app.frameworks.db.models import TenantModel
from app.frameworks.api.deps import db_session, get_current_tenant_id, get_app_settings, get_session_store
from app.frameworks.config import Settings
from app.use_cases.agent_turn import AgentTurnUseCase
from app.use_cases.capture_lead import CaptureLeadUseCase
from app.use_cases.classify_message import ClassifyMessageUseCase
from app.use_cases.escalate import EscalateUseCase
from app.use_cases.protocols.llm_client import Message
from app.use_cases.protocols.session_store import SessionStore
from app.use_cases.rag_search import RAGSearchUseCase
from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase
from app.use_cases.session_memory import SessionMemory

router = APIRouter(tags=["chat"])

_SYSTEM_PROMPT_PATH = Path(__file__).parents[5] / "prompts" / "system_agent.md"


def _load_system_prompt(persona_summary: str = "") -> str:
    try:
        source = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        return Template(source).render(persona_summary=persona_summary)
    except FileNotFoundError:
        return f"You are a helpful AI assistant. {persona_summary}"


async def _get_persona_summary(tenant_id: UUID, session: AsyncSession) -> str:
    """Fetch persona_summary from tenant.persona_config at runtime (T126 / FR-025)."""
    result = await session.execute(
        select(TenantModel).where(TenantModel.id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return ""
    return (row.persona_config or {}).get("persona_summary", "")


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


def _build_context(session: AsyncSession, settings: Settings, session_store: SessionStore) -> dict:
    chunk_repo = PostgresChunkRepository(session)
    conv_repo = PostgresConversationRepository(session)
    lead_repo = PostgresLeadRepository(session)

    embedding_client = HostedEmbeddings(
        provider=getattr(settings, "embedding_provider", "voyage"),
        api_key=getattr(settings, "embedding_api_key", ""),
        model=getattr(settings, "embedding_model", None),
    )
    llm_client = AnthropicLLM(
        api_key=getattr(settings, "anthropic_api_key", ""),
        model=getattr(settings, "llm_model", "claude-sonnet-4-6"),
    )
    classifier = ModelserverClassifier(
        base_url=settings.classifier_url,
        service_token=settings.service_token,
    )
    reindex = ReindexTenantChunksUseCase(chunk_repo, embedding_client)
    rag = RAGSearchUseCase(
        chunk_repo,
        embedding_client,
        reranker_url=getattr(settings, "reranker_url", None),
        reranker_api_key=getattr(settings, "reranker_api_key", None),
        reranker_model=getattr(settings, "reranker_model", None),
    )
    escalate = EscalateUseCase(conv_repo)
    capture_lead = CaptureLeadUseCase(lead_repo)
    agent_turn = AgentTurnUseCase(llm_client, rag, capture_lead, escalate, embedding_client)
    classify = ClassifyMessageUseCase(classifier)
    memory = SessionMemory(
        session_store,
        ttl=settings.session_ttl_seconds,
        max_messages=settings.session_max_messages,
    )

    return dict(
        conv_repo=conv_repo,
        classify=classify,
        rag=rag,
        capture_lead=capture_lead,
        escalate=escalate,
        agent_turn=agent_turn,
        memory=memory,
    )


@router.post(
    "/chat",
    response_model=ChatTurnResponse,
    responses={503: {"model": UpstreamUnavailableResponse, "description": "LLM unavailable; conversation escalated"}},
)
async def chat(
    body: ChatRequest,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_app_settings),
    session_store: SessionStore = Depends(get_session_store),
) -> ChatTurnResponse:
    tenant_id = UUID(tenant_id_str)
    ctx = _build_context(session, settings, session_store)
    conv_repo: PostgresConversationRepository = ctx["conv_repo"]
    classify: ClassifyMessageUseCase = ctx["classify"]
    rag: RAGSearchUseCase = ctx["rag"]
    capture_lead_uc: CaptureLeadUseCase = ctx["capture_lead"]
    escalate_uc: EscalateUseCase = ctx["escalate"]
    agent_turn_uc: AgentTurnUseCase = ctx["agent_turn"]
    memory: SessionMemory = ctx["memory"]

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

    # Load prior session history before classify so it's available for all routes
    prior_turns = await memory.load(tenant_id, body.conversation_id)

    # Classify
    classify_result = await classify.execute(
        message=body.message, tenant_id=tenant_id
    )
    label = classify_result.label
    # Low-confidence override: fall through to full agent rather than a wrong fast path (T185)
    if classify_result.confidence < settings.router_confidence_threshold and label != "spam":
        label = "ambiguous"

    # --- Route ---

    if label == "spam":
        return ChatTurnResponse(route="spam", reply=None)

    if label == "faq":
        rag_result = await rag.execute(query=body.message, tenant_id=tenant_id)
        reply = None  # agent_turn synthesises the reply; direct FAQ uses top chunk
        await memory.append_turn(
            tenant_id, body.conversation_id, body.message, reply or ""
        )
        return ChatTurnResponse(
            route="faq",
            reply=reply,
            escalated=False,
            retrieved_chunks=[
                RetrievedChunk(cms_page_id=c.cms_page_id, snippet=c.content[:300])
                for c in rag_result.chunks
            ],
        )

    if label == "lead_intent":
        reply = "Thanks! We've noted your interest and will be in touch."
        await memory.append_turn(
            tenant_id, body.conversation_id, body.message, reply
        )
        return ChatTurnResponse(
            route="lead_intent",
            reply=reply,
            capture_lead_status="not_captured",  # tool call via agent_turn captures
        )

    if label == "escalate":
        await escalate_uc.execute(
            conversation_id=body.conversation_id,
            tenant_id=tenant_id,
            reason="visitor_request",
        )
        reply = "You've been connected with our team. Someone will follow up shortly."
        await memory.append_turn(
            tenant_id, body.conversation_id, body.message, reply
        )
        return ChatTurnResponse(
            route="escalate",
            reply=reply,
            escalated=True,
        )

    # label == "ambiguous" → full agent turn
    persona_summary = await _get_persona_summary(tenant_id, session)
    system_prompt = _load_system_prompt(persona_summary)
    # Build history: prior clean turns + current user message
    history = [
        Message(role=t["role"], content=t["content"]) for t in prior_turns
    ] + [Message(role="user", content=body.message)]

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

    # Persist the turn to session memory
    await memory.append_turn(
        tenant_id,
        body.conversation_id,
        body.message,
        turn_result.reply or "",
    )

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
