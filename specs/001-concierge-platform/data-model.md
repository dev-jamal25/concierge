# Phase 1 — Data Model

**Feature**: Concierge Multi-Tenant AI SaaS Platform
**Plan**: [plan.md](./plan.md) · **Research**: [research.md](./research.md)
**Date**: 2026-05-25

This document defines the persistent data model. Source of truth for
schema is Alembic migrations under `src/frameworks/db/alembic/versions/`;
this file is the design specification those migrations implement.

The model is enforced at three layers, in this order of trust:

1. **Database (Postgres + RLS)**: schema constraints, foreign keys,
   uniqueness, and Row-Level Security policies. This is the wall.
2. **Repository (`src/adapters/repositories/`)**: every query explicitly
   includes `WHERE tenant_id = :tenant_id` as defence in depth.
3. **Use case (`src/use_cases/`)**: validates business invariants before
   issuing repository calls.

`tenant_id` is set on the SQLAlchemy session via
`SET LOCAL app.tenant_id = '<uuid>'::uuid` at the start of every request
by `TenantContextMiddleware`. `SET LOCAL` ensures the value never leaks
across requests on a pooled connection.

---

## Tenancy model

- `tenant_manager`: global role, no `tenant_id` association. Uses a
  dedicated Postgres role (`concierge_manager`) which has `BYPASSRLS`
  on the `audit_entries` and `tenants` tables ONLY. Cannot read
  conversations, leads, CMS content. Crossing the boundary is itself
  an audit event.
- `tenant_admin`: per-tenant role, may administer one or more tenants
  via rows in `user_tenant_roles`. Uses the default Postgres role
  (`concierge_app`) which is bound by RLS.
- `visitor`: anonymous; identified by a session token derived from a
  widget JWT. Cannot reach the admin / manager surfaces at all.

---

## Postgres extensions required

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
```

---

## Tables

### `tenants`

The isolated workspace for a business. Global table (no `tenant_id`
column on itself). RLS allows tenant_admins to read only their own
row; `tenant_manager` can read all rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | `DEFAULT gen_random_uuid()` |
| `slug` | `TEXT NOT NULL UNIQUE` | URL-safe handle, e.g. `acme-co` |
| `display_name` | `TEXT NOT NULL` | Human-readable name |
| `plan` | `TEXT NOT NULL DEFAULT 'poc'` | `poc | growth | production` (only `poc` in v1.0) |
| `persona_config` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Persona injected into prompts at runtime |
| `theme_config` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Widget colours / greeting |
| `guardrail_config` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Tenant rails (topics, refusal tone, enabled tools) |
| `status` | `TEXT NOT NULL DEFAULT 'active'` | `active | erasing | erased` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**RLS**:
- `SELECT`/`UPDATE` for `concierge_app`:
  `id = current_setting('app.tenant_id')::uuid`.
- `concierge_manager` bypasses RLS on this table.

---

### `users`

Global identity. Managed by fastapi-users; we add a `role` column.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `email` | `TEXT NOT NULL UNIQUE` | |
| `hashed_password` | `TEXT NOT NULL` | Argon2id (fastapi-users default) |
| `role` | `TEXT NOT NULL` | `tenant_manager | tenant_admin` |
| `is_active` | `BOOLEAN NOT NULL DEFAULT TRUE` | |
| `is_verified` | `BOOLEAN NOT NULL DEFAULT FALSE` | |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**RLS**: Users read/write only their own row; tenant_manager bypasses.

---

### `user_tenant_roles`

Join table linking `tenant_admin` users to tenants. `tenant_manager`
has zero rows here.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | `UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `PRIMARY KEY (user_id, tenant_id)` | | |

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

---

### `invitations`

Pending invitation for a tenant_admin to take ownership.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id)` | |
| `email` | `TEXT NOT NULL` | |
| `token_hash` | `TEXT NOT NULL` | SHA-256 of the issued one-time token |
| `expires_at` | `TIMESTAMPTZ NOT NULL` | |
| `accepted_at` | `TIMESTAMPTZ` | NULL until accepted |
| `created_by` | `UUID NOT NULL REFERENCES users(id)` | tenant_manager who issued |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `UNIQUE (tenant_id, email) WHERE accepted_at IS NULL` | | |

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`; manager bypasses.

---

### `cms_pages`

Tenant content. State machine: `draft → published`,
`published → unpublished`, `unpublished → published`,
`unpublished → draft`. `draft → unpublished` is forbidden (enforced
by `CHECK` + use-case validation).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `title` | `TEXT NOT NULL` | |
| `body` | `TEXT NOT NULL` | Markdown / plain text |
| `state` | `TEXT NOT NULL` | `draft | published | unpublished`; CHECK constraint |
| `slug` | `TEXT NOT NULL` | `UNIQUE (tenant_id, slug)` |
| `published_at` | `TIMESTAMPTZ` | NULL unless state has ever been `published` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**: `(tenant_id, state)` for the common "list published pages
for this tenant" query.

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

**Visibility rules** (enforced in repository AND verified in tests):
- Public site renders rows with `state = 'published'`.
- Agent retrieval (via `chunks` join) MUST NOT return chunks from rows
  with `state != 'published'`.

---

### `chunks`

Embedded fragments of `cms_pages.body`. The vector store.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `cms_page_id` | `UUID NOT NULL REFERENCES cms_pages(id) ON DELETE CASCADE` | |
| `chunk_index` | `INTEGER NOT NULL` | 0-based position within page |
| `content` | `TEXT NOT NULL` | The chunk text (≤ 600 tokens) |
| `embedding` | `vector(1024) NOT NULL` | Dimension set by chosen embedder; documented in DECISIONS.md |
| `metadata` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | e.g. heading path |
| `embedded_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `UNIQUE (cms_page_id, chunk_index)` | | |

**Indexes**:
- `(tenant_id)` B-tree — used by retrieval WHERE clause.
- `embedding` HNSW or ivfflat (cosine distance) — vector ANN.
- Important: retrieval query is `WHERE tenant_id = :tenant_id ORDER BY
  embedding <=> :query LIMIT 20`. Filter is applied AT QUERY TIME by
  the planner, not as a post-filter. The composite plan is exercised by
  `tests/integration/test_rls_isolation.py`.

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

**Lifecycle**: When a `cms_pages` row transitions OUT of `published`,
its chunks are DELETED (re-ingested on re-publish). This is enforced in
`publish_cms_page.py` / `reindex_tenant_chunks.py`.

---

### `conversations`

One conversation between a visitor and the agent / router.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `widget_id` | `UUID NOT NULL REFERENCES widgets(id)` | |
| `visitor_session` | `TEXT NOT NULL` | Pseudonymous ID from the widget JWT |
| `escalated_at` | `TIMESTAMPTZ` | NULL unless flagged for human |
| `escalation_reason` | `TEXT` | e.g. `visitor_request | llm_unavailable | tool_loop_cap` |
| `started_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `last_turn_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

---

### `messages`

One turn within a conversation (visitor or agent).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `conversation_id` | `UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE` | |
| `role` | `TEXT NOT NULL` | `visitor | agent | tool | system` |
| `router_label` | `TEXT` | Set for visitor turns once classified |
| `content` | `TEXT NOT NULL` | PII-redacted before write |
| `tool_calls` | `JSONB` | Recorded tool invocations (sanitised) |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**: `(conversation_id, created_at)`.

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

---

### `leads`

Captured contact + intent from a visitor. Real side-effect target of
the `capture_lead` tool.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `conversation_id` | `UUID NOT NULL REFERENCES conversations(id)` | |
| `name` | `TEXT` | Visitor-provided |
| `contact` | `TEXT NOT NULL` | Email / phone / handle |
| `intent` | `TEXT NOT NULL` | Free-form stated intent |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**: `(tenant_id, created_at DESC)`.

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

**Rate limit**: Repository enforces ≤ 1 lead per visitor session per
60s and ≤ 5 leads per session lifetime. Excess attempts are rejected and
audit-logged on the conversation (not on this table).

---

### `widgets`

Embeddable chat widget configuration. One widget per tenant in v1.0
(constraint enforced; multi-widget can come later).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE` | |
| `public_id` | `TEXT NOT NULL UNIQUE` | Pasted into the embed snippet's `data-widget-id` |
| `is_enabled` | `BOOLEAN NOT NULL DEFAULT TRUE` | |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

Note: `public_id` is the public-facing handle the host pastes; it's
high-entropy but not a secret. The widget loader sends `(public_id,
origin)` to `/widget/token` and gets a short-lived signed JWT in
return.

---

### `allowed_origins`

Tenant's list of permitted origins for widget loading + CORS + CSP.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `tenant_id` | `UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` | |
| `origin` | `TEXT NOT NULL` | e.g. `https://acme.example.com` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `UNIQUE (tenant_id, origin)` | | |

**RLS**: `tenant_id = current_setting('app.tenant_id')::uuid`.

Origin matching is exact-string only — no wildcards, no path matching.

---

### `audit_entries`

Append-only log of tenant_manager actions. NEVER updated, NEVER deleted
(not even on tenant erasure).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PRIMARY KEY` | |
| `actor_user_id` | `UUID REFERENCES users(id)` | Acting tenant_manager (NULL only for system events) |
| `target_tenant_id` | `UUID` | NOT a foreign key — survives the tenant it referenced |
| `action` | `TEXT NOT NULL` | `tenant_create | tenant_erase | tenant_erase_complete | manager_access_attempt | ...` |
| `outcome` | `TEXT NOT NULL` | `success | denied | failure` |
| `details` | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Structured detail (stores purged, error, etc.) |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Indexes**: `(target_tenant_id, created_at DESC)`, `(actor_user_id, created_at DESC)`.

**RLS**:
- `concierge_manager`: read-only access to all rows.
- `concierge_app`: NO access (tenant_admin cannot read audit entries).
- INSERT: only `concierge_manager` and the system (via internal
  function `audit_log_internal()`).
- UPDATE/DELETE: **revoked from every role** — appendonly enforced.

---

## State machines

### `cms_pages.state`

```text
       create
draft ─────────┐
  │            ▼
  │       published ◀──── unpublished
  │            │              ▲
  │            └──────────────┘
  ▼            (admin click)
draft ──── X ──── (not allowed) ──── unpublished
```

Permitted transitions (enforced by CHECK and use-case):
- `draft → published`
- `published → unpublished`
- `unpublished → published`
- `unpublished → draft`

`draft → unpublished` is **not** allowed; an unwanted draft is deleted.

### `conversations.escalated_at` lifecycle

- NULL → set to `now()` when the agent / router decides to escalate.
- Once non-NULL, this conversation is read-only from the agent's
  perspective (no further LLM calls); the tenant_admin sees it in the
  escalations list.

### `tenants.status` lifecycle

- `active` → `erasing` (set by `EraseTenantUseCase` at start of purge)
- `erasing` → `erased` (set when all stores confirmed purged; `tenants`
  row itself remains for audit reference until a vacuum job removes it)

---

## Cross-store erasure path (FR-037 / SC-009)

The `EraseTenantUseCase` purges every store within the ≤ 1-hour SLA:

1. **Postgres**: `DELETE FROM tenants WHERE id = :t` cascades through
   `cms_pages → chunks`, `conversations → messages`, `leads`,
   `widgets`, `allowed_origins`, `user_tenant_roles`, `invitations`.
   `users` with no remaining tenant rows are NOT deleted (their row in
   `users` is global identity).
2. **Vector index**: covered by step 1 (chunks live in Postgres).
3. **Redis**: scan + delete all keys matching
   `tenant:<tenant_id>:*` via `SCAN MATCH` (non-blocking).
4. **MinIO**: list and delete every object under the
   `tenant-<tenant_id>/` prefix.
5. **Audit**: write `tenant_erase_complete` to `audit_entries` with
   `details.stores_purged = ['pg','vector','redis','minio']` and
   `outcome = 'success'`.

A post-erasure audit job (`tests/integration/test_erasure_path.py`)
samples each store with the deleted tenant's UUID and asserts zero
matches.

---

## Vector retrieval query (illustrative)

```sql
-- Executed inside a request that has already SET LOCAL app.tenant_id.
-- Both the explicit WHERE clause and RLS apply.
SELECT
  c.id,
  c.cms_page_id,
  c.content,
  c.metadata,
  c.embedding <=> :query_embedding AS distance
FROM chunks c
JOIN cms_pages p ON p.id = c.cms_page_id AND p.state = 'published'
WHERE c.tenant_id = :tenant_id     -- repository-layer scoping (defence in depth)
ORDER BY c.embedding <=> :query_embedding
LIMIT 20;
```

The top-20 are sent to the reranker; top-5 reranked are returned to
the agent / router.

---

## Entity ↔ table map

| Entity (spec) | Table(s) |
|---------------|----------|
| Tenant | `tenants` |
| User | `users` (+ role column) |
| User-tenant binding | `user_tenant_roles` |
| Visitor | NOT persisted as identity (session-only via JWT) |
| Conversation | `conversations` + `messages` |
| CMSPage / Content | `cms_pages` |
| Chunk | `chunks` |
| Lead | `leads` |
| Widget | `widgets` |
| AllowedOrigin | `allowed_origins` |
| AuditEntry | `audit_entries` |
| ModelCard | NOT in DB — file `services/modelserver/model_card.yaml` |
| GuardrailConfig (tenant rails) | `tenants.guardrail_config` JSONB |
| GuardrailConfig (platform rails) | NOT in DB — locked in `services/guardrails/config/platform_rails/` |
