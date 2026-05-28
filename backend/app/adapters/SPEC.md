# Adapters Layer — SPEC (T163)

This document describes the concrete adapter implementations in `app/adapters/`.
The layer sits between use-case protocols (Layer 2) and external services.
No adapter may be imported by `entities/` or `use_cases/`; all cross-layer
wiring happens in `frameworks/`.

---

## Architecture rules

- Every adapter implements exactly one Layer-2 protocol from `use_cases/protocols/`.
- Adapters receive connection/config via constructor injection; they do not read
  `Settings` directly (the framework wires them via `frameworks/api/deps.py`).
- Tenant scoping for database adapters: every query includes `WHERE tenant_id = :tid`.
  Row-level security (`SET LOCAL app.tenant_id`) is applied by `TenantContextMiddleware`
  before any repository call; adapters never set it themselves.

---

## LLM

### `llm/anthropic_client.py` — `AnthropicLLM`

**Protocol**: `use_cases/protocols/llm_client.py::LLMClient`

Anthropic Python SDK (`anthropic>=0.28`). Single-shot `messages.create` call
(non-streaming). Tool schema passed as `tools=`. Provider is swappable — swap
the constructor call in `frameworks/api/routes/chat.py` to change provider.

**Model**: `claude-sonnet-4-6` (default); overridable via `LLM_MODEL` env var.

---

## Embeddings

### `embeddings/hosted_embeddings.py` — `HostedEmbeddings`

**Protocol**: `use_cases/protocols/embedding_client.py::EmbeddingClient`

Provider selected by `EMBEDDING_PROVIDER` env var:

| Provider | SDK | Default model |
|----------|-----|---------------|
| `voyage` | `voyageai>=0.2` | `voyage-3` (1024-dim) |
| `cohere` | `cohere` | `embed-english-v3.0` |
| `openai` | `openai` | `text-embedding-3-large` |

Vector dimension is 1024 (matches `chunks.embedding` column and HNSW index).
See DECISIONS.md entry #2 for provider choice rationale.

---

## Classifier

### `classifier/modelserver_client.py` — `ModelserverClassifier`

**Protocol**: `use_cases/protocols/classifier_client.py::ClassifierClient`

HTTP client to the Owner C modelserver sidecar (`http://localhost:8001` default).
Sends `POST /predict` with `{"text": message, "tenant_id": tenant_id}`.
Authenticates via `X-Service-Token` header (shared secret from Vault, T151).
Returns `label`, `confidence`, `per_class` scores.

Fallback: `ClassifyMessageUseCase` falls back to the LLM router prompt
(`prompts/system_router.md`) when the sidecar is unavailable.

---

## Guardrails

### `guardrails/nemo_client.py` — `NeMoGuardrailsClient`

**Protocol**: `use_cases/protocols/guardrails_client.py::GuardrailsClient`

HTTP client to the Owner C NeMo guardrails sidecar (`http://localhost:8002`).
Platform rails (`injection_defense`, `jailbreak_defense`, `cross_tenant_defense`,
`pii_redaction`) cannot be weakened via the admin API (returns 403).

---

## Session

### `session/redis_session.py` — `RedisSession`

**Protocol**: `use_cases/protocols/session_store.py::SessionStore`

Redis 7 (`redis[hiredis]>=5.0`). Values are JSON-serialised.

**Key schema**: `session:{tenant_id}:{conversation_id}` (tenant-scoped for
per-tenant erasure — Owner A's T129 calls `delete_by_tenant(tenant_id)`).

**TTL strategy** (DECISIONS.md entry #5):
- First write: `SET key val NX EX 3600` — starts fixed 60-min clock once.
- Subsequent writes: `SET key val KEEPTTL` — updates value without resetting TTL.
- Plain `SET` would silently clear the TTL (making the key permanent) — this is
  the bug the KEEPTTL approach corrects.

**Erasure seam**: `delete_by_tenant(tenant_id)` scans `session:{tenant_id}:*`
and deletes via a pipelined batch (no transaction). Published for Owner A's T129;
`erase_tenant.py` is not edited by Owner B.

---

## Repositories

All repositories are in `repositories/`. Each implements a use-case protocol
from `use_cases/protocols/`.

### `repositories/chunk_repository.py` — `PostgresChunkRepository`

**Protocol**: `use_cases/protocols/chunk_repository.py::ChunkRepository`

pgvector HNSW cosine-distance search:
```sql
SELECT ... ORDER BY embedding <=> $1 LIMIT 20
WHERE tenant_id = :tid AND cms_pages.state = 'published'
```
Column `metadata` is aliased as `chunk_metadata` on the ORM model to avoid
the SQLAlchemy 2.x reserved attribute name.

### `repositories/cms_page_repository.py` — `PostgresCMSPageRepository`

**Protocol**: `use_cases/protocols/cms_page_repository.py::CMSPageRepository`

CRUD + publish/unpublish state transitions. DELETE only allowed on `draft` state.
Unique constraint on `(tenant_id, slug)`.

### `repositories/conversation_repository.py` — `PostgresConversationRepository`

**Protocol**: `use_cases/protocols/conversation_repository.py::ConversationRepository`

Creates conversations on first chat turn; updates `escalated_at` +
`escalation_reason` + `last_turn_at` on escalate.

### `repositories/lead_repository.py` — `PostgresLeadRepository`

**Protocol**: `use_cases/protocols/lead_repository.py::LeadRepository`

Inserts leads; enforces per-session rate-limit (1 per window, 1 lifetime)
by counting existing leads for the conversation.

### `repositories/audit_repository.py` — `PostgresAuditRepository`
### `repositories/invitation_repository.py` — `PostgresInvitationRepository`
### `repositories/tenant_repository.py` — `PostgresTenantRepository`
### `repositories/user_repository.py` — `PostgresUserRepository`
### `repositories/widget_repository.py` — `PostgresWidgetRepository`

Owner A repositories — see Owner A's scope notes.

---

## Email

### `email/console_email.py` — `ConsoleEmailSender`

**Protocol**: `use_cases/protocols/email_sender.py::EmailSender`

Prints email to stdout (dev/test). Swap for SMTP adapter in production.

---

## Storage

### `storage/minio_object_storage.py` — `MinIOObjectStorage`

**Protocol**: `use_cases/protocols/object_storage.py::ObjectStorage`

Owner D adapter. Not consumed by Owner B's use cases.

---

## Tokens

### `tokens/pyjwt_signer.py` — `PyJWTSigner`

**Protocol**: `use_cases/protocols/token_signer.py::TokenSigner`

Widget JWT signing (HS256). Owner D adapter. Not consumed by Owner B's use cases.

---

## Integration with other owners

| Protocol | Adapter owner | Consumed by |
|----------|---------------|-------------|
| `ClassifierClient` | C | `use_cases/classify_message.py` (B) |
| `GuardrailsClient` | C | `frameworks/api/middleware/` (C) |
| `TokenSigner` | D | `frameworks/api/routes/widget.py` (D) |
| `ObjectStorage` | D | not used by B |
| `SessionStore` | B | `use_cases/session_memory.py` (B), `EraseTenantUseCase` (A via T129) |
