# Guardrails Sidecar — Specification

**Owner**: C (Models / Security / Guardrails)
**Status**: live. Protocol + adapter (T028/T048), redaction middleware (T035/T173), sidecar with checksummed locked platform rails + DB-loaded tenant rails (T172), service-token auth (T151, sidecar side), and redteam/PII-canary eval gates (T142/T143) all merged. Pending: modelserver service `app.py` (T151 modelserver side).

The guardrails sidecar is a small HTTP service that applies **platform rails** and **tenant rails** to every piece of text moving in or out of the agent. It is the place where prompt-injection defenses, jailbreak defenses, cross-tenant refusal, and PII redaction live as code, not as polite prompt suggestions.

## Two layers of rails

| Layer | Configurable by tenant? | Examples | Why locked |
|---|---|---|---|
| **Platform** | **No** | prompt-injection refusal; jailbreak refusal; cross-tenant data refusal; PII redaction (credit cards, emails, API keys, SSNs) | Constitution Principle V: a tenant must not be able to weaken the rails that protect every other tenant or that protect users from the agent. |
| **Tenant** | Yes (via admin UI → tenant.guardrail_config JSONB) | allowed topics; blocked topics; refusal tone; enabled tools (subset of `rag_search`, `capture_lead`, `escalate`) | These shape per-tenant brand voice without weakening platform protections. |

If a tenant request would weaken a platform rail, the admin endpoint returns 403 and the attempt is audit-logged (T123).

## Wire contract

Defined in [`specs/001-concierge-platform/contracts/internal/guardrails.yaml`](../../specs/001-concierge-platform/contracts/internal/guardrails.yaml).

### `POST /check`

Request:
```json
{ "tenant_id": "uuid", "role": "visitor_input | agent_output | tool_input | tool_output", "content": "string ≤ 16000 chars" }
```

Response:
```json
{
  "action": "allow | redact | refuse",
  "content": "<see below>",
  "triggered_rails": ["pii_credit_card", ...],
  "rail_layer": "platform | tenant"
}
```

The `content` field is **what the caller should use**:
- `allow` → original input, unchanged
- `redact` → original input with PII replaced by `[REDACTED]` markers
- `refuse` → the refusal message from the triggered rail (the caller passes this on to the user)

`triggered_rails` and `rail_layer` are for logging and audit — not for caller branching.

### `GET /healthz`

Returns liveness once the rail pack is loaded.

## Where /check is called

Every direction of agent traffic crosses the sidecar:

```
Visitor message
    │
    ▼
[/check role=visitor_input]   ── refuse / redact / allow ──┐
                                                            │
                                              chat route (Owner B, T080)
                                                            │
                                                            ▼
                                                    Agent (T077)
                                                            │
                                          tool call ───────┤
                                                            │
                                              ┌─────────────┴───────────┐
                                              ▼                          ▼
                                  [/check role=tool_input]   [/check role=tool_input]
                                              │                          │
                                          rag_search                capture_lead
                                              │                          │
                                              ▼                          ▼
                                  [/check role=tool_output]  [/check role=tool_output]
                                              │
                                              ▼
                                   Agent response synthesis
                                              │
                                              ▼
                                  [/check role=agent_output]
                                              │
                                              ▼
                                     Visitor sees reply
```

The `PIIRedactionMiddleware` (T035) wires a sync regex redactor into the logger and tracer so logs and traces are safe even before the sidecar is reachable (defense in depth). The async `RedactionService` in that same middleware is the path the chat route and Redis writer use to call `/check` properly.

## Authentication

Every request carries the shared `X-Service-Token` issued from Vault (T151). The sidecar rejects missing or invalid tokens with 401. The token is rotated per Vault policy; both the FastAPI backend and the sidecar accept the active and previous-active versions during the rotation window.

## Platform rails (locked)

The active rail set is declared in `services/guardrails/config/platform_rails.yml` (baked into the image) and its sha256 is computed at boot and exposed on `/healthz` — a runtime edit is detectable and the container cannot mutate the locked set. The YAML names which rails are active; the regex implementations live in the catalog in `app.py`. A manifest naming a rail absent from the catalog fails fast at boot.

| Rail | Trigger | Action |
|---|---|---|
| `prompt_injection` | inputs matching known injection patterns (e.g. "ignore previous instructions", suspicious system-prompt syntax) | refuse with a generic decline |
| `jailbreak` | inputs attempting persona override or content-policy bypass | refuse |
| `cross_tenant` | inputs containing identifiers that look like other tenants' data | refuse + audit |
| `pii_credit_card` | credit-card-shaped digit sequences | redact |
| `pii_email` | email addresses outside an allow-list per tenant | redact |
| `pii_api_key` | strings shaped like API keys (`sk-…`, `AIza…`, etc.) | redact |
| `pii_ssn` | US SSN pattern `\d{3}-\d{2}-\d{4}` | redact |

The PII set mirrors the regex set in `app.frameworks.api.middleware.pii_redaction` so the sync fast path and the sidecar slow path agree on what counts as PII.

## Tenant rails (configurable)

Loaded from `tenants.guardrail_config` JSONB at boot, refreshed when a tenant admin updates settings (T123). Per-tenant rails compile into NeMo definitions templated against the tenant's id.

```yaml
# Example tenant config (validated by T123)
allowed_topics: ["hours", "pricing", "services", "policies", "support"]
blocked_topics: ["competitor_*", "off_topic_examples"]
refusal_tone: friendly        # one of: friendly | neutral | formal
enabled_tools: [rag_search, capture_lead]   # subset of [rag_search, capture_lead, escalate]
```

Validation rules (T123): a tenant config that tries to disable any platform rail or to weaken redaction returns 403 from the admin endpoint and is audit-logged.

## Container constraints

- **No torch, no GPU.** Same Principle IV rule as the modelserver.
- **Base**: `python:3.11-slim`.
- **Bundled**: NeMo Guardrails + pinned LLM client for the rail evaluator (uses the hosted LLM via the same `OpenAI`-compatible client the rest of the system uses).
- **Cache**: rail-evaluation results are memoized in-process by `(rail_id, content_hash)` for the request lifetime to keep latency reasonable when the same content traverses multiple roles.

## Eval coverage

| Gate | What it asserts | Task |
|---|---|---|
| `injection_redteam_success_rate ≥ 0.95` | the sidecar refuses 95%+ of curated prompt-injection probes | T140 + T142 |
| `cross_tenant_redteam_success_rate = 1.0` | the sidecar refuses 100% of cross-tenant data-leakage probes | T141 + T142 |
| `pii_redaction_rate = 1.0` | synthetic PII canaries never appear unredacted in logs, traces, Redis, or LLM input | T143 |

All three are committed thresholds in `eval_thresholds.yaml`. They block merges if regression occurs.

## Related tasks

| Task | Status | Notes |
|---|---|---|
| T028 | done | GuardrailsClient protocol |
| T035 | done | PIIRedactionMiddleware (sync regex redactor + async RedactionService seam) |
| T048 | done | NeMoGuardrails HTTP adapter stub |
| T122, T123 | done | GuardrailConfig entity + UpdateGuardrailConfigUseCase (rejects rail weakening) |
| T140, T141 | done | redteam JSONL probe sets (injection, cross-tenant) |
| T142, T143 | done | redteam + PII canary eval gates (`tests/evals/redteam/`, in-process) |
| T151 | partial | Vault service credential — sidecar 401 enforcement + integration test done; modelserver side pending its `app.py` |
| T165 | done | this document |
| T172 | done | platform rails locked from checksummed YAML; tenant rails loaded from DB at boot + `/reload` |
| T173 | done | PII redaction middleware: message + structured-field log redaction, trace + Redis/LLM seam |
