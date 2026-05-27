from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

GuardrailRole = Literal["visitor_input", "agent_output", "tool_input", "tool_output"]
GuardrailAction = Literal["allow", "redact", "refuse"]
GuardrailLayer = Literal["platform", "tenant"]

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "")
REFUSAL_MESSAGE = (
    "I can't help with requests to bypass instructions, reveal private system "
    "details, or access another tenant's data."
)
REDACTED = "[REDACTED]"


class CheckRequest(BaseModel):
    tenant_id: UUID
    role: GuardrailRole
    content: str = Field(max_length=16_000)


class CheckResponse(BaseModel):
    action: GuardrailAction
    content: str
    triggered_rails: list[str] = Field(default_factory=list)
    rail_layer: GuardrailLayer | None = None


@dataclass(frozen=True)
class RedactionPattern:
    name: str
    pattern: re.Pattern[str]


PII_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern(
        "pii_credit_card",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    ),
    RedactionPattern(
        "pii_email",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    ),
    RedactionPattern(
        "pii_openai_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    ),
    RedactionPattern(
        "pii_google_api_key",
        re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    ),
    RedactionPattern(
        "pii_ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
)

REFUSAL_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern(
        "prompt_injection",
        re.compile(
            r"\b(ignore|forget|disregard)\b.{0,80}\b(previous|prior|system|developer)\b"
            r"|\breveal\b.{0,60}\b(system prompt|developer message|instructions)\b"
            r"|\bprint\b.{0,60}\b(system prompt|hidden prompt|instructions)\b",
            re.IGNORECASE,
        ),
    ),
    RedactionPattern(
        "jailbreak",
        re.compile(
            r"\b(jailbreak|DAN mode|developer mode|act as unrestricted|no policies)\b",
            re.IGNORECASE,
        ),
    ),
    RedactionPattern(
        "cross_tenant",
        re.compile(
            r"\b(other tenant|another tenant|tenant b|competitor tenant|cross[- ]tenant)\b"
            r"|\bshow me\b.{0,80}\b(their|another customer's|other customer's)\b",
            re.IGNORECASE,
        ),
    ),
)

app = FastAPI(title="Concierge guardrails sidecar", version="1.0.0")


def _require_service_token(x_service_token: str | None) -> None:
    if not SERVICE_TOKEN:
        return
    if x_service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="missing or invalid service token")


def _apply_refusals(content: str) -> list[str]:
    return [rule.name for rule in REFUSAL_PATTERNS if rule.pattern.search(content)]


def _apply_redactions(content: str) -> tuple[str, list[str]]:
    triggered: list[str] = []
    redacted = content
    for rule in PII_PATTERNS:
        redacted_next = rule.pattern.sub(REDACTED, redacted)
        if redacted_next != redacted:
            triggered.append(rule.name)
            redacted = redacted_next
    return redacted, triggered


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
async def check(
    request: CheckRequest,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> CheckResponse:
    _require_service_token(x_service_token)

    refusal_rails = _apply_refusals(request.content)
    if refusal_rails:
        return CheckResponse(
            action="refuse",
            content=REFUSAL_MESSAGE,
            triggered_rails=refusal_rails,
            rail_layer="platform",
        )

    redacted, redaction_rails = _apply_redactions(request.content)
    if redaction_rails:
        return CheckResponse(
            action="redact",
            content=redacted,
            triggered_rails=redaction_rails,
            rail_layer="platform",
        )

    return CheckResponse(action="allow", content=request.content, triggered_rails=[])
