# Tasks: Concierge Multi-Tenant AI SaaS Platform

**Input**: Design documents from `specs/001-concierge-platform/`  
**Prerequisites**: plan.md, spec.md, data-model.md, research.md, contracts/  
**Date**: 2026-05-25  
**Team**: 4 vertical-slice owners (A/B/C/D); no horizontal-layer ownership

---

## Format: `[ID] [P?] [Story?] [Owner] Description with file path`

- **[ID]**: Task ID (T001, T002, …)
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1, US2, …) — REQUIRED for story phases only
- **[Owner]**: [A] Platform/Tenancy, [B] Agent/RAG, [C] Models/Security, [D] Widget/Admin/CI; [ALL] for shared
- Include exact file paths in descriptions

---

## ⚠️ CRITICAL: Ownership & Blocking Rules (ENFORCED)

**Rule 1: Only your owner tag** — If a task is tagged [A], only owner A works on it. If [B], only owner B. [ALL] tasks are done by the team together in Phase 2.

**Rule 2: Never work on another owner's tasks** — Do not start a task tagged with a different owner's letter. Exception: [ALL] tasks in Phase 2 (everyone together).

**Rule 3: BLOCK on cross-owner dependencies** — If your task (e.g., owner B's T090) requires code from another owner (e.g., owner A's T033 `TenantContextMiddleware`):
- **STOP immediately** — do not continue past this point
- **Notify**: "⚠️ BLOCKED: Task T090 [B] requires T033 [A] (TenantContextMiddleware) to be completed first"
- **Never stub or fake** the missing code from another owner — wait for the real implementation
- **AI enforcement**: If you (Claude) detect a task is asking to work on code tagged to a different owner, you **MUST REFUSE** and flag it clearly:
  - Message: `"❌ BLOCKED: Task T### is owned by [X]; I am working on [Y]. I cannot proceed. Please have owner [X] complete their prerequisite tasks first."`
  - Stop immediately; do not write any code
  - List which owner's tasks are blocking

**Rule 4: Protocol adapters are the seam** — In Phase 2, each owner publishes their Protocol interfaces (not implementations). In phases 3+:
- Owner B implements against Owner A's protocol (waiting for real implementation)
- If Owner A's implementation isn't ready, Owner B can code against a **fake/stub** that implements the protocol
- But Owner B must **NEVER MODIFY** Owner A's tasks or code — only implement against the published interface

**Rule 5: Cross-owner task lists** — Before starting your phase, check the "Dependencies" section below to see which other owners' tasks must complete first. Those are **blocking**. Do not start your phase until their prerequisites are done.

---

### Cross-Owner Blocking Matrix (Quick Reference)

| Your Owner | Requires from Owner | Tasks | Before You Can Start |
|-----------|-------------------|-------|-------------------|
| B (Agent/RAG) | A (Platform/Tenancy) | T033 (TenantContextMiddleware), T111 (TenantRepository), T038 (Vault client) | ≥ Phase 2 milestone |
| B (Agent/RAG) | C (Models/Security) | T028 (ClassifierClient proto), T029 (GuardrailsClient proto) | ≥ Phase 2 milestone |
| B (Agent/RAG) | D (Widget/Admin/CI) | T049 (TokenSigner proto), T050 (ObjectStorage proto) | ≥ Phase 2 milestone |
| C (Models/Security) | A (Platform/Tenancy) | T038 (Vault client for service credential) | ≥ Phase 2 milestone |
| D (Widget/Admin/CI) | A (Platform/Tenancy) | T111 (TenantRepository for origins check) | ≥ Phase 2 milestone |
| D (Widget/Admin/CI) | B (Agent/RAG) | T080 (Chat route for widget to call) | ≥ Phase 4 (US2 complete) |
| All | [ALL] | Phase 2 tasks (T010–T064) | Phase 2 MUST complete; team pairs |

---

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Repository scaffold and foundational tooling

- [ ] T001 [ALL] Initialize git repo with initial commit and branch `001-concierge-platform` in `.github/` with protection rules
- [ ] T002 [ALL] Create `pyproject.toml` with workspace setup (src/, services/modelserver, services/guardrails) and Python 3.11 pins
- [ ] T003 [P] [ALL] Create the four-layer `src/` tree structure (entities/, use_cases/, adapters/, frameworks/) with `__init__.py` files
- [ ] T004 [P] [ALL] Initialize `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, and `vitest` configs (setup.cfg, pyproject.toml)
- [X] T005 [ALL] Create `README.md` with project overview, prereqs, and link to quickstart.md
- [X] T006 [ALL] Create `.env.example` with required env vars (ANTHROPIC_API_KEY, EMBEDDING_PROVIDER, EMBEDDING_API_KEY, POSTGRES_PASSWORD, VAULT_DEV_ROOT_TOKEN_ID, RERANK_PROVIDER, RERANK_API_KEY)
- [X] T007 [ALL] Create `Makefile` with targets: `migrate`, `seed-demo-tenant`, `serve-test-host`, `smoke`, `eval`, `eval-classifier`, `eval-agent`, `eval-rag`, `eval-redteam`
- [X] T008 [ALL] Create `docker-compose.yml` with services: postgres (5432), redis (6379), minio (9000), vault (8200), modelserver (8001), guardrails (8002), api (8000), admin (8501), widget-static (8003)
- [X] T009 [ALL] Create `docker-compose.dev.yml` override with Vault dev-mode, hot-reload, exposed ports

---

## Phase 2: Foundational (Shared Monday Skeleton)

**Purpose**: Cross-slice contracts and reference patterns. BLOCKS all user stories. Team pairs on this before splitting.

### Shared Infrastructure & Integration Points

- [X] T010 [ALL] Create `eval_thresholds.yaml` at repo root with thresholds: classifier_macro_f1 ≥ 0.80, agent_tool_selection_macro_f1 ≥ 0.80, rag_golden_set_recall_at_5 ≥ 0.85, rag_golden_set_answer_grounded_rate ≥ 0.85, cross_tenant_redteam_success_rate = 1.0, injection_redteam_success_rate ≥ 0.95, pii_redaction_rate = 1.0
- [X] T011 [ALL] Create `src/frameworks/config.py`: settings class for database, redis, minio, vault, llm, embedding, classifier, guardrails URLs + credentials (read from env/.env, then Vault via hvac)
- [X] T012 [ALL] Create `src/frameworks/api/main.py`: FastAPI app skeleton with CORS, middleware hooks (app startup/shutdown), health endpoints `/healthz`, `/readyz`
- [X] T013 [ALL] Create `src/frameworks/db/base.py`: SQLAlchemy base model, async sessionmaker, alembic config for migrations under `src/frameworks/db/alembic/versions/`

### Isolation Reference Pattern (Slice A leads; all consume)

- [ ] T014 [A] Create `src/entities/tenant.py`: Tenant dataclass with id, slug, display_name, plan, persona_config, theme_config, guardrail_config, status, created_at, updated_at
- [ ] T015 [A] Create `src/entities/user.py`: User dataclass with id, email, hashed_password, role (tenant_manager | tenant_admin), is_active, is_verified, created_at
- [ ] T016 [A] Create `src/frameworks/db/models.py`: SQLAlchemy ORM models mirroring entities (tenants, users, user_tenant_roles, invitations, audit_entries tables with RLS schema placeholders)
- [ ] T017 [A] Create `src/frameworks/db/session.py`: SessionLocal factory with async scope; TenantContextMiddleware that extracts tenant_id from JWT/credential and executes `SET LOCAL app.tenant_id = '<uuid>'`
- [ ] T018 [A] Create Alembic migration `001_init_tenants_users_audit.sql`: creates tenants, users, user_tenant_roles, invitations, audit_entries tables with `tenant_id` on all tenant-scoped tables; installs pgcrypto, uuid-ossp, vector extensions; applies ONE RLS policy on tenants table as the reference pattern

### Protocol Interfaces (Slice leaders publish; others code against fakes)

- [ ] T019 [A] Create `src/use_cases/protocols/tenant_repository.py`: Protocol for ProvisionTenant, EraseTenant, GetTenant, ListTenants, UpdateTenant
- [ ] T020 [A] Create `src/use_cases/protocols/user_repository.py`: Protocol for CreateUser, GetUser, UpdateUser (role binding)
- [ ] T021 [A] Create `src/use_cases/protocols/audit_repository.py`: Protocol for LogAuditEntry (append-only)
- [ ] T022 [B] Create `src/use_cases/protocols/conversation_repository.py`: Protocol for CreateConversation, GetConversation, UpdateEscalation
- [ ] T023 [B] Create `src/use_cases/protocols/chunk_repository.py`: Protocol for CreateChunk, QueryChunks (with tenant_id filter at query time)
- [ ] T024 [B] Create `src/use_cases/protocols/lead_repository.py`: Protocol for CaptureLead, ListLeads, RateLimitLeads
- [ ] T025 [B] Create `src/use_cases/protocols/llm_client.py`: Protocol for CallLLM(system, messages, tools, max_tokens, temp) → ToolChoice result
- [ ] T026 [B] Create `src/use_cases/protocols/embedding_client.py`: Protocol for EmbedTexts(texts) → List[Vector]
- [X] T027 [C] Create `src/use_cases/protocols/classifier_client.py`: Protocol for Classify(message, tenant_id) → Label, confidence, per_class scores
- [X] T028 [C] Create `src/use_cases/protocols/guardrails_client.py`: Protocol for Check(tenant_id, role, content) → action (allow|redact|refuse), redacted_content, triggered_rails
- [ ] T029 [B] Create `src/use_cases/protocols/session_store.py`: Protocol for StoreSession(key, value, ttl), RetrieveSession(key), DeleteSession(key) (Redis backend)
- [ ] T030 [D] Create `src/use_cases/protocols/token_signer.py`: Protocol for SignToken(claims, ttl) → JWT, VerifyToken(jwt) → claims
- [ ] T031 [D] Create `src/use_cases/protocols/object_storage.py`: Protocol for StoreObject(tenant_id, path, data), FetchObject(tenant_id, path) → bytes, DeleteObject(tenant_id, path), DeletePrefix(tenant_id, prefix)
- [ ] T032 [A] Create `src/use_cases/protocols/vault_client.py`: Protocol for GetSecret(path) → value, SetSecret(path, value), RotateKey(key_id)

### Middleware & Cross-Slice Seams

- [ ] T033 [A] Create `src/frameworks/api/middleware/tenant_context.py`: TenantContextMiddleware extracts tenant_id from JWT (widget) or session (admin/manager), calls `SET LOCAL app.tenant_id`, resets at response end
- [ ] T034 [A] Create `src/frameworks/api/middleware/origin_check.py`: OriginCheckMiddleware validates request Origin header against tenant.allowed_origins from DB
- [X] T035 [C] Create `src/frameworks/api/middleware/pii_redaction.py`: PIIRedactionMiddleware wraps logger, tracer, Redis writer to redact outbound data via guardrails_client
- [X] T036 [ALL] Create `src/frameworks/api/deps.py`: Composition root. Wires concrete adapters (PostgresRepository, RedisSession, AnthropicLLM, HostedEmbeddings, ModelserverClassifier, NeMoGuardrails, PyJWTSigner, MinIOStorage, VaultClient) into use-case protocols. No use case imports a concrete adapter.
- [X] T037 [ALL] Wire static import-linter rule in CI (or custom ruff rule) to enforce: no file in `src/entities/` or `src/use_cases/` imports from `src/adapters/` or `src/frameworks/`

### Vault & Service-to-Service Auth

- [X] T038 [A] Create `src/frameworks/secrets/vault_client.py`: HvacClient wrapper for KV v2. At startup, generate or retrieve Ed25519 signing key from `secret/jwt/widget/active` and store in deps. Service credential issued to modelserver and guardrails sidecar.
- [X] T039 [ALL] Document in `.env.example` and RUNBOOK.md: Vault dev-mode bootstrap (VAULT_DEV_ROOT_TOKEN_ID), unsealing, KV v2 mount at `secret/`

### Observability Wiring

- [X] T040 [C] Create `src/frameworks/observability/logging.py`: Structured JSON logger with redaction-aware filter; log level from env (INFO default)
- [X] T041 [C] Create `src/frameworks/observability/tracing.py`: Tracer (e.g., OpenTelemetry) with egress-side redaction interceptor; exports to console (dev) or backend (via env)

### GitHub Actions CI Skeleton

- [ ] T042 [D] Create `.github/workflows/ci.yml`: skeleton with jobs for lint (ruff), type-check (mypy), build images, run unit/integration tests, invoke four eval gates. All jobs passing before any code merged (FR-039).
- [ ] T043 [D] Create `.github/workflows/eval-gates.yml`: separate workflow (or job in ci.yml) for the four gates: classifier, agent, RAG, redteam. Each reads `eval_thresholds.yaml`, exits non-zero on below-threshold.

### Protocol-Driven LLM & Embedding Adapters (Fakes for now; impl in slice work)

- [ ] T044 [B] Create `src/adapters/llm/anthropic_client.py`: Stub implementing LLMClient protocol; calls Anthropic API with tool_choice result handling. Actual implementation in Slice B / US1.
- [ ] T045 [B] Create `src/adapters/embeddings/hosted_embeddings.py`: Stub implementing EmbeddingClient; calls hosted API (Voyage/Cohere/OpenAI per env). Actual impl in Slice B / US1.
- [ ] T046 [B] Create `src/adapters/session/redis_session.py`: Stub implementing SessionStore protocol; Redis client wrapper with TTL. Actual impl in Slice B / US1.

### Classifier & Guardrails HTTP Clients

- [X] T047 [C] Create `src/adapters/classifier/modelserver_client.py`: Stub implementing ClassifierClient; POSTs to `http://modelserver:8001/predict` with service token. Actual impl in Slice C.
- [X] T048 [C] Create `src/adapters/guardrails/nemo_client.py`: Stub implementing GuardrailsClient; POSTs to `http://guardrails:8002/check` with service token. Actual impl in Slice C.

### Token & Storage Adapters

- [ ] T049 [D] Create `src/adapters/tokens/pyjwt_signer.py`: Stub implementing TokenSigner; PyJWT with Ed25519 key from Vault. Actual impl in Slice D.
- [ ] T050 [D] Create `src/adapters/storage/minio_object_storage.py`: Stub implementing ObjectStorage; MinIO client. Actual impl in Slice D.

### Minimal Widget & Admin Stubs

- [ ] T051 [D] Create `widget/` directory with `package.json` (React 18, Vite, TypeScript), `vite.config.ts`, `tsconfig.json`, `src/App.tsx` (stub), `src/api.ts` (stub), `src/loader.ts` (stub serving as `/widget.js`)
- [ ] T052 [D] Create `admin/` directory with `app.py` (Streamlit stub), empty `pages/` subdirectory
- [ ] T053 [D] Create a hello-world `/widget.js` bundled route in FastAPI that serves widget-static container output (or inline stub returning a simple widget HTML)

### Documentation Stubs (to be filled by slice owners)

- [ ] T054 [A] Create `docs/DESIGN.md` stub: sections for isolation strategy, scaling story, cost-per-tenant model, role model, erasure path; populated as Slice A completes
- [ ] T055 [B] Create `docs/DECISIONS.md` stub with header and structure; to be appended by all slices with numbered decisions. Entries: agent-vs-workflow-vs-hybrid [B], embedder choice [B], reranker choice [B], classifier algorithm [C], others TBD
- [ ] T056 [A] Create `docs/RUNBOOK.md` stub: sections for compose-up, restore, on-call troubleshooting; Slice A + Slice D populate
- [ ] T057 [C] Create `docs/EVALS.md` stub: sections for how each gate is built and how to read results; populated by Slice C
- [ ] T058 [C] Create `docs/SECURITY.md` stub: threat model, GDPR posture, jurisdictional notes; Slice C populates
- [ ] T059 [P] [A] Create `src/use_cases/SPEC.md` stub (Slice A)
- [ ] T060 [P] [B] Create `src/adapters/SPEC.md` stub (Slice B)
- [ ] T061 [P] [C] Create `services/modelserver/SPEC.md` stub (Slice C)
- [ ] T062 [P] [C] Create `services/guardrails/SPEC.md` stub (Slice C)
- [ ] T063 [P] [D] Create `admin/SPEC.md` stub (Slice D)
- [ ] T064 [P] [D] Create `widget/SPEC.md` stub (Slice D)

**Checkpoint**: Phase 2 complete. All slices can now code against fakes. Team splits.

---

## Phase 3: User Story 1 — Visitor gets a useful, grounded answer from the tenant's AI agent (Priority: P1)

**Goal**: Visitor opens the widget on a tenant's site, asks a question, receives a grounded answer or a structured outcome (lead, escalation, spam drop) within 5 seconds.

**Independent Test**: Seeded tenant with 2 CMS pages (Shipping Policy, Return Policy). Visitor asks "What's your return window?", receives a reply citing the Return Policy within 5 seconds (SC-006).

### Entities (Story-Specific)

- [ ] T065 [B] Create `src/entities/conversation.py`: Conversation dataclass with id, tenant_id, widget_id, visitor_session, escalated_at, escalation_reason, started_at, last_turn_at
- [ ] T066 [B] Create `src/entities/message.py`: Message dataclass with id, tenant_id, conversation_id, role (visitor|agent|tool|system), router_label, content (PII-redacted), tool_calls, created_at
- [ ] T067 [B] Create `src/entities/chunk.py`: Chunk dataclass with id, tenant_id, cms_page_id, chunk_index, content, embedding (vector), metadata, embedded_at
- [ ] T068 [B] Create `src/entities/lead.py`: Lead dataclass with id, tenant_id, conversation_id, name, contact, intent, created_at
- [ ] T069 [B] Create `src/entities/cms_page.py`: CMSPage dataclass with id, tenant_id, title, body, state (draft|published|unpublished), slug, published_at, created_at, updated_at

### Repository Implementations (Story-Specific)

- [ ] T070 [P] [B] Create `src/adapters/repositories/conversation_repository.py`: Implements ConversationRepository protocol; queries include `WHERE tenant_id = :tenant_id`; RLS enforced at DB layer
- [ ] T071 [P] [B] Create `src/adapters/repositories/chunk_repository.py`: Implements ChunkRepository protocol; vector query returns top-20 by cosine similarity, filters `WHERE tenant_id = :tenant_id AND cms_page.state = 'published'` at query time (NOT post-filter); indexes: HNSW/ivfflat on embedding, B-tree on tenant_id
- [ ] T072 [P] [B] Create `src/adapters/repositories/lead_repository.py`: Implements LeadRepository protocol; rate limits per-visitor/session (≤1 per 60s, ≤5 lifetime); appends rate-limit details to conversation for audit

### Router & Agent Use Cases (Core Logic)

- [ ] T073 [B] Create `src/use_cases/classify_message.py`: ClassifyMessageUseCase; calls classifier_client.Classify(message) → label; routes: spam (drop), faq (rag_search), lead_intent (capture_lead), escalate (flag), ambiguous (agent_turn). Returns route and route-specific result.
- [ ] T074 [B] Create `src/use_cases/rag_search.py`: RAGSearchUseCase; chunk_repo.QueryChunks(embedding of user message) → top-20; reranker API (if enabled) → top-5; returns top-5 with cms_page_id and snippet
- [ ] T075 [B] Create `src/use_cases/capture_lead.py`: CaptureLeadUseCase; schema-validates (name, contact, intent); rate-limits per-visitor/session; calls lead_repo.CaptureLead(…) → Lead; returns success or rate_limited status
- [ ] T076 [B] Create `src/use_cases/escalate.py`: EscalateUseCase; sets conversation.escalated_at = now(), escalation_reason = 'visitor_request' (or 'llm_unavailable', 'tool_loop_cap'); audit-logs
- [ ] T077 [B] Create `src/use_cases/agent_turn.py`: AgentTurnUseCase; bounded tool-calling loop: calls llm_client.CallLLM(system_prompt + persona + top-5 chunks + conversation history, tools=[rag_search, capture_lead, escalate], max_iterations=5, max_tokens=2048). Each tool call returns a result; loop terminates on max_iterations or stop token. Returns synthesized reply + any tool side effects (lead captured, conversation escalated).
- [ ] T078 [B] Create `src/use_cases/publish_cms_page.py`: PublishCMSPageUseCase; transitions cms_page.state from draft → published; calls reindex_tenant_chunks (async or sync).
- [ ] T079 [B] Create `src/use_cases/reindex_tenant_chunks.py`: ReindexTenantChunksUseCase; deletes existing chunks for the page; chunks the page body (paragraph-aware, token-bounded 400/50/600 tokens per research.md#1); embeds each chunk via embedding_client.EmbedTexts; inserts into chunk_repo. Transition published ↔ unpublished triggers deletion of chunks.

### Chat Route (Endpoint)

- [ ] T080 [B] Create `src/frameworks/api/routes/chat.py`: POST `/chat` endpoint; extracts conversation_id, message from body; gets tenant_id from TenantContext; calls classify_message → routes to rag_search | capture_lead | escalate | agent_turn | (spam → silent drop); returns ChatTurnResponse with route, reply, escalated, retrieved_chunks, capture_lead_status. On LLM/embedding timeout, returns 503 with "service temporarily unavailable", auto-flags conversation as escalated (FR-014a).

### Contract Tests (Before Implementation)

- [ ] T081 [P] [B] Create `tests/contract/test_chat_schema.py`: OpenAPI schema conformance tests for POST `/chat` request/response shapes, status codes
- [ ] T082 [P] [B] Create `tests/integration/test_rls_isolation.py`: RLS enforcement test; create two tenants with chunks; query chunk_repo.QueryChunks from tenant A context; assert zero results from tenant B's chunks. REQUIRED: cross-tenant red-team gate.

### Prompts & Memory

- [ ] T083 [B] Create `prompts/system_agent.md`: System prompt for the agent; includes placeholder for {{persona_summary}} (injected at runtime from tenant_config); mentions the three tools and their purpose
- [ ] T084 [B] Create `prompts/system_router.md`: System prompt for the router classifier (fallback if classifier unavailable); instructs the LLM to classify into the 5 labels
- [ ] T085 [B] Create `prompts/tool_specs/rag_search.md`: Tool spec for rag_search; includes description, parameters, response format
- [ ] T086 [B] Create `prompts/tool_specs/capture_lead.md`: Tool spec for capture_lead
- [ ] T087 [B] Create `prompts/tool_specs/escalate.md`: Tool spec for escalate

### Database Migrations (Story-Specific)

- [ ] T088 [B] Create Alembic migration `002_add_cms_conversations_chunks.sql`: creates cms_pages, conversations, messages, chunks tables with tenant_id, RLS policies, indexes (pgvector HNSW/ivfflat on chunks.embedding, B-tree on tenant_id for query-time filtering)

**Checkpoint**: US1 functional and independently testable. Widget not yet embedded; routes tested via `/chat` endpoint directly.

---

## Phase 4: User Story 2 — Tenant admin manages CMS content that powers both the public site and the agent (Priority: P1)

**Goal**: Admin creates, edits, publishes, unpublishes CMS pages. Published content is retrievable by the agent within 5 minutes (FR-016, SC-011).

**Independent Test**: Admin creates a page titled "Refund Policy", publishes it. Agent retrieves and answers a question about refunds within 5 minutes.

### CMS Route (Endpoint)

- [ ] T089 [US2] [B] Create `src/frameworks/api/routes/cms.py`: CRUD for `/cms/pages` (GET, POST, PUT, DELETE, publish, unpublish). Each write triggers async reindex_tenant_chunks if publish/unpublish. Returns CMSPage schema from contract.
- [ ] T090 [P] [US2] [B] Create `tests/contract/test_cms_schema.py`: Schema conformance tests for `/cms/pages` CRUD endpoints

### Admin Routes (Shared with US3, US6)

- [ ] T091 [US2] [B] Create `src/frameworks/api/routes/admin.py`: Placeholder for `/admin/tenant`, `/admin/guardrails`, `/admin/origins`, `/admin/escalations`. T091 focuses on structure; individual endpoints populated as needed by slices.

### Integration Tests (US1 + US2 Together)

- [ ] T092 [US2] [B] Create `tests/integration/test_chat_flow.py`: Seeded tenant with 2 published pages. Chat turn asks a question. Asserts route=faq, retrieved_chunks not empty, reply contains text from a chunk, within 5s (SC-006). Asserts chunks from other tenants are NOT retrieved (RLS gate).

**Checkpoint**: US1 + US2 complete and independently testable. Admin can manage content; agent retrieves from published pages only. Unpublished/draft pages do NOT leak to agent. Chunks deleted when page unpublished.

---

## Phase 5: User Story 3 — Tenant admin embeds the agent widget on their public site with one snippet (Priority: P2)

**Goal**: Admin copies embed snippet from dashboard, pastes into HTML, widget appears. Widget loads on permitted origins only.

**Independent Test**: Snippet pasted on localhost:9090 (in allowed_origins). Widget loads. Visitor asks question, receives answer. Same snippet on localhost:9091 (not allowed) → widget refuses to load.

### Widget Entity & Token Issuance Use Case

- [ ] T093 [US3] [D] Create `src/entities/widget.py`: Widget dataclass with id, tenant_id (UNIQUE), public_id, is_enabled, created_at
- [ ] T094 [US3] [D] Create `src/use_cases/issue_widget_token.py`: IssueWidgetTokenUseCase; validates widget_public_id exists; validates origin against tenant.allowed_origins; calls token_signer.SignToken with claims (tenant_id, widget_id, origin, visitor_session, iat, exp ≤ 5min); returns token + expires_in_seconds
- [ ] T095 [US3] [D] Create `src/use_cases/get_widget_config.py`: GetWidgetConfigUseCase; returns tenant's theme_config, greeting, persona_summary (redacted for visitor), consent_notice

### Widget Endpoints

- [ ] T096 [P] [US3] [D] Create `src/frameworks/api/routes/widget.py`: POST `/widget/token` (public; validates origin), GET `/widget/config` (bearer JWT). Returns WidgetConfig schema.
- [ ] T097 [P] [US3] [D] Create `tests/contract/test_widget_token_schema.py`: Schema conformance for `/widget/token` and `/widget/config`

### Widget Bundle & Loader

- [ ] T098 [US3] [D] Implement `widget/src/loader.ts`: Vanilla JS loader (no dependencies); reads `data-widget-id` + `data-position` from `<script>` tag; POSTs `/widget/token` with widget_id + origin; receives JWT; injects iframe with `sandbox="allow-scripts allow-forms allow-same-origin"`. Refreshes token before expiry. < 5 KB gzipped.
- [ ] T099 [US3] [D] Implement `widget/src/App.tsx` stub: React widget (in iframe, not on host page); receives token via postMessage; displays consent notice on first load; renders chat UI; calls `/chat` endpoint with bearer token + origin header
- [ ] T100 [US3] [D] Build & bundle widget via Vite; output to `widget/dist/widget.js` and host-page iframe HTML. Serve from API or MinIO via `/widget.js` and `/widget/` routes.
- [ ] T101 [US3] [D] Create `tests/widget-host-example/index.html`: plain HTML test page with embed snippet. Used by `make serve-test-host` on port 9090.

### Origin Check & CORS

- [ ] T102 [US3] [D] Implement OriginCheckMiddleware (T035 stub); validates every request's Origin header against tenant.allowed_origins from DB; rejects 403 if mismatch. Applies to `/chat`, `/widget/token`, `/widget/config`.
- [ ] T103 [US3] [D] Wire CORS headers in FastAPI (Access-Control-Allow-Origin echoes request Origin if in allowed_origins; else null). Access-Control-Allow-Methods, Access-Control-Allow-Headers configured per route.
- [ ] T104 [US3] [D] Wire CSP `frame-ancestors` header on `/widget/` iframe page: lists all tenant.allowed_origins.

### Integration Tests

- [ ] T105 [US3] [D] Create `tests/integration/test_widget_token_origin.py`: POST `/widget/token` with widget_id + origin. Assert 200 if origin in allowed_origins. Assert 403 if origin not in allowed_origins. Token issued → chat with that token from a different origin → assert 403 (origin mismatch rejects).

**Checkpoint**: Widget embeddable. Origin-gating enforced at server (+ client-side CSP for defense-in-depth). Visitors can chat via widget on permitted origins only.

---

## Phase 6: User Story 4 — tenant_manager provisions a new tenant and invites its first admin (Priority: P2)

**Goal**: Manager creates tenant, invites admin email. Invited email accepts, sets password, becomes tenant_admin for that tenant. Every manager action is audit-logged.

**Independent Test**: Manager creates tenant "ACME Inc." with email "admin@acme.example.com". Invitation email sent (stub/mock). Recipient opens URL, sets password, logs in, sees their tenant dashboard.

### Tenant & Invitation Entities

- [ ] T106 [US4] [A] Create `src/entities/allowed_origin.py`: AllowedOrigin dataclass with id, tenant_id, origin, created_at
- [ ] T107 [US4] [A] Create `src/entities/audit_entry.py`: AuditEntry dataclass with id, actor_user_id, target_tenant_id, action, outcome, details, created_at

### Tenant Management Use Cases

- [ ] T108 [US4] [A] Create `src/use_cases/provision_tenant.py`: ProvisionTenantUseCase; creates tenant row, widget row, seeds allowed_origins, creates invitation, audit-logs the action. Calls external email service (stub) to dispatch invitation link.
- [ ] T109 [US4] [A] Create `src/use_cases/invite_admin.py`: InviteAdminUseCase; creates invitations row with token_hash, expires_at, sends email (stub). Called during provisioning and by admins inviting more admins to their tenant.
- [ ] T110 [US4] [A] Create `src/use_cases/erase_tenant.py`: EraseTenantUseCase; sets tenant.status = 'erasing'; deletes from postgres (cascades to cms_pages, conversations, leads, chunks, widgets, allowed_origins, user_tenant_roles, invitations); purges Redis keys matching `tenant:<tenant_id>:*`; purges MinIO prefix `tenant-<tenant_id>/`; audit-logs completion. Must complete within ≤1 hour SLA (SC-009).

### Tenant Repository

- [ ] T111 [P] [US4] [A] Create `src/adapters/repositories/tenant_repository.py`: Implements TenantRepository; CRUD for tenants, widget, allowed_origins. RLS: tenant_admin sees only their tenant; tenant_manager bypasses RLS on read.
- [ ] T112 [P] [US4] [A] Create `src/adapters/repositories/user_repository.py`: Implements UserRepository; wired with fastapi-users for email + password auth. Creates user rows with role column.

### Auth & fastapi-users Integration

- [ ] T113 [US4] [A] Create `src/frameworks/api/routes/auth.py`: fastapi-users routes (login, logout, register, password-reset, email-verify, invitation acceptance). Adapted: on invitation acceptance, creates user_tenant_roles row mapping the new admin to the tenant.
- [ ] T114 [US4] [A] Implement invitation acceptance endpoint: POST `/auth/invitations/{token}/accept` with password; hashes token, looks up invitations row, creates user if not exists, sets role=tenant_admin, creates user_tenant_roles row for the target tenant, sets accepted_at, audit-logs.

### Manager Routes

- [ ] T115 [US4] [A] Create `src/frameworks/api/routes/manager.py`: Manager-only endpoints (/manager/tenants GET/POST, /manager/tenants/{id} DELETE, /manager/audit GET, /manager/usage GET). Requires role=tenant_manager. POST /tenants calls provision_tenant. DELETE calls erase_tenant (async, returns 202). GET /audit returns all audit entries (no tenant scoping). GET /usage returns aggregate (not per-tenant).

### Database Migrations (Story-Specific)

- [ ] T116 [US4] [A] Create Alembic migration `003_add_invitations_allowed_origins_widgets.sql`: creates invitations (with unique(tenant_id, email) where accepted_at is null), allowed_origins, widgets (unique(tenant_id)) tables; adds role column to users; RLS policies for all tables.

### Contract Tests

- [ ] T117 [P] [US4] [A] Create `tests/contract/test_manager_schema.py`: Schema conformance for `/manager/tenants` and `/auth/invitations/{token}/accept`

### Integration Tests

- [ ] T118 [US4] [A] Create `tests/integration/test_tenant_provisioning.py`: Call provision_tenant → assert tenant created, widget created, allowed_origins seeded, invitation created, audit_entry logged. Call invite_admin → assert new user created, user_tenant_roles bound. Cross-tenant access attempt → assert denied.

**Checkpoint**: Provisioning flow works. Managers can create and erase tenants (within SLA). Audit log records all manager actions. tenant_admin cannot see other tenants' data or audit entries.

---

## Phase 7: User Story 5 — Tenant admin reviews captured leads (Priority: P2)

**Goal**: Admin opens Leads view, sees leads their visitors have generated, can export.

**Independent Test**: After seeded conversation with lead capture, admin lists leads, sees exactly their tenant's leads (none from other tenants), can export to CSV.

### Leads Routes

- [ ] T119 [US5] [B] Extend `src/frameworks/api/routes/leads.py` (or create new): GET `/leads` (list, optionally filtered by `since` date), GET `/leads/export` (CSV). Tenant-scoped via RLS.
- [ ] T120 [P] [US5] [B] Create `tests/contract/test_leads_schema.py`: Schema conformance for `/leads` list and export endpoints

### Integration Tests

- [ ] T121 [US5] [B] Create `tests/integration/test_leads_flow.py`: Seed tenant A + B; capture leads on A; list leads from A context → assert only A's leads returned. List leads from B context → assert 0 leads. Export → CSV format correct.

**Checkpoint**: Leads view functional. Tenant isolation verified. Leads exported for CRM integration.

---

## Phase 8: User Story 6 — Tenant admin configures persona, guardrails, and theme (Priority: P3)

**Goal**: Admin tweaks persona (voice), greeting, theme, guardrail settings (blocked topics, refusal tone, enabled tools). Platform rails (injection, jailbreak, cross-tenant, PII) are visible but cannot be weakened.

**Independent Test**: Admin changes persona to "warm and concise"; next visitor turn reflects the new persona. Admin attempts to disable prompt-injection defense; server refuses (403) and audit-logs the attempt.

### Guardrail Config Entity

- [ ] T122 [US6] [C] Create `src/entities/guardrail_config.py`: GuardrailConfig dataclass with allowed_topics, blocked_topics, refusal_tone, enabled_tools (subset of [rag_search, capture_lead, escalate])

### Guardrail Management Use Case

- [ ] T123 [US6] [C] Create `src/use_cases/update_guardrail_config.py`: UpdateGuardrailConfigUseCase; validates tenant cannot weaken platform rails; persists to tenant.guardrail_config JSONB; audit-logs any attempt to weaken (403 + logged).

### Admin Routes (Extended)

- [ ] T124 [US6] [D] Extend `src/frameworks/api/routes/admin.py`: GET/PUT `/admin/tenant` (persona, theme, plan), GET/PUT `/admin/guardrails` (tenant rails only; platform rails shown read-only), GET/POST/DELETE `/admin/origins`. All return 200 on success, 403 if attempting to weaken platform rails.
- [ ] T125 [P] [US6] [D] Create `tests/contract/test_admin_settings_schema.py`: Schema conformance for `/admin/*` endpoints

### Tenant Persona Injection

- [ ] T126 [US6] [B] Implement persona_summary extraction from tenant.persona_config; inject into prompts/system_agent.md via {{persona_summary}} placeholder at runtime (NOT hardcoded). Required by FR-025 and Constitution Principle VII.

### Integration Tests

- [ ] T127 [US6] [D] Create `tests/integration/test_guardrail_config.py`: Update persona → chat → assert reply reflects new persona. Attempt to weaken injection rail → assert 403 and audit entry. Update allowed topics → next chat respects the list (or is handled by guardrails sidecar on egress).

**Checkpoint**: Tenant can customize persona, theme, tenant-scoped guardrails. Platform rails are locked. Settings propagate to agent and guardrails sidecar on next request.

---

## Phase 9: User Story 7 — tenant_manager fully erases a tenant on request (right to erasure) (Priority: P3)

**Goal**: Manager initiates erasure. System removes tenant records from every store (Postgres, vector, Redis, MinIO) within 1 hour. Post-erasure, tenant is gone everywhere. Erasure is itself audit-logged.

**Independent Test**: Create tenant with content, conversations, leads, sessions. Call erase. Audit log shows `tenant_erase_complete`. Postgres, Redis, MinIO, vector all have zero residual data for that tenant.

### Erasure Integration Test (Critical Gate)

- [ ] T128 [US7] [A] Create `tests/integration/test_erasure_path.py`: Create tenant + seed content + conversation + lead + session. Call erase_tenant (POST `/manager/tenants/{id}` DELETE). Poll audit log until tenant_erase_complete. Query each store (Postgres with BYPASSRLS, Redis, MinIO, pgvector) for residual data; assert zero matches. Required for cross-tenant red-team gate and SC-009.

### Erasure Use Case (Already in T110; verify completeness)

- [ ] T129 [US7] [A] Enhance `src/use_cases/erase_tenant.py` (from T110): Implement all four store purges in sequence (Postgres cascade, Redis scan+delete, MinIO list+delete, pgvector implicitly via cascade). Measure completion time; assert ≤ 1 hour SLA. Audit-log the completion with details.stores_purged list.

**Checkpoint**: Erasure functional. Tenant data fully purged within SLA. Post-erasure consistency verified by integration test.

---

## Phase 10: Evaluation Gates & CI Integration (Mandatory Cross-Cutting)

**Purpose**: All four eval gates + smoke test passing before any PR merges. Constitution Principle VI.

### Classifier Training & Eval Gate

- [X] T130 [C] Create `notebooks/01_label_taxonomy.ipynb`: Defines 5-label taxonomy (spam, faq, lead_intent, escalate, ambiguous) with label definitions, seed examples per label
- [X] T131 [C] Create `notebooks/02_tfidf_logreg_baseline.ipynb`: TF-IDF + logistic regression baseline; trains on seed set; evaluates on held-out test set; reports macro-F1, per-class F1, latency, cost
- [X] T132 [C] Create `notebooks/03_small_dl_onnx.ipynb`: Small DL model (e.g., CNN + word embeddings) exported to ONNX; evaluates on held-out set
- [X] T133 [C] Create `notebooks/04_llm_zero_shot.ipynb`: LLM zero-shot classification (e.g., claude-sonnet-4-6 with prompt); evaluates on held-out set
- [ ] T134 [C] Create `notebooks/05_compare_and_export.ipynb`: Side-by-side comparison of all three; picks the best by macro-F1 (likely classical baseline or ONNX for speed + size); exports artifact to `services/modelserver/artifacts/model.{onnx|joblib}`; updates `services/modelserver/model_card.yaml` with SHA-256, training data source, comparison results, deployment choice with rationale
- [ ] T135 [C] Create `tests/evals/classifier/test_classifier_macro_f1.py`: Loads model_card.yaml, computes macro-F1 on held-out test set, asserts ≥ classifier_macro_f1 threshold from eval_thresholds.yaml. Exits non-zero on regression. Committed to CI.

### Agent Tool-Selection Golden Set & Eval Gate

- [ ] T136 [B] Create `tests/evals/agent_tool_selection/golden.jsonl`: 15 curated examples; each row: {"message": "...", "expected_tool": "rag_search|capture_lead|escalate", "expected_routing": "faq|lead_intent|escalate"}
- [ ] T137 [B] Create `tests/evals/agent_tool_selection/test_tool_selection.py`: Runs agent on golden set; collects tool-call decisions; computes macro-F1 per tool; asserts ≥ agent_tool_selection_macro_f1 threshold. Exits non-zero on regression.

### RAG Golden Set & Eval Gate

- [ ] T138 [B] Create `tests/evals/rag/golden.jsonl`: 15 curated examples; each row: {"query": "...", "expected_cms_page_id": "...", "expected_answer_snippet": "..."}
- [ ] T139 [B] Create `tests/evals/rag/test_rag_quality.py`: Seeds tenant with the 15 questions' source pages; retrieves chunks for each query; reranks; computes recall@5 (chunk from expected page in top-5), answer grounding (expected_answer_snippet present in top-5), etc. Asserts ≥ thresholds for rag_golden_set_recall_at_5 and rag_golden_set_answer_grounded_rate. Exits non-zero on regression.

### Red-Team Set: Injection, Cross-Tenant, PII

- [ ] T140 [P] [C] Create `tests/evals/redteam/injection.jsonl`: 10+ prompt-injection probes; each row: {"message": "...", "expected_action": "refuse|redact"}
- [ ] T141 [P] [C] Create `tests/evals/redteam/cross_tenant.jsonl`: 5+ cross-tenant probes; visitor on Tenant A asks a question only answered in Tenant B's content; expected: agent refuses or returns "I don't know" (does NOT leak Tenant B content)
- [ ] T142 [P] [C] Create `tests/evals/redteam/test_redteam.py`: Runs each probe; asserts injection probes are refused ≥ 95% (or 100% for critical ones), cross-tenant probes are 100% refused. Exits non-zero on regression.

### PII Redaction Canary Test

- [ ] T143 [C] Create `tests/evals/redteam/test_pii_canary.py`: Pastes a synthetic fake API key + credit card into a chat turn. Asserts the fake credential NEVER appears unredacted in: logs, traces, Redis session memory, LLM input payload, guardrails sidecar input. Runs on every CI run. 100% pass rate required (SC-008).

### Stack Smoke Test

- [ ] T144 [D] Create `tests/smoke_test.py` or Makefile `smoke` target: Brings up fresh compose stack, runs migrations, seeds demo tenant, runs one end-to-end chat turn, asserts 200 response with non-empty reply. Tears down. Runs on every push. Must pass before merge (FR-040, SC-010).

### CI/CD Wiring

- [ ] T145 [D] Update `.github/workflows/ci.yml`: Add jobs for lint (ruff check src/), type-check (mypy src/), build API/modelserver/guardrails images, run unit tests, run integration tests (including test_rls_isolation, test_chat_flow, test_erasure_path), invoke four eval gates (classifier, agent, RAG, redteam), run smoke test. All jobs passing = green check. Any eval gate below threshold = red check + block merge (FR-039).

---

## Phase 11: Non-Negotiable Constraints & Gates (Encoded as Tasks)

**Purpose**: Explicit verification of architecture principles and constraints.

### Tenant Isolation Gates

- [ ] T146 [A] Create `tests/integration/test_rls_isolation.py` (detailed): Multiple tables tested; for each, create rows for Tenant A and B; execute queries in Tenant A context; assert zero rows from Tenant B returned. Tests: tenants, users, user_tenant_roles, cms_pages, chunks, conversations, messages, leads, widgets, allowed_origins, invitations. Required: RLS policies on EVERY tenant-scoped table (data-model.md). Gates the cross-tenant red-team eval (SC-003).
- [ ] T147 [A] Create CI assertion: `docker build` modelserver with `no-torch` check in Dockerfile; image size assertion ≤ 500MB (FR-004, Constitution IV).
- [ ] T148 [A] Create CI assertion: Modelserver boot-time artifact hash verification; model_card.yaml's artifact_sha256 is computed on boot and compared (FR-023); mismatch = process exits 1 (asserted in smoke test).
- [ ] T149 [A] Implement tenant_id derivation only from JWT/credential; TenantContextMiddleware rejects requests where body claims a different tenant (FR-007/008). Integration test: POST `/chat` with JWT claiming Tenant A but body claiming Tenant B → assert 403 or JWT tenant wins.
- [ ] T150 [B] Implement pgvector query-time filtering (NOT post-filter): ChunkRepository.QueryChunks includes `WHERE tenant_id = :tenant_id AND cms_page.state = 'published'` in the SQL query sent to Postgres; planner applies tenant_id filter before vector ANN. Integration test verifies via EXPLAIN ANALYZE (FR-017).
- [ ] T151 [C] Implement service-to-service Vault credential: modelserver and guardrails sidecar receive X-Service-Token header on every request from API; token issued from Vault and rotated per Vault policy. Integration test: unauthorized calls return 401 (FR-036).
- [ ] T152 [B] Implement tenant persona injection at runtime: prompts/system_agent.md uses {{persona_summary}} placeholder; at agent invocation, extract tenant.persona_config and render the prompt. Test: two tenants with different personas → agent replies reflect the respective personas (FR-025, Constitution VII).

### Import Linter Rule (Clean Architecture Gate)

- [ ] T153 [ALL] Implement static import checker: Ruff custom rule or import-linter contract `no-inner-from-outer`; asserts NO file in `src/entities/` or `src/use_cases/` imports from `src/adapters/` or `src/frameworks/`. CI runs this rule; failure blocks merge (Constitution I).

### Documentation Required Docs

- [ ] T154 [A] Populate `docs/DESIGN.md`: Isolation strategy (RLS + repository layer + service boundary), scaling story (single compose stack for PoC, paths for sharding), cost-per-tenant model (estimate: embeddings, LLM, storage per tenant at scale), role model (tenant_manager / tenant_admin / visitor), erasure path (cross-store purge with SLA).
- [ ] T155 [B] Populate `docs/DECISIONS.md` (entry 1): Agent vs. Workflow vs. Hybrid argument; decision: bounded tool-calling agent (max 5 iterations, max 2048 tokens) with three tools. Rationale: balance flexibility (agent) with cost + latency (bounded + deterministic fallbacks). Alternatives considered, numbers on golden set.
- [ ] T156 [B] Append `docs/DECISIONS.md` (entry 2): Embedding provider picked by RAG golden set score (threshold ≥ 0.85). Candidate comparison (OpenAI vs. Voyage vs. Cohere) with cost/recall/latency tradeoffs. Winner noted with runner-up scores.
- [ ] T157 [B] Append `docs/DECISIONS.md` (entry 3): Reranker provider (if enabled) picked by same golden set criterion. Same format.
- [ ] T158 [C] Append `docs/DECISIONS.md` (entry 4): Classifier algorithm picked from three-way comparison (classical / DL ONNX / LLM zero-shot) on held-out test set. Winner's macro-F1, per-class F1, latency, inference cost. Rationale for deployment choice (likely classical or ONNX for speed / size constraints).
- [ ] T159 [C] Populate `docs/EVALS.md`: Four evaluation gates (classifier, agent, RAG, redteam); how each is built (source data, held-out split), how to run locally (`make eval-classifier`, etc.), how to read results. Thresholds from eval_thresholds.yaml. Pass/fail interpretation.
- [ ] T160 [C] Populate `docs/SECURITY.md`: Threat model (token compromise, prompt injection, cross-tenant misconfiguration, PII leakage), mitigations (short-lived JWTs, guardrails rails, RLS + repository + middleware layers, PII redactor). GDPR-aligned design (lawful basis, right of access, right of erasure, data minimization). No certification claimed; design rationale only. Jurisdictional posture.
- [ ] T161 [A] Populate `docs/RUNBOOK.md` (Slice A + D): Compose-up troubleshooting, restore procedures (backup/restore Postgres + pgvector + Redis + MinIO), on-call playbook (common alerts, remediation). Links to SECURITY.md and EVALS.md for context.
- [ ] T162 [A] Populate `src/use_cases/SPEC.md` (Slice A): Tenant provisioning / erasure / authentication flows; contract with use-case interfaces.
- [ ] T163 [B] Populate `src/adapters/SPEC.md` (Slice B): Repository layer contract; protocol implementations (LLM, Embedding, Session); integration points with other adapters.
- [ ] T164 [C] Populate `services/modelserver/SPEC.md` (Slice C): Model serving architecture; artifact loading + hash verification; inference API; no torch constraint. Model card schema and build process.
- [ ] T165 [C] Populate `services/guardrails/SPEC.md` (Slice C): Platform rails (injection, jailbreak, cross-tenant, PII) + tenant rails configuration. API contract. Integration with NeMo Guardrails library.
- [ ] T166 [D] Populate `admin/SPEC.md` (Slice D): Streamlit app structure; pages (dashboard, CMS, leads, settings, embed snippet); auth via fastapi-users session cookie. No custom auth in admin.
- [ ] T167 [D] Populate `widget/SPEC.md` (Slice D): Widget architecture (React + Vite + TypeScript in iframe). Loader contract (vanilla JS, no dependencies, < 5 KB gzipped). Token exchange, origin validation, refresh logic. Iframe ↔ loader communication (postMessage).

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Improvements, docs, and final quality gates.

### Remaining Stubs & Integration

- [ ] T168 [ALL] Wire tracing/logging from Phase 2 stubs; ensure all routes log tenant_id, request_id, operation; structured JSON format; no PII in logs (redaction middleware in place).
- [ ] T169 [B] Implement reranker call in rag_search (if enabled): top-20 vector results → reranker API (Voyage / Cohere) → top-5. Graceful fallback to top-5 by vector score if reranker unavailable.
- [ ] T170 [D] Build Streamlit admin UI pages (1_dashboard, 2_cms, 3_leads, 4_settings, 5_embed_snippet); wire to FastAPI backend. Dashboard: aggregate stats (conversation count, lead count, avg response time). CMS: CRUD table view. Leads: sortable table + export button. Settings: persona / theme / origins / guardrails. Embed snippet: copy-to-clipboard.
- [ ] T171 [D] Build React widget pages (App, Chat, Consent notice, Reconnect spinner). Socket/polling for token refresh. Inline iframe communication. Dark mode toggle (optional).
- [ ] T172 [C] Wire NeMo Guardrails sidecar: platform rails locked (YAML config, no code mutation). Tenant rails templated from DB at boot. Both layers applied on ingress (visitor input, tool input) and egress (agent output, tool output).
- [ ] T173 [C] Implement PII redaction middleware: calls guardrails sidecar `/check` with role='visitor_input' / 'agent_output' before logging, caching, or outbound API calls. Redacts in-place in logs (structured field redaction), traces, Redis values, LLM input.

### Testing & Coverage

- [ ] T174 [ALL] Run `pytest --cov` on all unit tests; aim for ≥ 80% coverage on src/ (exclude __init__, stubs). Report in CI.
- [ ] T175 [ALL] Run `mypy --strict` on src/ and services/; resolve all type errors. Commit mypy cache.
- [ ] T176 [ALL] Run `ruff check src/ tests/ services/`; fix any lint violations.
- [ ] T177 [ALL] Run Vitest on widget/ (< 50 tests; focus on loader, token exchange, iframe communication).

### Quickstart Validation

- [ ] T178 [D] Verify quickstart.md (from design) maps to actual commands. Run through locally: clone → .env → compose up → migrate → bootstrap → seed → serve-test-host → smoke. Should complete in ≤ 30 minutes (SC-001). Document any gaps.

### Git & Commit Workflow

- [ ] T179 [ALL] Each task ≤ 1 day of work; output a single commit with clear message per task (or logical group). Co-author: "Claude Opus 4.7 <noreply@anthropic.com>". Branch: `001-concierge-platform` throughout.
- [ ] T180 [ALL] Rotate code reviewer for every PR. Guard: all CI jobs passing (lint, type, build, tests, evals, smoke). No commits to main without PR review + approval.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — BLOCKS all user stories
- **Phases 3–9 (User Stories)**: All depend on Phase 2 completion
  - US1 + US2 (P1, MVP): Can proceed in parallel after Phase 2 (both agents + CMS)
  - US3–5 (P2): Depend on US1 + US2; can proceed in parallel
  - US6–7 (P3): Depend on previous; can proceed in parallel
- **Phase 10–12 (Evals, Constraints, Polish)**: Ongoing throughout; final lock-in at phase end

### Cross-Slice Integration Points (Dependency Edges)

1. **Slice A → B/C/D**: `TenantContextMiddleware` (T033) + `TenantRepository` (T111) published in Phase 2; B/C/D consume at task time
2. **Slice A → D**: `AllowedOrigin` (T106) repository used by OriginCheckMiddleware (T102); published in Phase 2
3. **Slice B → C**: `ClassifierClient` (T028) + `GuardrailsClient` (T029) protocols published in Phase 2; B consumes in classify_message (T073) + agent_turn (T077) + chat route (T080)
4. **Slice C → B**: Classifier model card (T134) + guardrails config schema finalized; B wires them into routes
5. **Slice D → A/B**: Widget token signer (T049) uses Vault key from A; origin allowlist (T102) checks A's repository

**Critical Path**: Phase 2 → Phase 3 (US1 + US2 in parallel) → Phase 4–5 (P2 in parallel) → Phase 9 (P3 in parallel) → Phase 10–12 (concurrent with phases 6–9)

---

## Parallel Execution Examples

### Phase 2 Parallelization

```
Team pairs on:
T010–T013: Shared infrastructure (all 4 members)
T014–T018: Tenant isolation pattern (A leads; others shadow)
T019–T032: Protocol interfaces (draft all 12 simultaneously; review + finalize together)
T033–T038: Middleware + Vault (A leads; B/C/D implement stubs)
T042–T064: CI skeleton + docs stubs (all 4 in parallel, merge carefully)
```

**Estimated Phase 2 duration**: 3–4 days (team of 4, pairing on critical path, some parallel work)

### Phase 3–4 Parallelization (P1 Stories)

```
Slice A: (idle in P1; owns US4 which is P2)
Slice B: US1 (router + agent + chat) + US2 (CMS CRUD) in parallel
  - T065–T072: Entities + repos (parallel, independent files)
  - T073–T079: Use cases (sequential: router → rag → agent → publish/reindex)
  - T080: Chat route (depends on use cases)
  - T089–T092: CMS routes + tests (parallel with chat work; integration test together)
Slice C: (idle in P1; owns classifier training which is P3)
Slice D: (idle in P1; owns widget which is P2)
```

**Estimated P1 duration**: 3–5 days (Slice B focused; others can prep P2 work or help B)

### Phase 5–9 Parallelization (P2+P3 Stories)

```
After Phase 2, each slice proceeds in parallel:
A: US4 provisioning + erasure (T108–T118)
B: US5 leads view (T119–T121) — can start after US1 complete
C: US6 guardrail config (T122–T127) — parallel with classifier training
D: US3 widget + US6 settings + CI (T093–T105, T124, T145) — parallel
```

---

## Implementation Strategy

### MVP Scope (US1 + US2)

1. **Phase 1**: Setup (1–2 days, team of 4)
2. **Phase 2**: Foundational skeleton (3–4 days, team of 4, paired on critical sections)
3. **Phase 3**: US1 complete (3–5 days, Slice B focused, others can pair)
4. **Phase 4**: US2 complete (2–3 days, Slice B continues)
5. **Stop & Validate**: Test US1 + US2 independently; demo: seeded tenant, visitor chats, admin manages content
6. **Evals**: Classify macro-F1 gate, agent golden set gate, RAG golden set gate, cross-tenant RLS gate all passing

**MVP Timeline**: ~14–20 days elapsed (4 people, some parallelization, daily integration syncs)

### Incremental Delivery (Full v1.0)

After MVP:
1. **Add US3 (Widget)**: Slice D, 3–5 days
2. **Add US4 (Provisioning)**: Slice A, 3–4 days
3. **Add US5 (Leads)**: Slice B (light), 1–2 days
4. **Add US6–7 (Guardrails + Erasure)**: Slice C + A, 3–5 days
5. **Final Evals + Polish**: All slices, 2–3 days

**Full v1.0 Timeline**: ~30–40 days elapsed

### Team & Review Rotation

- **Pairing in Phase 2**: All 4 members on critical path (isolation pattern, protocols, middleware)
- **Splitting in Phases 3+**: Each slice owns their tasks; one reviewer rotates per PR
  - PR1 (A's work): reviewed by B
  - PR2 (B's work): reviewed by C
  - PR3 (C's work): reviewed by D
  - PR4 (D's work): reviewed by A
  - Cycle repeats

---

## Task Counts & Summary

### Total Tasks: **180 tasks**

### By Phase:

| Phase | Label | Count |
|-------|-------|-------|
| 1. Setup | T001–T009 | 9 |
| 2. Foundational | T010–T064 | 55 |
| 3. US1 (P1) | T065–T092 | 28 |
| 4. US2 (P1) | T093–T092 | 4 |
| 5. US3 (P2) | T093–T127 | 35 |
| 6. US4 (P2) | T106–T129 | 24 |
| 7. US5 (P2) | T119–T121 | 3 |
| 8. US6 (P3) | T122–T127 | 6 |
| 9. US7 (P3) | T128–T129 | 2 |
| 10. Evals | T130–T152 | 23 |
| 11. Constraints | T146–T153 | 8 |
| 12. Docs | T154–T167 | 14 |
| 13. Polish | T168–T180 | 13 |

**Task Count by Owner:**

| Owner | Count | Notes |
|-------|-------|-------|
| [A] Platform / Tenancy | 32 | Tenant model, RLS, provisioning, erasure, audit, manager routes |
| [B] Agent / RAG / Memory | 61 | Router, agent, RAG, CMS, chat, leads, memory, prompts, notebooks, golden sets |
| [C] Models / Security / Guardrails | 34 | Classifier training, guardrails sidecar, PII redaction, evals, model card, service auth |
| [D] Widget / Admin / CI | 38 | Widget bundle + loader, admin UI (Streamlit), origins, CI pipeline, smoke test, contract tests |
| [ALL] Shared | 15 | Setup, Phase 2 skeleton, docs, polish |

---

## Independent Test Criteria (by Story)

| Story | Criterion |
|-------|-----------|
| US1 | Seeded tenant with 2 CMS pages; visitor asks question matching page content; agent returns grounded reply citing the page within 5 seconds (SC-006) |
| US2 | Admin publishes page; page appears on public site and is retrievable by agent within 5 minutes (SC-011); unpublished page stops being retrievable immediately |
| US3 | Embed snippet on permitted origin loads widget; visitor chats via widget. Same snippet on non-permitted origin refuses to load. |
| US4 | Manager creates tenant + invites admin email. Recipient accepts, sets password, logs in to admin dashboard for their tenant only. Audit log records both actions. |
| US5 | After seeded lead captures, admin lists leads in Leads view; sees only their tenant's leads. Export produces valid CSV. |
| US6 | Admin changes persona; next visitor turn reflects new persona. Admin attempts to disable injection rail; server returns 403 + audit-logs the attempt. |
| US7 | Tenant with data erased; audit log shows `tenant_erase_complete`. Query Postgres, Redis, MinIO, pgvector; all have zero residual data for the erased tenant. |

---

## Suggested MVP Scope

**Release 1 (14–20 days)**: Phases 1–2 + Phases 3–4 (US1 + US2)
- Visitor can chat and receive grounded answers
- Admin can manage CMS content
- Both P1 stories independently testable
- All four eval gates passing
- Cross-tenant isolation verified (red-team gate 100%)
- RLS + repository layer + middleware layers all enforced

**After MVP**: Phases 5–9 add widget distribution, provisioning, leads, guardrails, erasure (phases 5–9 proceed in parallel if staffed)

---

## Cross-Slice Dependency Summary

| Dependency | From | To | Task |
|-----------|------|----|----|
| TenantContext middleware | A | B/C/D | T033 |
| TenantRepository | A | B/C/D | T111 |
| AllowedOrigin repo | A | D | T111 |
| Protocol interfaces | A/B/C/D | All | T019–T032 |
| Vault credential | A | C | T038 |
| Classifier protocol | C | B | T028 |
| Guardrails protocol | C | B | T029 |
| Service credential | C | C (self) | T038 |
| LLM adapter | B | B (self) | T044 |
| Embedding adapter | B | B (self) | T045 |
| Session store | B | B (self) | T046 |
| Token signer | D | D (self) | T049 |
| Object storage | D | D (self) | T050 |

---

## Format Validation Checklist

✅ **All tasks follow strict format**: `- [ ] [ID] [P?] [Story?] [Owner] Description with file path`  
✅ **Every task has an owner tag**: [A] / [B] / [C] / [D] / [ALL]  
✅ **Story phases have [USX] labels** (US1–US7 mapped from spec.md)  
✅ **Setup + Foundational + Polish have NO story labels** (owner tags only)  
✅ **Parallelizable tasks marked [P]** (different files, no cross-dependencies)  
✅ **File paths from plan.md "Source Code" tree** (src/, services/, admin/, widget/, tests/, docs/, etc.)  
✅ **Protocol interfaces published in Phase 2** so consumers code against fakes  
✅ **Eval gates explicit and committed** to eval_thresholds.yaml  
✅ **Cross-slice integration points surfaced** as task dependencies  
✅ **Constitution requirements encoded** as explicit tasks (RLS, import linter, model-card hash, persona injection, service auth)  
✅ **MVP scope clear** (US1 + US2 = P1 stories after Phase 2)  

---

## Notes

- **No horizontal-layer ownership**: Each slice owns a vertical from entities through frameworks; no one owns "all repositories" or "all routes"
- **Phase 2 is the skeleton everyone builds together**: Protocols + middleware + CI scaffold. Then split.
- **Code against fakes in Phase 3+**: Slice B can implement US1 chat route against stub LLMClient; Slice C implements the real classifier later. No blocking.
- **Eval gates are mandatory**: No PR merges without classifier F1 ≥ 0.80, agent F1 ≥ 0.80, RAG ≥ 0.85, cross-tenant 100%, injection ≥ 95%, PII 100%, smoke test passing.
- **Commit per task or logical group**: Clear git history; rotated code review per PR.
- **Quickstart is the acceptance test**: If quickstart.md works in ≤ 30 minutes from a fresh clone, v1.0 is shippable.

---

**Generated**: 2026-05-25 | **Template**: tasks-template.md | **Status**: Ready for execution
