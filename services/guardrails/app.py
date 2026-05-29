from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

import asyncpg
import hvac
import yaml
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

GuardrailRole = Literal["visitor_input", "agent_output", "tool_input", "tool_output"]
GuardrailAction = Literal["allow", "redact", "refuse"]
GuardrailLayer = Literal["platform", "tenant"]

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "")
VAULT_ADDR = os.getenv("VAULT_ADDR", "")
VAULT_TOKEN = os.getenv("VAULT_DEV_ROOT_TOKEN_ID", "")
VAULT_KV_MOUNT = os.getenv("VAULT_KV_MOUNT", "secret")
SERVICE_TOKEN_PATH = "service/internal-token"

PLATFORM_RAILS_PATH = Path(
    os.getenv("PLATFORM_RAILS_PATH", str(Path(__file__).parent / "config" / "platform_rails.yml"))
)
# Read-only cross-tenant connection used ONLY to load tenants.guardrail_config at
# boot/reload. asyncpg wants a native postgresql:// DSN (no +asyncpg suffix).
GUARDRAILS_DATABASE_URL = os.getenv("GUARDRAILS_DATABASE_URL", "")

logger = logging.getLogger("guardrails")
REFUSAL_MESSAGE = (
    "I can't help with requests to bypass instructions, reveal private system "
    "details, or access another tenant's data."
)
# Tenant-layer refusal copy, shaped by the tenant's configured refusal_tone.
TENANT_REFUSAL_BY_TONE: dict[str, str] = {
    "friendly": "Sorry, I can't help with that one — happy to help with anything else though!",
    "neutral": "I'm not able to help with that topic.",
    "polite": "I'm sorry, but I'm not able to help with that topic.",
    "formal": "We are unable to assist with that request.",
}
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


# --- Rail catalog -----------------------------------------------------------
# The regexes ARE the rail implementations. Which of them are active is NOT
# decided here: the locked platform_rails.yml manifest selects the active set
# at boot (see load_platform_rails). A rail absent from the manifest is inert,
# and the manifest is checksummed so a runtime edit is detectable.

_REDACTION_CATALOG: dict[str, re.Pattern[str]] = {
    "pii_credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "pii_email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "pii_openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "pii_google_api_key": re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    "pii_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

_REFUSAL_CATALOG: dict[str, re.Pattern[str]] = {
    # Instruction-override: telling the agent to disregard its real instructions
    # or accept new ones injected by the visitor.
    "prompt_injection": re.compile(
        r"\b(ignore|forget|disregard|override|bypass)\b.{0,80}"
        r"\b(previous|prior|above|earlier|system|developer|your)\b"
        r".{0,20}\b(instruction|prompt|rule|restriction|message|direction)s?\b"
        r"|\bnew instructions?\b\s*:"
        r"|\bfrom now on\b.{0,40}\b(ignore|you are|act|respond)\b",
        re.IGNORECASE,
    ),
    # Persona / policy override: jailbreak personas and "restrictions off" framing.
    "jailbreak": re.compile(
        r"\bjailbreak"
        r"|\bDAN\b|\bdo anything now\b"
        r"|\bdeveloper mode\b"
        r"|\b(un)?restricted (mode|assistant|ai|model)\b"
        r"|\buncensored\b"
        r"|\ball restrictions are off\b|\brestrictions are off\b"
        r"|\bno (rules|restrictions|filters|policies|content policy|guardrails)\b"
        r"|\bact as\b.{0,30}\b(unrestricted|jailbroken|uncensored|dan|developer)\b"
        r"|\byou are now\b.{0,30}\b(in )?(developer mode|uncensored|unrestricted|dan)\b",
        re.IGNORECASE,
    ),
    # Extraction of the hidden system/developer prompt or prior instructions.
    "system_prompt_extraction": re.compile(
        r"\b(reveal|show|print|output|repeat|reproduce|echo|display|spell out|give me)\b"
        r".{0,60}\b(system|initial|original|developer|hidden|your)\b.{0,20}"
        r"\b(prompt|instruction|message)s?\b"
        r"|\binstructions? you were given\b"
        r"|\b(text|everything) above\b.{0,20}\bverbatim\b"
        r"|\bfirst \d+ tokens?\b"
        r"|\b(system|initial) prompt\b.{0,30}\b(verbatim|word for word)\b",
        re.IGNORECASE,
    ),
    # Social-engineering wrappers used to coax policy-violating output.
    "content_policy_bypass": re.compile(
        r"\bfor (educational|research|awareness|academic) purposes\b"
        r"|\bhypothetically\b|\bjust for awareness\b"
        r"|\bmy (grand)?mother\b.{0,60}\b(code|password|secret)s?\b"
        r"|\b(admin )?override codes?\b"
        r"|\bextract (sensitive|confidential|private|customer)\b",
        re.IGNORECASE,
    ),
    # Structured-tag / template injection trying to forge system or user turns.
    "syntax_injection": re.compile(
        r"</?\s*(system|user|assistant)\s*>"
        r"|\{\{\s*(system|user|assistant)\s*\}\}"
        r"|\[\s*(system|user|assistant)\s*\]"
        r"|\bnew role\b",
        re.IGNORECASE,
    ),
    # Visitor directing the agent to invoke internal tools with crafted payloads.
    "tool_use_abuse": re.compile(
        r"\b(use|trigger|invoke|call|run|execute)\b.{0,40}"
        r"\b(capture_lead|escalate|rag_search)\b.{0,10}\btool\b"
        r"|\b(capture_lead|escalate|rag_search)\b.{0,10}\btool\b.{0,40}"
        r"\b(payload|fields|with)\b"
        r"|\bforce_email\b",
        re.IGNORECASE,
    ),
    # Cross-tenant data access: references to other tenants by slug, quantifiers
    # over "all/other/which tenant(s)", per-tenant breakdowns, or tenant-scoped
    # object paths. Anchored to attack-shaped phrasing to avoid firing on benign
    # uses of the word "tenant" (e.g. property-management concierges).
    "cross_tenant": re.compile(
        r"\b(all|other|another|every|each|any|which|per|cross[- ]?)[ -]tenants?\b"
        r"|\b(for|on|of|from|across|to)\s+tenant[ -][a-z0-9][\w-]*"
        r"|\b(look\s?up|access|show|list|find|retrieve|read|fetch|summari[sz]e)\b"
        r"[^.?!]{0,40}\btenant[ -][a-z0-9][\w-]*"
        r"|\btenant[ -][a-z0-9][\w-]*['’]s\b"
        r"|/tenants?/[a-z0-9]"
        r"|\b(other|another)\s+(customer|client|business|account)('?s)?\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class PlatformRails:
    refusals: tuple[RedactionPattern, ...]
    redactions: tuple[RedactionPattern, ...]
    checksum: str


def load_platform_rails(path: Path = PLATFORM_RAILS_PATH) -> PlatformRails:
    """Load the locked platform-rail manifest and bind it to the rail catalog.

    The YAML names which catalog rails are active; the file's sha256 is recorded
    so /healthz can expose it and any tamper is visible. An unknown rail name in
    the manifest is a deploy-time error (fail fast rather than silently skip a
    protection)."""
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    manifest = yaml.safe_load(raw) or {}
    section = manifest.get("platform_rails", {})
    refusal_names = section.get("refusal", [])
    redaction_names = section.get("redaction", [])

    unknown = [n for n in refusal_names if n not in _REFUSAL_CATALOG] + [
        n for n in redaction_names if n not in _REDACTION_CATALOG
    ]
    if unknown:
        raise RuntimeError(f"platform_rails.yml names rails absent from catalog: {unknown}")

    return PlatformRails(
        refusals=tuple(RedactionPattern(n, _REFUSAL_CATALOG[n]) for n in refusal_names),
        redactions=tuple(RedactionPattern(n, _REDACTION_CATALOG[n]) for n in redaction_names),
        checksum=checksum,
    )


PLATFORM_RAILS: PlatformRails | None = None


# --- Tenant rails (configurable, loaded from DB) ----------------------------


@dataclass(frozen=True)
class TenantRails:
    """Per-tenant configurable layer. Shapes brand voice; never weakens platform
    rails (that invariant is enforced at write time by T123, not here)."""

    blocked_topics: tuple[re.Pattern[str], ...] = ()
    refusal_tone: str = "polite"


def _compile_blocked_topic(topic: str) -> re.Pattern[str]:
    """Compile one configured blocked-topic term into a matcher.

    A trailing ``*`` is a prefix wildcard (``competitor_*`` → any token starting
    with ``competitor_``); otherwise the term matches as a whole word."""
    term = topic.strip()
    if term.endswith("*"):
        return re.compile(rf"\b{re.escape(term[:-1])}\w*", re.IGNORECASE)
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


def build_tenant_rails(config: dict) -> TenantRails:
    """Turn a tenants.guardrail_config JSONB blob into compiled tenant rails."""
    blocked = config.get("blocked_topics") or []
    tone = config.get("refusal_tone") or "polite"
    return TenantRails(
        blocked_topics=tuple(_compile_blocked_topic(t) for t in blocked if t and t.strip()),
        refusal_tone=tone if tone in TENANT_REFUSAL_BY_TONE else "polite",
    )


TENANT_RAILS: dict[str, TenantRails] = {}


async def load_tenant_rails(database_url: str) -> dict[str, TenantRails]:
    """Read every tenant's guardrail_config and compile it into tenant rails.

    Best-effort: a DB outage must not take the sidecar down or weaken platform
    rails, so on any failure we log and return an empty map (platform-only)."""
    if not database_url:
        logger.warning("GUARDRAILS_DATABASE_URL unset — tenant rails disabled (platform-only)")
        return {}
    try:
        conn = await asyncpg.connect(database_url)
        try:
            rows = await conn.fetch("SELECT id, guardrail_config FROM tenants")
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001 — never let a DB problem disable the sidecar
        logger.exception("tenant-rail load failed; serving platform rails only")
        return {}

    rails: dict[str, TenantRails] = {}
    for row in rows:
        raw = row["guardrail_config"]
        config = json.loads(raw) if isinstance(raw, str) else (raw or {})
        rails[str(row["id"])] = build_tenant_rails(config)
    logger.info("tenant rails loaded for %d tenant(s)", len(rails))
    return rails


def _apply_tenant_rails(content: str, rails: TenantRails) -> list[str]:
    """Return the blocked-topic terms triggered by this content, if any."""
    return [r.pattern for r in rails.blocked_topics if r.search(content)]


app = FastAPI(title="Concierge guardrails sidecar", version="1.0.0")


def _ensure_service_token_from_vault() -> str:
    """Idempotently fetch or provision the shared sidecar token in Vault (T151).

    First sidecar to reach Vault writes a random token; subsequent boots (and the
    api container) read the same value. Returns "" if Vault is unreachable so we
    fall through to the env override.
    """
    if not VAULT_ADDR or not VAULT_TOKEN:
        return ""
    try:
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        try:
            resp = client.secrets.kv.v2.read_secret_version(
                path=SERVICE_TOKEN_PATH,
                mount_point=VAULT_KV_MOUNT,
                raise_on_deleted_version=False,
            )
            existing = resp["data"]["data"]
        except hvac.exceptions.InvalidPath:
            existing = None
        if existing and existing.get("token"):
            return existing["token"]
        token = secrets.token_urlsafe(32)
        client.secrets.kv.v2.create_or_update_secret(
            path=SERVICE_TOKEN_PATH,
            secret={"token": token},
            mount_point=VAULT_KV_MOUNT,
        )
        return token
    except Exception:  # noqa: BLE001 — log and fall back to env override
        logger.exception("vault service-token fetch failed; falling back to SERVICE_TOKEN env")
        return ""


@app.on_event("startup")
async def _bootstrap() -> None:
    global SERVICE_TOKEN, PLATFORM_RAILS, TENANT_RAILS
    PLATFORM_RAILS = load_platform_rails()
    logger.info(
        "platform rails loaded (checksum=%s, refusals=%d, redactions=%d)",
        PLATFORM_RAILS.checksum[:12],
        len(PLATFORM_RAILS.refusals),
        len(PLATFORM_RAILS.redactions),
    )
    TENANT_RAILS = await load_tenant_rails(GUARDRAILS_DATABASE_URL)
    vault_token = _ensure_service_token_from_vault()
    if vault_token:
        SERVICE_TOKEN = vault_token
        logger.info("service token loaded from Vault (path=%s)", SERVICE_TOKEN_PATH)
    elif SERVICE_TOKEN:
        logger.warning("service token sourced from env (Vault unavailable)")
    else:
        logger.warning("no service token configured — auth disabled")


def _require_service_token(x_service_token: str | None) -> None:
    if not SERVICE_TOKEN:
        return
    if x_service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="missing or invalid service token")


def _apply_refusals(content: str, rails: PlatformRails) -> list[str]:
    return [rule.name for rule in rails.refusals if rule.pattern.search(content)]


def _apply_redactions(content: str, rails: PlatformRails) -> tuple[str, list[str]]:
    triggered: list[str] = []
    redacted = content
    for rule in rails.redactions:
        redacted_next = rule.pattern.sub(REDACTED, redacted)
        if redacted_next != redacted:
            triggered.append(rule.name)
            redacted = redacted_next
    return redacted, triggered


def evaluate(
    content: str,
    rails: PlatformRails,
    tenant_rails: TenantRails | None = None,
) -> CheckResponse:
    """Apply the locked platform rails, then the tenant layer, to a piece of text.

    Order matters: platform rails run first and cannot be weakened by the tenant
    layer. A tenant blocked-topic refusal only fires on content the platform
    rails allowed, so the tenant layer can tighten but never loosen. Pure (no
    I/O) so the redteam and canary suites (T142/T143) can exercise it directly."""
    refusal_rails = _apply_refusals(content, rails)
    if refusal_rails:
        return CheckResponse(
            action="refuse",
            content=REFUSAL_MESSAGE,
            triggered_rails=refusal_rails,
            rail_layer="platform",
        )

    if tenant_rails is not None:
        blocked = _apply_tenant_rails(content, tenant_rails)
        if blocked:
            return CheckResponse(
                action="refuse",
                content=TENANT_REFUSAL_BY_TONE[tenant_rails.refusal_tone],
                triggered_rails=blocked,
                rail_layer="tenant",
            )

    redacted, redaction_rails = _apply_redactions(content, rails)
    if redaction_rails:
        return CheckResponse(
            action="redact",
            content=redacted,
            triggered_rails=redaction_rails,
            rail_layer="platform",
        )

    return CheckResponse(action="allow", content=content, triggered_rails=[])


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if PLATFORM_RAILS is None:
        raise HTTPException(status_code=503, detail="platform rails not loaded")
    return {"status": "ok", "platform_rails_checksum": PLATFORM_RAILS.checksum}


@app.post("/check", response_model=CheckResponse)
async def check(
    request: CheckRequest,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> CheckResponse:
    _require_service_token(x_service_token)
    if PLATFORM_RAILS is None:
        raise HTTPException(status_code=503, detail="platform rails not loaded")
    return evaluate(request.content, PLATFORM_RAILS, TENANT_RAILS.get(str(request.tenant_id)))


@app.post("/reload")
async def reload_tenant_rails(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> dict[str, int]:
    """Re-read tenant rails from the DB. Called by the admin update use case
    (T123) after a tenant edits its guardrail_config so changes take effect
    without a sidecar restart. Platform rails are immutable and never reloaded."""
    _require_service_token(x_service_token)
    global TENANT_RAILS
    TENANT_RAILS = await load_tenant_rails(GUARDRAILS_DATABASE_URL)
    return {"tenants": len(TENANT_RAILS)}
