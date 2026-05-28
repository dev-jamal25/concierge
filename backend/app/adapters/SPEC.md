# Adapters Layer — SPEC (stub — Owner B, T060)

To be populated by Owner B as Slice B completes (T163). Sections:

## Repository layer contract

How each repository adapter implements its protocol:
- Tenant scoping: every query includes `WHERE tenant_id = :tenant_id`.
- RLS: `SET LOCAL app.tenant_id` is applied by `TenantContextMiddleware`
  before any repository call; the adapter never sets it directly.
- Erasure: `delete_by_page`, `delete`, and cascade-deletes clean up
  related rows; Redis purge and MinIO prefix deletion handled in
  `EraseTenantUseCase`.

## Protocol implementations

### LLMClient — AnthropicLLM (`adapters/llm/anthropic_client.py`)

Anthropic Python SDK, model `claude-sonnet-4-6` by default.
Tool-calling loop lives in `use_cases/agent_turn.py`; the adapter
is a single-shot `messages.create` call. Provider is swappable via
the `LLMClient` protocol.

### EmbeddingClient — HostedEmbeddings (`adapters/embeddings/hosted_embeddings.py`)

Provider selected by `EMBEDDING_PROVIDER` env var (voyage | cohere | openai).
Model and vector dimension (1024) documented in DECISIONS.md entry 2.
Batch embeds; called from `use_cases/reindex_tenant_chunks.py`.

### SessionStore — RedisSession (`adapters/session/redis_session.py`)

Redis 7, keys namespaced `session:<key>`, JSON-serialised values, per-key TTL.
Bulk-deletable per tenant via key scan in `EraseTenantUseCase`.

## Integration points with other adapters

- `ClassifierClient` (Owner C) — consumed by `use_cases/classify_message.py`.
- `GuardrailsClient` (Owner C) — consumed by `use_cases/agent_turn.py` and
  `frameworks/api/middleware/pii_redaction.py`.
- `TokenSigner` (Owner D) — consumed by `frameworks/api/routes/widget.py`
  (not by Owner B's routes).
- `ObjectStorage` (Owner D) — not consumed by Owner B's use cases.
