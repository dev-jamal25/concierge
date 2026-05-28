# Security Design

**Owner**: C (Models / Security / Guardrails) for this doc; per-mitigation ownership called out below.
**Status**: design document. Reflects the system as built (Owner A foundation + Owner C Phase 2 + classifier track + Owner D widget/admin); does not certify any specific framework compliance.

This document describes the threat model the system is designed against, the defenses in code, and the design choices made for data protection. It is a rationale document, not a certification.

## Scope and non-goals

In scope:
- Multi-tenant SaaS hosting an AI agent embedded on tenants' public sites.
- Visitor traffic from arbitrary origins; tenant admins; a small set of platform managers.
- Hosted LLMs and embeddings via API; self-hosted Postgres, Redis, MinIO, Vault, and two small internal services (modelserver, guardrails sidecar).

Out of scope (not implemented; do not assume present):
- SOC2 / ISO 27001 / HIPAA controls (no certification claimed).
- DLP at the network layer.
- WAF or DDoS mitigation (assumed to be provided by the deployment environment).

## Threat model

| Threat | Mitigations | Owner | Status |
|---|---|---|---|
| **Token compromise** — a leaked widget JWT lets an attacker chat as if they were a legitimate visitor of tenant X. | Short-lived JWTs (15 min default); signed with an Ed25519 key stored in Vault; rotated per Vault policy; **origin check** on every request validates `Origin` header against `tenant.allowed_origins`. CORS headers are defense-in-depth, never the sole gate (Principle V). | A + D | A: T038 Vault client done. D: T030 TokenSigner protocol done, T049 signer pending. |
| **Prompt injection** — visitor input attempts to override agent system prompt, exfiltrate other tenants' data, or escalate privileges. | Platform rail `prompt_injection` in the guardrails sidecar refuses known injection patterns; rate-limited; refusals audit-logged. Tenant rails cannot weaken this layer (validation in T123 returns 403 + audit on attempts). Red-team gate `injection_redteam_success_rate ≥ 0.95` blocks regressions. | C | Protocol + adapter stub done (T028/T048); sidecar wiring pending (T172). |
| **Cross-tenant data leakage** — agent for tenant A returns data from tenant B (via RAG misconfiguration, JWT spoofing, or query injection). | **Defense in depth**, four independent layers (Principle III, NON-NEGOTIABLE): (1) `tenant_id` from the verified JWT only — never from request body / query / header (T033 middleware enforces this); (2) Postgres Row-Level Security per tenant on every tenant-scoped table; (3) repository layer scopes every query by `tenant_id` independently; (4) pgvector retrieval filters by `tenant_id` at query time. Red-team gate `cross_tenant_redteam_success_rate = 1.0` — zero leakage tolerated, blocks merges. | A + B | A: T033/T038/T111 done. B: chunk repo + retrieval pending. |
| **PII leakage to LLM / logs / traces / Redis** — visitor pastes a credit card or API key; it flows downstream unredacted. | Two-layer redaction: (a) sync regex redactor (T035) installed on the logger filter + OTel span processor at app startup, catches obvious patterns inline with zero latency; (b) async `RedactionService` calls the guardrails sidecar's `/check` for full coverage before content is sent to the LLM or written to Redis. Canary test (T143) asserts `pii_redaction_rate = 1.0` — zero leakage tolerated. | C | Sync redactor done (T035/T040/T041); guardrails sidecar pending (T172); canary test pending (T143). |
| **Insider misuse via platform-manager role** — a tenant_manager exfiltrates many tenants' aggregate data. | `tenant_manager` role has access to a separate Postgres connection (`concierge_manager`) bound to a role with elevated reads on `tenants` + `audit_entries` + provisioning tables **only** — not on tenant content tables. Every manager action is audit-logged (T021/T036). | A | Done — see `backend/app/frameworks/db/session.py`, `frameworks/api/session_auth.py`. |
| **Service-to-service credential theft** — modelserver or guardrails sidecar credential is stolen, attacker calls those services directly to bypass rails or to enumerate. | Both services require `X-Service-Token` (Vault-issued, rotated). Tokens are not baked into images, not committed to `.env` files in the repo, and are scoped to the internal Docker network (not exposed publicly). | C | Protocol slots in T047/T048; Vault-rotated impl pending T151. |
| **Tenant config weakens platform rails** — admin tries to set persona/rails that disable injection detection or PII redaction. | `UpdateGuardrailConfigUseCase` (T123) validates the proposed config against an immutable platform-rail schema. Attempts to weaken return 403 and are audit-logged. The 403 + audit pattern is itself part of the test surface (T127). | C + D | T123 pending [C], T127 pending [D]. |
| **Stale or swapped model artifact** — wrong `model.onnx` ends up in the modelserver image (build mistake, rollback gone wrong, supply-chain attack). | Boot-time SHA-256 verification (T148): the modelserver computes `sha256(model.onnx)` and `sha256(vocab.json)` and compares against `model_card.yaml`. Mismatch exits the process. Same check runs in the classifier eval gate (T135) — CI catches drift before merge. | A + C | T135 done (C); T148 pending (A). |
| **Unsigned or low-quality model swap** — somebody pushes a new model without justification. | A new `model_card.yaml` requires a new numbered entry in DECISIONS.md (Principle VII). Reviewer rotation per PR (Owner T180) ensures the entry is read by someone outside the slice. | All | Convention enforced socially; no automation. |
| **Pgvector OOB read across tenants** — pgvector returns embeddings from another tenant if the filter is wrong. | The query filter is on `tenant_id` at the SQL level (the indexed column on every chunks row), not as a post-filter on the result set. Repository (Owner B) is the only code that constructs vector queries; tests assert tenant filtering before any retrieval is exposed. | B | Pending — chunk repository protocol published (T023), impl pending. |
| **Vault outage at boot** — modelserver / guardrails sidecar can't fetch the service token. | Containers fail closed: no token → no startup. The backend's chat route returns 503 if either sidecar is unhealthy. Visitors see a graceful "we're temporarily unavailable" rather than an unauthenticated chat. | A + C | Vault client done (T038); failure-mode test pending. |

## Authentication paths

Three distinct authenticated paths, three different credentials:

| Path | Caller | Credential | Token TTL | Where verified |
|---|---|---|---|---|
| **Widget** | visitor's browser | Ed25519-signed JWT, claims = `{tenant_id, widget_id, iat, exp, jti}` | 15 min | `TenantContextMiddleware` (T033) — extracts `tenant_id` from verified claims; `OriginCheckMiddleware` (T034) — validates request `Origin` against `tenant.allowed_origins`. |
| **Admin** | tenant admin (browser) | fastapi-users session cookie + per-tenant role binding | session | `session_auth.get_principal()`; `require_matching_tenant()` rejects requests whose body claims a different tenant than the session. |
| **Manager** | platform operator | fastapi-users session cookie + `tenant_manager` global role | session | `session_auth.require_manager()`; uses a separate Postgres role with elevated cross-tenant reads on a restricted table set. |

The widget JWT signing key lives at Vault path `secret/jwt/widget/active`, generated at startup by `HvacVaultClient.ensure_widget_signing_key()`. Rotation produces a new active key while the previous key is still accepted for one TTL window, so in-flight widget sessions don't fail mid-conversation.

## Data protection posture

**GDPR-aligned design choices** (no certification claimed; these are deliberate architectural decisions that align with GDPR principles):

| Principle | Implementation | Where |
|---|---|---|
| **Lawful basis** | Visitor consent is the tenant's responsibility, captured on the tenant's site before the widget is loaded. The widget loader checks for a consent cookie before initializing the chat. | Owner D widget loader (T101) |
| **Data minimization** | The widget collects only what the visitor types; no fingerprinting, no IP logging beyond what's required for rate-limiting (kept 24h then aged out of Redis). Lead capture is opt-in per turn. | Owner B chat route + lead use case |
| **Right of access** | Per-tenant data is exportable via the admin `/admin/leads` endpoint as CSV (T120) and via DB role-scoped queries for the tenant admin. | Owner B (T120) |
| **Right of erasure** | `EraseTenantUseCase` (T110) cascades delete across Postgres (RLS-scoped), Redis (per-tenant key prefix), MinIO (per-tenant bucket prefix), and pgvector (per-tenant rows). Integration test (T128) asserts zero residual rows after erasure. Audit log keeps the `tenant_erase_complete` entry. | Owner A (T110/T128) |
| **Storage limitation** | Conversation memory in Redis has a 7-day TTL; lead rows are retained per tenant retention policy (configurable; default 1 year). | Owner B session_store impl |
| **Purpose limitation** | Service tokens are scoped — modelserver token can call only modelserver endpoints; guardrails token can call only guardrails endpoints. | Owner C T151 |

## Jurisdictional posture

The system makes no claims about the residency of:
- Hosted LLM inference (depends on tenant choice of provider; Anthropic, Groq, etc. have their own residency stories)
- Hosted embedding inference (same)
- Object storage (MinIO is self-hosted; deployment environment chooses the region)

A tenant with strict residency requirements must select providers whose residency matches and deploy the self-hosted services (Postgres, Redis, MinIO, Vault, modelserver, guardrails sidecar) in the appropriate region. The platform does not enforce residency itself — it is provided by the deployment topology.

## Audit logging

Every privileged action writes an `audit_entries` row (T021 + T036). The row records:
- `actor_user_id` and `actor_role`
- `tenant_id` (or `null` for platform-level actions)
- `action` (string code: `tenant_provision`, `tenant_erase`, `guardrail_weaken_attempted`, etc.)
- `outcome` (success | failure | refused)
- `metadata` (JSONB for action-specific context)
- `at` (timestamp)

Audit rows are append-only — there is no UPDATE or DELETE path. Querying audit rows requires the `tenant_manager` role (cross-tenant reads) or RLS-scoped access for the tenant's own actions.

## What's left

The threats above name pending tasks where the mitigation isn't fully in code yet. Treat this document as the contract: when those tasks land, the corresponding row's mitigation transitions from "designed" to "implemented + tested + gated by CI". The eval gates in [`EVALS.md`](EVALS.md) are how we know each defense actually works.
