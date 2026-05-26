# Implementation Plan: Concierge Multi-Tenant AI SaaS Platform

**Branch**: `001-concierge-platform` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-concierge-platform/spec.md`

## Summary

Concierge is a multi-tenant AI SaaS. Businesses sign up, manage their CMS
content, and embed an AI agent on their public site. The agent's inbound
visitor messages go through a classifier-driven router first; only ambiguous
or multi-step turns reach a single tool-calling LLM agent with three tools
(`rag_search`, `capture_lead`, `escalate`). Tenant isolation is the
non-negotiable property: enforced at the database (Postgres Row-Level
Security), the repository layer (every query tenant-scoped), the retrieval
layer (pgvector filtered at query time), and the auth layer (`tenant_id`
derived only from the verified token).

The implementation follows the constitution's Clean Architecture: four layers
(Entities → Use Cases → Interface Adapters → Frameworks & Drivers) with the
dependency rule strictly enforced. Composition root wires concrete adapters
into use cases at startup; no use case ever imports a framework. The
deployable surface is one FastAPI backend plus three sidecars (a lean
modelserver running the offline-trained classifier, a NeMo Guardrails sidecar,
and the React widget bundle), the Streamlit tenant admin UI, and shared
infrastructure (Postgres + pgvector, Redis, MinIO, Vault).

The team of four owns four vertical slices — A) Platform/Tenancy/Isolation,
B) Agent/RAG/Memory, C) Models/Security/Guardrails, D) Widget/Admin/CI —
each cutting through API → use case → repository → infrastructure. No one
owns a horizontal layer.

## Technical Context

**Language/Version**: Python 3.11 (backend, admin, modelserver, eval suite);
TypeScript / Node 20 (React widget); SQL (Postgres 16); YAML (CI, configs).

**Primary Dependencies**: FastAPI, fastapi-users (auth + roles), SQLAlchemy
2.x (async), Alembic (migrations), asyncpg (Postgres driver), pgvector
(vector type + ivfflat / hnsw index), PyJWT (widget token signing),
redis-py / aioredis (session memory), minio-py (object storage), hvac
(Vault client), httpx (sidecar calls), pydantic v2 (DTOs / validation),
Streamlit (tenant admin UI). Modelserver: FastAPI + onnxruntime +
scikit-learn + joblib (no torch). Guardrails: NeMo Guardrails sidecar.
Widget: React 18 + Vite + TypeScript. LLM: hosted Anthropic API
(claude-sonnet-4-6 default; provider swappable via adapter). Embeddings:
hosted API (e.g. Voyage / Cohere / OpenAI — provider swappable). Tests:
pytest + pytest-asyncio + pytest-cov + ruff + mypy; vitest for the widget.

**Storage**:
- Postgres 16 with the `pgvector` extension — primary store AND vector
  store. Row-Level Security enabled on every tenant-scoped table.
- Redis 7 — short-term per-conversation session memory only.
- MinIO — object storage for the widget bundle and for any tenant
  uploads.
- Vault (dev mode / KV v2 at PoC scale) — service credentials and
  JWT signing keys.

**Testing**: pytest (unit + integration + contract), pytest-asyncio,
pytest-cov, ruff (lint), mypy (type-check), vitest (widget), and a
dedicated `tests/evals/` tree for the four CI gate suites.

**Target Platform**: Linux x86_64 server. v1.0 runs as a single
`docker compose` stack (Postgres, Redis, MinIO, Vault, API, modelserver,
guardrails sidecar, admin, optional widget-static container). Local dev
mirrors prod compose with the same image set.

**Project Type**: Multi-service web platform — one HTTP API (FastAPI),
two HTTP sidecars (modelserver, guardrails), one admin UI (Streamlit),
one frontend bundle (React widget), shared infra (Postgres, Redis, MinIO,
Vault), plus an offline training surface (notebooks + exported artifacts).

**Performance Goals** (from spec SC-006 + per-component budgets):
- Visitor turn end-to-end p95 < 5s.
- Classifier (modelserver) p95 < 100ms.
- pgvector retrieval p95 < 200ms at 200 chunks per tenant.
- Guardrails check p95 < 200ms.
- Token issuance p95 < 50ms.

**Constraints**:
- **NON-NEGOTIABLE** — RLS on every tenant-scoped table; `tenant_id`
  derived from token only; pgvector filter at query time, never
  post-filter.
- No `torch` in any deployed container.
- Modelserver image ≤ 500MB.
- LLM + embeddings via hosted API only.
- Tenant persona injected at runtime; never hardcoded in prompts.
- Service-to-service auth via shared credential from Vault.
- All four CI eval gates pass on every push (see `eval_thresholds.yaml`).

**Scale/Scope** (resolved by clarification Q1): PoC scale — ≤ 10 tenants,
~200 CMS pages per tenant, ≤ 50 concurrent visitors platform-wide.
Sharding, HA, and replicas are explicitly out of scope for v1.0.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the seven principles in `.specify/memory/constitution.md`
v1.0.0:

| # | Principle | Status | How this plan satisfies it |
|---|-----------|--------|----------------------------|
| I  | Clean Architecture & Dependency Rule (NON-NEGOTIABLE) | ✅ PASS | Source tree (below) physically separates `entities/`, `use_cases/`, `adapters/`, `frameworks/`. Static checks (import-linter or ruff custom rules) block any inward → outward import. Reviewed slice-by-slice. |
| II | SOLID via Dependency Inversion | ✅ PASS | Each repository owns one aggregate (TenantRepo, LeadRepo, ChunkRepo, ConversationRepo, UserRepo, AuditRepo). LLM, embedding, classifier, guardrails adapters all implement abstract `Protocol` interfaces declared in `use_cases/`. Concretes are bound in `frameworks/api/deps.py` (composition root) — use cases never import concretes. |
| III | Tenant Isolation (NON-NEGOTIABLE) | ✅ PASS | Defence in depth: (1) `tenant_id` UUID on every tenant-scoped table; (2) Postgres RLS policies enforce `app.tenant_id` per request; (3) every repository scopes by `tenant_id` as a second layer; (4) pgvector retrieval filters by `tenant_id` in the WHERE clause; (5) `tenant_id` is set ONLY from the verified JWT or service credential — middleware refuses any request that supplies a conflicting body field. Cross-tenant red-team set is a CI gate. |
| IV | Hosted Inference, Lean Containers | ✅ PASS | No `torch` anywhere. LLM + embeddings via hosted API. Modelserver constrained: `python:3.11-slim` base, `onnxruntime` + `scikit-learn` + `joblib` + FastAPI only; final image size budget 500MB, asserted in CI. |
| V  | Defense-in-Depth Security | ✅ PASS | Short-lived PyJWT widget tokens (≤ 5 min). Origin check on every chat request against `tenant.allowed_origins` (DB). CORS + CSP `frame-ancestors` configured from same source — defence-in-depth only, never the only gate. Service-to-service calls authenticated with a Vault-issued shared credential. NeMo platform rails locked; tenant config cannot weaken injection / jailbreak / cross-tenant defences. |
| VI | Evals as CI Gates | ✅ PASS | Four CI gates: (a) classifier macro-F1, (b) agent tool-selection golden set (15 examples), (c) RAG golden set (15 triples), (d) red-team set (prompt injection + cross-tenant). Thresholds in `eval_thresholds.yaml` at repo root. Regression below threshold blocks merge. Stack smoke test is a fifth always-on gate. |
| VII | Spec-Driven, No Vibe Coding | ✅ PASS | `SPEC.md` per major component is part of slice DoD (see Source Code tree). `DECISIONS.md` updated for every architectural choice with a number from a golden / held-out set (see Phase 0). Prompts live in `prompts/`; tenant persona injected at runtime from `tenant.persona_config`. Required docs (`DESIGN.md`, `SPEC.md` per component, `DECISIONS.md`, `RUNBOOK.md`, `EVALS.md`, `SECURITY.md`) listed in the source tree below. |

**Result**: PASS — zero violations to justify. `Complexity Tracking` table
below remains intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-concierge-platform/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature specification (/speckit-specify output, clarified)
├── research.md          # Phase 0 — decisions + numbers + alternatives
├── data-model.md        # Phase 1 — tables, RLS policies, state machines
├── quickstart.md        # Phase 1 — clone → compose up → smoke test
├── contracts/           # Phase 1 — OpenAPI for API; widget-loader contract
│   ├── api.openapi.yaml
│   └── widget-loader.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already populated)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

The repo is one polyglot monorepo. Python packages follow the constitution's
four-layer split; non-Python services and the offline training surface live
in sibling top-level directories.

```text
src/
├── entities/                       # Layer 1 — pure dataclasses, no I/O
│   ├── __init__.py
│   ├── tenant.py
│   ├── user.py
│   ├── conversation.py
│   ├── cms_page.py
│   ├── chunk.py
│   ├── lead.py
│   ├── widget.py
│   ├── allowed_origin.py
│   ├── audit_entry.py
│   ├── model_card.py
│   └── guardrail_config.py
│
├── use_cases/                      # Layer 2 — business logic
│   ├── __init__.py
│   ├── protocols/                  # Abstract interfaces (Protocol classes)
│   │   ├── tenant_repository.py
│   │   ├── user_repository.py
│   │   ├── conversation_repository.py
│   │   ├── chunk_repository.py
│   │   ├── lead_repository.py
│   │   ├── audit_repository.py
│   │   ├── llm_client.py
│   │   ├── embedding_client.py
│   │   ├── classifier_client.py
│   │   ├── guardrails_client.py
│   │   ├── session_store.py
│   │   ├── object_storage.py
│   │   └── token_signer.py
│   ├── provision_tenant.py
│   ├── erase_tenant.py
│   ├── invite_admin.py
│   ├── classify_message.py         # Router
│   ├── rag_search.py
│   ├── capture_lead.py
│   ├── escalate.py
│   ├── agent_turn.py               # Bounded LLM tool-loop (≤ N iters, ≤ M tokens)
│   ├── issue_widget_token.py
│   ├── get_widget_config.py
│   ├── publish_cms_page.py
│   └── reindex_tenant_chunks.py
│
├── adapters/                       # Layer 3 — concrete implementations
│   ├── __init__.py
│   ├── repositories/               # One aggregate each — SRP
│   │   ├── tenant_repository.py
│   │   ├── user_repository.py
│   │   ├── conversation_repository.py
│   │   ├── chunk_repository.py
│   │   ├── lead_repository.py
│   │   └── audit_repository.py
│   ├── llm/
│   │   └── anthropic_client.py     # Implements LLMClient protocol
│   ├── embeddings/
│   │   └── hosted_embeddings.py    # Implements EmbeddingClient protocol
│   ├── classifier/
│   │   └── modelserver_client.py   # HTTP client → modelserver
│   ├── guardrails/
│   │   └── nemo_client.py          # HTTP client → guardrails sidecar
│   ├── session/
│   │   └── redis_session.py
│   ├── storage/
│   │   └── minio_object_storage.py
│   └── tokens/
│       └── pyjwt_signer.py
│
└── frameworks/                     # Layer 4 — only this layer knows infra
    ├── api/                        # FastAPI app
    │   ├── main.py
    │   ├── deps.py                 # Composition root — DI wiring
    │   ├── middleware/
    │   │   ├── tenant_context.py   # Sets app.tenant_id from JWT; resets at end
    │   │   ├── origin_check.py
    │   │   ├── cors.py             # Reads tenant.allowed_origins
    │   │   └── pii_redaction.py    # Pre-egress redactor for logs/traces
    │   └── routes/
    │       ├── widget.py           # /widget/token, /widget/config
    │       ├── chat.py             # /chat (router → agent loop)
    │       ├── cms.py              # /cms/pages CRUD + publish/unpublish
    │       ├── leads.py            # /leads list/export
    │       ├── admin.py            # /admin/tenant, /admin/guardrails, /admin/origins
    │       └── manager.py          # /manager/tenants, /manager/audit, /manager/usage
    ├── db/                         # SQLAlchemy + Alembic
    │   ├── base.py
    │   ├── models.py               # ORM models (NEVER imported from use_cases)
    │   ├── session.py              # Session factory, RLS SET CONFIG
    │   ├── pgvector_setup.py
    │   └── alembic/
    │       ├── env.py
    │       └── versions/
    ├── secrets/
    │   └── vault_client.py
    ├── observability/
    │   ├── logging.py              # Structured JSON, redaction-aware
    │   └── tracing.py
    └── config.py                   # Reads env / Vault; produces typed settings

services/                           # Separate deployable processes
├── modelserver/                    # Lean classifier server (no torch, < 500MB)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app.py                      # FastAPI + onnxruntime / joblib loader
│   └── model_card.yaml             # Hash-verified at boot
└── guardrails/                     # NeMo Guardrails sidecar
    ├── Dockerfile
    ├── config/
    │   ├── platform_rails/         # Locked rails (injection / jailbreak / cross-tenant / PII)
    │   └── tenant_rails_template/  # Per-tenant rails templated from DB at boot

admin/                              # Streamlit tenant admin UI
├── app.py
└── pages/
    ├── 1_dashboard.py
    ├── 2_cms.py
    ├── 3_leads.py
    ├── 4_settings.py               # persona, theme, allowed origins, guardrails
    └── 5_embed_snippet.py

widget/                             # React + Vite + TypeScript embeddable widget
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── loader.ts                   # Served at /widget.js — injects iframe
│   ├── App.tsx
│   ├── api.ts                      # Calls /chat, /widget/token
│   └── components/
└── tests/                          # vitest

notebooks/                          # Offline classifier training (NOT in any container)
├── 01_label_taxonomy.ipynb
├── 02_tfidf_logreg_baseline.ipynb
├── 03_small_dl_onnx.ipynb
├── 04_llm_zero_shot.ipynb
└── 05_compare_and_export.ipynb     # Produces artifact + model_card.yaml + SHA-256

prompts/                            # Version-controlled, persona injected at runtime
├── system_agent.md
├── system_router.md
├── tool_specs/
│   ├── rag_search.md
│   ├── capture_lead.md
│   └── escalate.md
└── refusal_templates.md

tests/
├── unit/                           # Per-layer unit tests
│   ├── entities/
│   ├── use_cases/                  # Fakes for all adapters
│   ├── adapters/
│   └── frameworks/
├── integration/                    # Real Postgres + Redis + MinIO via testcontainers / compose
│   ├── test_rls_isolation.py
│   ├── test_chat_flow.py
│   ├── test_erasure_path.py
│   └── test_widget_token_origin.py
├── contract/                       # OpenAPI schema conformance + widget-loader contract
└── evals/                          # CI gate suites
    ├── classifier/
    │   └── test_classifier_macro_f1.py
    ├── agent_tool_selection/
    │   ├── golden.jsonl            # 15 examples
    │   └── test_tool_selection.py
    ├── rag/
    │   ├── golden.jsonl            # 15 (q, expected-doc, expected-answer)
    │   └── test_rag_quality.py
    └── redteam/
        ├── injection.jsonl
        ├── cross_tenant.jsonl
        └── test_redteam.py

docs/                               # Required by constitution Principle VII
├── DESIGN.md                       # Isolation, scaling, cost-per-tenant, role model, erasure
├── DECISIONS.md                    # Every architectural choice backed by a number
├── RUNBOOK.md                      # Compose-up, restore, on-call
├── EVALS.md                        # How each gate is built and read
└── SECURITY.md                     # Threat model, jurisdictional posture (GDPR-aligned)

# Per-component SPEC.md files live alongside the code:
src/use_cases/SPEC.md
src/adapters/SPEC.md
services/modelserver/SPEC.md
services/guardrails/SPEC.md
admin/SPEC.md
widget/SPEC.md

.github/
└── workflows/
    ├── ci.yml                      # lint + type-check + build images + 4 eval gates + smoke
    └── eval-gates.yml

eval_thresholds.yaml                # Committed thresholds (classifier F1, RAG, agent, redteam)
docker-compose.yml                  # Full stack (compose-up smoke test target)
docker-compose.dev.yml              # Dev overrides (Vault dev mode, hot reload)
.env.example                        # Documents required env vars (no secrets)
pyproject.toml                      # Backend + modelserver workspaces
README.md
CLAUDE.md                           # Points at the current plan
```

**Structure Decision**: A polyglot monorepo with four Python layers
strictly separated under `src/` (Entities → Use Cases → Interface Adapters
→ Frameworks). Non-Python sub-products (`services/modelserver`,
`services/guardrails`, `widget/`) and offline training (`notebooks/`) are
siblings of `src/`, not nested under it. The chief constraint enforced by
this layout is that **nothing under `src/entities/` or `src/use_cases/`
may import from `src/adapters/` or `src/frameworks/`** — this is checked
by a static import-rule guard in CI (Principle I gate). Streamlit admin
and React widget are deployed independently from the API; the API and the
two sidecars are the three Python-runtime images shipped.

### Four-slice ownership map (parallel work)

Each slice is a vertical that cuts API → use case → repository → infra.
Nobody owns a horizontal layer in isolation.

| Slice | Owns (entities) | Owns (use cases) | Owns (adapters) | Owns (infra / non-Python) | Owns (eval gate) |
|-------|-----------------|------------------|-----------------|---------------------------|------------------|
| **A. Platform / Tenancy / Isolation** | Tenant, User, AllowedOrigin, AuditEntry | ProvisionTenantUseCase, EraseTenantUseCase, InviteAdminUseCase | TenantRepository, UserRepository, AuditRepository, VaultClient | Postgres schema + RLS policies, Alembic migrations, fastapi-users wiring, Vault setup, tenant_context middleware, manager routes | Cross-tenant RLS regression test (integration) — feeds the red-team gate |
| **B. Agent / RAG / Memory** | Conversation, Chunk, Lead, CMSPage | ClassifyMessageUseCase (router), RAGSearchUseCase, CaptureLeadUseCase, EscalateUseCase, AgentTurnUseCase, PublishCMSPageUseCase, ReindexTenantChunksUseCase | ConversationRepo, ChunkRepo, LeadRepo, LLMClient (Anthropic), EmbeddingClient, RedisSession | pgvector index + retrieval SQL, Redis session store, agent loop bounding, prompts/ wiring, chat + cms + leads routes | Agent tool-selection golden set, RAG golden set |
| **C. Models / Security / Guardrails** | ModelCard, GuardrailConfig | (Cross-cuts: integrates PIIRedaction into pipeline; classifier + guardrails clients) | ClassifierClient (HTTP→modelserver), GuardrailsClient (HTTP→NeMo) | `services/modelserver/*`, `services/guardrails/*`, classifier training notebooks, PII redaction middleware, Vault-issued service credentials, eval_thresholds.yaml | Classifier macro-F1 gate, red-team set (injection + cross-tenant) |
| **D. Widget / Admin / CI** | Widget | IssueWidgetTokenUseCase, GetWidgetConfigUseCase | PyJWTSigner, MinIOObjectStorage | React+Vite widget bundle + loader, Streamlit admin UI, widget routes, CORS + CSP middleware (driven by allowed_origins), MinIO image, `.github/workflows/*`, docker-compose smoke test | Stack smoke test, widget origin / CORS regression test |

Cross-slice integration points are explicit and small: A exposes a
`TenantContext` middleware that B/C/D use; C exposes
`ClassifierClient` and `GuardrailsClient` interfaces that B consumes via
its router and agent loop; D consumes A's `allowed_origins` for origin
validation. Daily integration sync is the only meeting needed.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_ | _(none)_ | _(none)_ |

The Constitution Check above passed all seven principles with no
violations. This table is intentionally empty.

## Phase 0 — Outline & Research

See [`research.md`](./research.md) for the full set of decisions. The
research phase resolves these open questions (each with a number from a
held-out or golden set per Principle VII):

1. **Chunking strategy** — paragraph-aware with token-bounded windows
   and overlap; justified vs. fixed-window baseline on the RAG golden
   set.
2. **Retrieval improvement** — cross-encoder rerank over top-k; justified
   vs. raw vector-only retrieval on the RAG golden set.
3. **LLM provider choice** — Anthropic `claude-sonnet-4-6` default;
   provider-swappable via `LLMClient` protocol. Reasoning: tool-calling
   quality + 200k context + JSON mode reliability.
4. **Embedding provider choice** — hosted API
   (e.g. Voyage / Cohere / OpenAI); abstracted behind
   `EmbeddingClient`. Provider chosen by cost-per-1M tokens + retrieval
   golden-set score.
5. **Redis session TTL** — 30 minutes per conversation, justified by
   typical visitor session abandonment data and to bound the blast
   radius of a token compromise.
6. **JWT algorithm and key rotation** — EdDSA (Ed25519) signing keys
   stored in Vault; key rotation by JWKS-style key ID indexed by Vault
   path.
7. **RLS pattern** — `SET LOCAL app.tenant_id = '<uuid>'` at the start
   of each request, reset at end via SQLAlchemy session scope. Policies
   filter every tenant-scoped table by `current_setting('app.tenant_id')::uuid`.
8. **PII redaction integration point** — outbound interceptor on the
   logger + tracer + Redis writer; canary test pastes a fake key per CI
   run and asserts redaction.
9. **Modelserver artifact verification** — modelserver computes SHA-256
   of `model.onnx` (or `model.joblib`) at boot and refuses to start if
   it disagrees with `model_card.yaml`.
10. **fastapi-users tenancy pattern** — users have a global role
    (`tenant_manager` | `tenant_admin`); `tenant_admin` users have one
    or more `user_tenant_role` rows mapping them to specific tenants.
    `tenant_manager` is global and has no per-tenant binding.
11. **Classifier label taxonomy** — `spam | faq | lead_intent | escalate
    | ambiguous` (5 labels). The router handles the first four directly;
    `ambiguous` is the only label that triggers the agent loop.

**Output**: `research.md` with each decision + rationale + alternatives
considered + the number that justifies the decision (or, where the gate
is built later, a "to be validated at Phase 2" marker).

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** → [`data-model.md`](./data-model.md):
   - Tables: `tenants`, `users`, `user_tenant_roles`, `invitations`,
     `cms_pages`, `chunks` (pgvector column), `conversations`,
     `messages`, `leads`, `widgets`, `allowed_origins`, `audit_entries`.
   - Every tenant-scoped table carries `tenant_id UUID NOT NULL` and
     has an RLS policy filtering by `current_setting('app.tenant_id')::uuid`.
   - State machine for `cms_pages`: `draft → published`,
     `published → unpublished`, `unpublished → published`,
     `unpublished → draft`. `draft → unpublished` is not allowed.
   - Indexes: pgvector `ivfflat` or `hnsw` on `chunks.embedding` with
     partial index `WHERE tenant_id = ...` not used — query-time filter
     is what the constitution requires.
   - Foreign keys, NOT NULLs, uniqueness rules (e.g.
     `tenants.slug UNIQUE`, `widgets.public_id UNIQUE`).
   - Audit log table append-only (no UPDATE/DELETE policies).

2. **Interface contracts** → [`contracts/`](./contracts/):
   - `api.openapi.yaml` — full OpenAPI 3.1 schema for every API
     endpoint. Endpoints grouped by slice:
     - **Slice A**: `/manager/tenants` (POST, GET, DELETE),
       `/manager/audit` (GET), `/manager/usage` (GET),
       `/admin/invitations` (POST), `/auth/*` (fastapi-users default).
     - **Slice B**: `/chat` (POST — visitor turn),
       `/cms/pages` (CRUD + publish/unpublish), `/leads` (GET, export).
     - **Slice C**: not directly user-facing — exposes
       `modelserver:/predict` and `guardrails:/check` over service
       network only. Both have `contracts/internal/*.yaml`.
     - **Slice D**: `/widget.js` (loader, static),
       `/widget/token` (POST — exchange `widget_id` + origin for JWT),
       `/widget/config` (GET — theme, greeting, persona).
   - `widget-loader.md` — the contract for the loader script:
     accepted attributes (`data-widget-id`, optional
     `data-position`), how it builds the iframe, how it polls for token
     refresh, allowed CSP `frame-ancestors`.

3. **Quickstart** → [`quickstart.md`](./quickstart.md):
   - Clone, copy `.env.example` → `.env`, set hosted-LLM and embeddings
     API keys.
   - `docker compose up -d` brings the full stack.
   - `make migrate` (alembic upgrade head) seeds the schema.
   - `make seed-demo-tenant` provisions a demo tenant, an admin
     account, one CMS page, and a widget; outputs the embed snippet.
   - Open `tests/widget-host-example/index.html` in a browser to
     interact with the agent.
   - `make smoke` runs the stack smoke test (D's CI gate locally).

4. **Update agent context**: Update `CLAUDE.md` to point at this plan
   between the `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->` markers.

**Output**: `data-model.md`, `contracts/api.openapi.yaml`,
`contracts/widget-loader.md`, `quickstart.md`, and updated `CLAUDE.md`.

## Post-Design Constitution Re-check

After Phase 1 design lands, re-verify each principle is still
satisfied:

- **I (Clean Arch)**: confirm no entity / use_case Python file in the
  generated tree imports from `adapters/` or `frameworks/`. CI rule:
  `import-linter` contract `no-inner-from-outer`.
- **II (DI)**: confirm `frameworks/api/deps.py` is the single
  composition root; no use case imports a concrete adapter module.
- **III (Tenant Isolation)**: confirm every tenant-scoped table in
  `data-model.md` has an RLS policy and the policy is exercised by
  `tests/integration/test_rls_isolation.py`.
- **IV (Lean Containers)**: confirm `services/modelserver/Dockerfile`
  builds an image ≤ 500MB and contains no `torch` (CI assertion).
- **V (Defense-in-Depth)**: confirm `/widget/token` issuance binds JWT
  to a single tenant + origin, and that `/chat` rejects
  origin/tenant mismatch with HTTP 403.
- **VI (Eval Gates)**: confirm `eval_thresholds.yaml` is present and
  CI loads it.
- **VII (Spec-Driven)**: confirm one `SPEC.md` per major component
  exists or is enqueued as a v1.0 prerequisite.

Re-check status: scheduled for end of Phase 1. Any post-design failure
must be recorded in this table with rationale before any task
generation in Phase 2.
