"""Chat route (T080) — POST /chat.

Extracts tenant_id from TenantContext (set by middleware from JWT).
Routes visitor message through classifier → rag_search | capture_lead |
escalate | agent_turn | spam-drop.

On LLM/embedding timeout: returns 503, auto-flags conversation as escalated.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from jinja2 import Template
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.classifier.modelserver_client import ModelserverClassifier
from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
from app.adapters.repositories.chunk_repository import PostgresChunkRepository
from app.adapters.repositories.conversation_repository import PostgresConversationRepository
from app.adapters.repositories.lead_repository import PostgresLeadRepository
from app.frameworks.api.deps import (
    WidgetTokenContext,
    db_session,
    get_app_settings,
    get_current_widget_context,
    get_guardrails_client,
    get_service_token,
    get_session_store,
)
from app.frameworks.config import Settings
from app.frameworks.db.models import TenantModel
from app.use_cases.agent_turn import AgentTurnUseCase
from app.use_cases.capture_lead import CaptureLeadUseCase
from app.use_cases.classify_message import ClassifyMessageUseCase
from app.use_cases.escalate import EscalateUseCase
from app.use_cases.protocols.llm_client import Message
from app.use_cases.protocols.session_store import SessionStore
from app.use_cases.rag_search import RAGSearchUseCase
from app.use_cases.session_memory import SessionMemory
from app.frameworks.observability.logging import log_turn_cost

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_SYSTEM_PROMPT_PATH = Path(__file__).parents[5] / "prompts" / "system_agent.md"

# Regex of business-domain keywords that indicate a legitimate FAQ query.
# When the ONNX classifier mislabels one of these as "spam", we override to "faq"
# so the message reaches agent_turn instead of being silently dropped.
_FAQ_KEYWORD_RE = re.compile(
    # No trailing \b — plurals/compounds like "coffees", "wi-fi", "take-away" must match.
    r"\b("
    r"coffee|espresso|latte|cappuccino|americano|flat\s+white|pour[- ]?over|drip|brew|roast|blend|bean|origin|"
    r"tea|cake|pastry|food|drink|beverage|menu|sandwich|milk|oat|almond|soy|decaf|"
    r"open|close|hour|location|address|where|parking|wi[- ]?fi|internet|"
    r"book|table|reservation|reserve|seat|catering|event|appointment|"
    r"price|cost|discount|loyalty|stamp|reward|offer|deal|"
    r"barista|service|staff|order|take[- ]?away|takeout|dine[- ]?in"
    r")",
    re.IGNORECASE,
)

_SPAM_REPLY = "I'm only able to help with questions about this business."


def _looks_like_faq(message: str) -> bool:
    """True when the message contains business-domain keywords.

    Prevents the classifier from silently dropping legitimate FAQ questions
    that happen to be misclassified as spam.
    """
    return bool(_FAQ_KEYWORD_RE.search(message))


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


@router.options("/chat", include_in_schema=False)
async def chat_options(origin: str | None = Header(default=None)) -> Response:
    if origin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing origin")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _allow_origin(response, origin)
    response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
    response.headers["Access-Control-Max-Age"] = "300"
    return response


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
    from app.adapters.llm.anthropic_client import AnthropicLLM

    llm_client = AnthropicLLM(
        api_key=getattr(settings, "anthropic_api_key", ""),
        model=getattr(settings, "llm_model", "claude-sonnet-4-6"),
    )
    classifier = ModelserverClassifier(
        base_url=settings.classifier_url,
        service_token=get_service_token(),
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
    agent_turn = AgentTurnUseCase(
        llm_client, rag, capture_lead, escalate, embedding_client,
        guardrails=get_guardrails_client(),
    )
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
    responses={
        503: {
            "model": UpstreamUnavailableResponse,
            "description": "LLM unavailable; conversation escalated",
        }
    },
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
    response: Response,
    widget_context: WidgetTokenContext = Depends(get_current_widget_context),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(get_app_settings),
    session_store: SessionStore = Depends(get_session_store),
) -> ChatTurnResponse:
    tenant_id = UUID(widget_context.tenant_id)
    widget_id = UUID(widget_context.widget_id)
    _allow_origin(response, widget_context.origin)
    ctx = _build_context(session, settings, session_store)
    conv_repo: PostgresConversationRepository = ctx["conv_repo"]
    classify: ClassifyMessageUseCase = ctx["classify"]
    escalate_uc: EscalateUseCase = ctx["escalate"]
    agent_turn_uc: AgentTurnUseCase = ctx["agent_turn"]
    memory: SessionMemory = ctx["memory"]

    # Ensure conversation exists (create on first turn)
    conversation = await conv_repo.get(body.conversation_id, tenant_id)
    if conversation is None:
        conversation = await conv_repo.create(
            tenant_id=tenant_id,
            widget_id=widget_id,
            visitor_session=str(body.conversation_id),
            conversation_id=body.conversation_id,
        )

    # If already escalated, reject new turns
    if conversation.escalated_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="conversation is escalated; no further turns accepted",
        )

    # Load prior session history before classify so it's available for all routes
    prior_turns = await memory.load(tenant_id, body.conversation_id)
    _t0 = time.perf_counter()

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
        # If the message contains business-domain keywords the classifier incorrectly
        # labelled it spam — fall through to faq so agent_turn can handle it.
        if _looks_like_faq(body.message):
            label = "faq"
        else:
            log_turn_cost(tenant_id=tenant_id, conversation_id=body.conversation_id,
                          route="spam", ms_elapsed=(time.perf_counter() - _t0) * 1000)
            return ChatTurnResponse(route="spam", reply=_SPAM_REPLY)

    if label == "faq":
        # Route through agent_turn so it can call rag_search as a tool and
        # synthesise a grounded reply from the tenant's knowledge base.
        persona_summary = await _get_persona_summary(tenant_id, session)
        system_prompt = _load_system_prompt(persona_summary)
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
        except Exception as _exc:
            logger.warning("agent_turn failed (faq route): %s: %s", type(_exc).__name__, _exc)
            try:
                await escalate_uc.execute(
                    conversation_id=body.conversation_id,
                    tenant_id=tenant_id,
                    reason="llm_unavailable",
                )
            except Exception:
                pass
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Service temporarily unavailable. Please try again shortly.",
                    "escalated": True,
                },
            )
        await memory.append_turn(
            tenant_id, body.conversation_id, body.message, turn_result.reply or ""
        )
        log_turn_cost(
            tenant_id=tenant_id,
            conversation_id=body.conversation_id,
            route="faq",
            embedding_calls=turn_result.iterations,
            ms_elapsed=(time.perf_counter() - _t0) * 1000,
            embedding_provider=getattr(settings, "embedding_provider", "voyage"),
        )
        return ChatTurnResponse(
            route="faq",
            reply=turn_result.reply or None,
            escalated=turn_result.escalated,
            retrieved_chunks=[
                RetrievedChunk(cms_page_id=c.cms_page_id, snippet=c.content[:300])
                for c in turn_result.retrieved_chunks
            ],
        )

    if label == "lead_intent":
        reply = "Thanks! We've noted your interest and will be in touch."
        await memory.append_turn(
            tenant_id, body.conversation_id, body.message, reply
        )
        log_turn_cost(tenant_id=tenant_id, conversation_id=body.conversation_id,
                      route="lead_intent", ms_elapsed=(time.perf_counter() - _t0) * 1000)
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
        log_turn_cost(tenant_id=tenant_id, conversation_id=body.conversation_id,
                      route="escalate", ms_elapsed=(time.perf_counter() - _t0) * 1000)
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
    except Exception as _exc:
        logger.warning("agent_turn failed (agent route): %s: %s", type(_exc).__name__, _exc)
        try:
            await escalate_uc.execute(
                conversation_id=body.conversation_id,
                tenant_id=tenant_id,
                reason="llm_unavailable",
            )
        except Exception:
            pass  # best-effort — don't mask the 503
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
    log_turn_cost(
        tenant_id=tenant_id,
        conversation_id=body.conversation_id,
        route="agent",
        embedding_calls=turn_result.iterations,  # one rag_search embed per iteration (approx)
        ms_elapsed=(time.perf_counter() - _t0) * 1000,
        embedding_provider=getattr(settings, "embedding_provider", "voyage"),
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


def _allow_origin(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "authorization,content-type,origin"
    response.headers["Vary"] = "Origin"
