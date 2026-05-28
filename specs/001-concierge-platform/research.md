# Phase 0 — Research & Decisions

**Feature**: Concierge Multi-Tenant AI SaaS Platform
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-25

Each decision below records: **Decision**, **Rationale**, **Alternatives
considered**, and the **Number** that backs it (per Constitution Principle
VII — every architectural decision backed by a number on a held-out or
golden set). Where the number is a target that's measured later, it's
flagged as **"To be validated at Phase 2"** and the threshold is committed
to `eval_thresholds.yaml` so a regression blocks merge.

---

## 1. Chunking strategy

**Decision**: Paragraph-aware chunking with token-bounded windows
(target 400 tokens, overlap 50 tokens, hard cap 600 tokens), respecting
heading boundaries. Implemented in
`src/use_cases/reindex_tenant_chunks.py`.

**Rationale**: CMS content is structured (titles, headings, paragraphs).
A naïve fixed-width chunker that splits mid-sentence loses the local
context that grounds answers; paragraph-aware chunking preserves the
unit of meaning while the token bound keeps embedding cost predictable.
The 400-token target sits below typical embedding-API context windows
with margin, and the 50-token overlap reduces boundary loss for queries
whose answer straddles two paragraphs.

**Alternatives considered**:
- *Fixed 512-token windows, no overlap* — simpler but loses cross-paragraph
  context.
- *Sentence-level chunking* — too granular; degrades retrieval recall on
  multi-sentence answers.
- *Whole-page chunking* — too coarse; one chunk per page makes
  retrieval undiscriminating.

**Number**: Threshold committed to `eval_thresholds.yaml` as
`rag_golden_set_recall_at_5 ≥ 0.85`. To be validated at Phase 2 against
the 15-triple RAG golden set; result entered in `docs/DECISIONS.md`.

### 1a. Validation: three-way chunker bake-off (Owner B addendum, 2026-05-27)

The "paragraph-aware" decision above is the **starting baseline**, not
the locked winner. Per the validation requirement, Slice B will benchmark
three chunker variants against the 15-triple RAG golden set and record
the winning variant in `docs/DECISIONS.md` (new entry "Decision 1.5 —
Chunker variant"). The three variants:

1. **Fixed-size baseline**: 500-token windows, no overlap, no heading
   awareness. The naïve floor that any structured chunker must beat.
2. **Paragraph-aware recursive**: split on `\n\n`, then merge to a
   400-token target with 50-token overlap, hard cap 600 tokens
   (the implementation already shipped in `reindex_tenant_chunks.py`).
3. **Header-first recursive**: split on Markdown headings (`#`/`##`/`###`),
   then recursively split each section on `\n\n` to fit the 400/50/600
   bounds. **Each child chunk is prepended with its full heading path**
   (e.g. `H1 > H2 > H3\n\n<body>`) so the embedder and downstream
   retrieval carry structural context.

**Metrics reported per variant** (single table in DECISIONS.md):
- `hit@5` — the gate metric (must satisfy `rag_golden_set_recall_at_5 ≥ 0.85`)
- `MRR` (mean reciprocal rank) — catches ranking-quality differences `hit@5` hides
- mean retrieval latency (ms) — catches a chunker that wins on accuracy but blows
  the per-turn 5s SLA budget

**Decision rule**: winner = highest `hit@5` that also satisfies the gate
*and* has retrieval latency ≤ 200ms p95 (the pgvector budget from plan.md).
Ties on `hit@5` broken by `MRR`; further ties broken by lower latency.
If the fixed-size baseline wins, that itself is a finding worth
documenting (and a signal the corpus is simpler than expected).

The chunker code lives in `backend/app/use_cases/_chunkers/`
(one module per variant) so the bake-off can swap implementations
without touching `reindex_tenant_chunks.py`.

---

## 2. Retrieval improvement

**Decision**: Cross-encoder rerank over the top-20 vector-retrieved
chunks, returning the top-5 reranked to the agent.

**Rationale**: Vector-only retrieval has a known weakness at the
top-of-list — embeddings capture topical similarity but not entailment.
A cross-encoder rerank (using a hosted reranker API, e.g. Cohere Rerank
or Voyage Rerank) re-scores the candidate set against the actual query
text and consistently lifts P@1 / NDCG@5 on small golden sets. It's a
single extra HTTP call, so cost is bounded and predictable at PoC scale.

**Alternatives considered**:
- *Query rewriting (HyDE / multi-query)* — interesting but introduces a
  second LLM call per turn, blowing the per-turn latency budget.
- *Metadata filtering* (e.g. by CMS page tags) — useful but tenants
  may not consistently tag content; rerank works with arbitrary content.
- *Hybrid BM25 + dense* — defensible but doubles the index complexity;
  rerank gives most of the lift at a fraction of the moving parts.

**Number**: Threshold committed to `eval_thresholds.yaml` as
`rag_golden_set_answer_grounded_rate ≥ 0.85`. Comparison baseline
(no-rerank) MUST be measured and recorded in `docs/DECISIONS.md` so the
+x improvement is auditable.

### 2a. A/B harness and ship/no-ship rule (Owner B addendum, 2026-05-27)

Tightens the "must be measured" requirement into an automated A/B test
that runs in CI and a binary ship/no-ship rule:

**Test**: `tests/evals/rag/test_reranker_ab.py` runs the existing 15-triple
RAG golden set **twice** — once with reranker enabled, once disabled
(the `rag_search.py` code already supports both modes via graceful
fallback). Records `hit@5` for both modes plus the delta in
`docs/DECISIONS.md` (entry 3 — Reranker provider).

**Ship/no-ship rule**: reranker stays in v1 if and only if it lifts
`hit@5` by **≥ 0.05 (5 percentage points)** over the no-rerank baseline
on the golden set. Below that, the reranker's cost (~$0.001/call +
~200ms latency) is not paid back at PoC scale and the v1 deployment
disables it (`RERANKER_URL` left unset). The graceful-fallback path
already in place means the change is config-only — no code revert needed.

**Rationale**: 5pp is a meaningful, statistically defensible margin on
a 15-triple set; smaller deltas risk noise. The rule is auditable and
the test re-runs on every CI build, so a future re-evaluation (e.g.
after corpus expansion) is one CI run away.

**FR-019 fallback**: FR-019 requires at least one retrieval improvement
in production. If the A/B test triggers the no-ship rule and the
reranker is disabled, **query rewriting** satisfies FR-019 as the
in-production retrieval improvement. The agent's `rag_search` tool
already rewrites the visitor's raw question into a focused search query
before retrieval (implemented in `agent_turn.py` — the `query` arg
passed to `RAGSearchUseCase` is the agent-composed search string, not
the visitor's verbatim message). No additional code is needed; the
fallback is already live.

---

## 3. LLM provider

**Decision**: Anthropic, model `claude-sonnet-4-6` by default for the
agent loop and router-LLM fallback. Provider is swappable via the
`LLMClient` protocol in `src/use_cases/protocols/llm_client.py`.

**Rationale**:
- Strong tool-calling reliability (the router and agent loop both depend
  on well-formed `tool_use` outputs).
- 200k token context window — more than enough headroom for top-k
  retrieved chunks + system prompt + persona + conversation history.
- Prompt caching available — useful for the long-lived system prompt
  and tenant persona (a per-tenant cache key).
- Per Constitution Principle IV, hosted-API only; no local weights.

**Alternatives considered**:
- *OpenAI gpt-4o family* — comparable tool calling but smaller default
  context and weaker function-call format adherence in our internal
  evals.
- *Locally hosted open model (vLLM / llama.cpp)* — violates Principle IV
  (lean containers / no torch / hosted only).

**Number**: Agent tool-selection golden set threshold committed as
`agent_tool_selection_macro_f1 ≥ 0.80` at Phase 2.

---

## 4. Embedding provider

**Decision**: Hosted embedding API. Default chosen by cost-per-1M-tokens
× retrieval-golden-set score; provider swappable behind
`EmbeddingClient`. Candidate set: OpenAI `text-embedding-3-small`,
Voyage `voyage-3`, Cohere `embed-v3`.

**Rationale**: At PoC scale (≤10 tenants × ~200 pages × ~400 tokens per
chunk ≈ 800k tokens to embed and a much smaller query-time volume),
embedding cost is dominated by the per-token rate. The retrieval
golden set picks the candidate that maximises grounded-answer rate; the
adapter pattern keeps the choice reversible.

**Alternatives considered**:
- *Local sentence-transformers* — would bring `torch` into a container,
  violating Principle IV.
- *Bring-your-own-fine-tuned embeddings* — out of scope for v1.0;
  bootstrap cost > benefit at PoC scale.

**Number**: Pick decided at Phase 2 by side-by-side RAG-golden-set
score, recorded in `docs/DECISIONS.md`. Threshold:
`rag_golden_set_recall_at_5 ≥ 0.85` (same gate as chunking).

---

## 5. Redis session TTL

**Decision (revised 2026-05-27, Owner B)**: **60 minutes per conversation
key, fixed expiry** (TTL set on first write only; subsequent writes
update the value but do NOT reset the TTL).

**Rationale**: Concierge-style conversations frequently span lunch breaks,
multi-tab browsing, and short interruptions; the original 30-minute
window cuts off visitors mid-session and forces context loss. Doubling
to 60 minutes covers the realistic long tail (per session-length data
on consumer-facing chat widgets) without meaningfully expanding the
blast radius of a leaked session token — the token itself is short-lived
(widget JWT exp ≤ 5 min, per §6) and Redis values are PII-redacted
before write.

**Fixed (not sliding)** because:
- A *fixed* expiry gives a **predictable upper bound** on how long
  any single session's data lives in Redis, which is cleaner to argue
  in `docs/SECURITY.md` and to GDPR-aligned reviewers (data minimisation
  principle).
- A *sliding* expiry can keep an idle-but-touched conversation alive
  indefinitely under adversarial activity, which expands the blast radius.
- The trade-off cost (a 65-minute visitor session loses last-5-min
  context) is small for concierge use and recoverable (visitor can
  restate; agent re-grounds via `rag_search`).

**Implementation note for adapters/session/redis_session.py**:
`store()` MUST set the TTL only on key creation (use `SET ... NX EX <ttl>`
or `SETNX`+`EXPIRE`, then plain `SET` without `EX` for subsequent updates).
A `touch()` method is explicitly NOT added — sliding TTL is rejected here.

**Alternatives considered**:
- *Sliding 60-minute window* — better UX for active conversations but
  loses the predictable-upper-bound property above.
- *Hours / days* — increases blast radius without proportional benefit.
- *Per-turn (no persistence between turns)* — breaks multi-turn
  context; visitor would have to restate prior turns.
- *Original 30 minutes (fixed)* — too aggressive a cut-off in practice;
  the original number was a guess, not measurement-backed.

**Number**: Acceptable as a one-paragraph justification per Constitution
Principle VII for memory (`FR-024`, which only requires "stated TTL
with documented rationale"). No held-out gate required. Decision also
recorded in `docs/DECISIONS.md` (new entry "Decision 5 — Memory TTL").

---

## 6. JWT algorithm and key rotation

**Decision**: EdDSA (Ed25519) signing keys. Keys generated and stored
in Vault KV v2 under `secret/jwt/widget/<key-id>`. The active signing
key is published with a 5-day overlap on rotation; clients identify
keys by the `kid` header.

**Rationale**: Ed25519 produces small signatures and tokens, signs and
verifies fast, and avoids the curve / parameter footguns of RS256
configurations. PyJWT supports EdDSA via PyNaCl. Vault is already a
required dependency; storing keys there avoids a new secret-management
surface.

**Alternatives considered**:
- *HS256 with a shared secret* — easier but every service that verifies
  needs the secret, expanding the blast radius if any service is
  compromised. Asymmetric keys keep the signer privilege isolated.
- *RS256* — fine but larger keys / tokens and historically more
  parameter-choice mistakes (key length, padding).

**Number**: No gate; documented as a security decision in
`docs/DECISIONS.md` and `docs/SECURITY.md`.

---

## 7. Row-Level Security pattern

**Decision**: At the start of every request, the
`TenantContextMiddleware` (Slice A) extracts the tenant UUID from the
verified JWT or service credential and executes
`SET LOCAL app.tenant_id = '<uuid>';` on the SQLAlchemy session. RLS
policies on every tenant-scoped table filter by
`current_setting('app.tenant_id')::uuid`. The value is reset implicitly
at transaction end (SET LOCAL) and re-set at the start of the next
request.

**Rationale**:
- `SET LOCAL` is transaction-scoped — there is no leak across requests
  even if a connection is reused from the pool.
- `current_setting('app.tenant_id')::uuid` in the policy gives Postgres
  the discriminator without making the application responsible for
  passing it in every WHERE clause. The repository layer still adds an
  explicit `WHERE tenant_id = :tenant_id` as a second line of defence
  (Principle III, defence in depth).
- `tenant_manager` operations use a dedicated role
  (`concierge_manager`) that has `BYPASSRLS` only on the audit table;
  manager operations on tenant data go through soft RPC functions and
  are themselves audit-logged.

**Alternatives considered**:
- *Application-only filtering* — a single bug exposes everyone; RLS at
  the database is the wall that holds when the application logic
  fails.
- *Per-tenant schemas / databases* — strong isolation but explodes
  operational cost at the team's current scale (10 schemas × N tables
  × backups × migrations).

**Number**: Gate — `tests/integration/test_rls_isolation.py` MUST
pass; cross-tenant red-team set MUST be 100% refused.

---

## 8. PII redaction integration point

**Decision**: A `PIIRedactor` invoked at the egress boundary of every
outbound channel: structured logger filter, tracer span exporter,
Redis writer for session memory, and any HTTP body sent to the LLM /
embedding / guardrails sidecar. Implementation: NeMo Guardrails' built-in
PII rail (regex + classifier) called via the `GuardrailsClient`
protocol; the same sidecar that enforces injection / jailbreak rails
also handles redaction.

**Rationale**: Single source of truth for what counts as PII. By
intercepting at egress, we redact in one place rather than scattering
patterns at every call site. The CI canary test
(`tests/evals/redteam/test_redteam.py::test_pii_canary`) pastes a fake
API key into a chat turn and asserts it never appears unredacted in
logs / traces / Redis / outbound LLM payload.

**Alternatives considered**:
- *In-application regex at every log call* — fragile; one missed call
  site is a leak.
- *Post-processing logs offline* — too late; the data has already left
  the boundary.

**Number**: Gate — PII canary test MUST be 100% redacted on every
CI run (Constitution Principle V, spec `FR-035`).

---

## 9. Modelserver artifact verification

**Decision**: The modelserver computes `sha256(model_artifact)` at boot
and compares against the `artifact_sha256` field in
`model_card.yaml`. Mismatch is a fatal error — the process exits with
non-zero before binding the HTTP port. Both files are baked into the
image; a model swap requires a new image build AND a `model_card.yaml`
update in the same commit.

**Rationale**: Prevents accidental or malicious artifact drift. Anchors
the model card as the canonical record of what's deployed. Aligns with
Constitution Principle VII (every decision backed by a number — the
model card records the held-out metrics).

**Alternatives considered**:
- *Sign artifacts with a private key* — defensible but adds Vault key
  ceremony for a PoC; hash-in-card achieves 80% of the assurance at 20%
  of the operational cost.
- *Trust the image registry* — registry compromise is a real threat;
  a self-verifying boot guards against it.

**Number**: Boot-time assertion; CI builds the image and runs `docker
run` to confirm it comes up cleanly with a matching card and fails fast
with a mismatched card (smoke test).

---

## 10. fastapi-users multi-tenancy pattern

**Decision**: `users` table holds the global identity + a single global
role column (`role: 'tenant_manager' | 'tenant_admin'`). For
`tenant_admin` users, a join table `user_tenant_roles (user_id,
tenant_id)` lists the tenants they administer. `tenant_manager` has no
rows in `user_tenant_roles`; their authorization scope is the platform
itself, not any tenant. Login is email + password (Argon2id), with
standard email verification and password reset flows from fastapi-users.

**Rationale**: Matches the role model in `spec.md` exactly (3 roles, only
`tenant_manager` crosses tenant boundaries). Keeps the user identity
unified — one human is one row in `users` — while supporting both
single-tenant and (future) multi-tenant `tenant_admin`. fastapi-users'
extension hooks let us add the tenant lookup without rewriting auth
internals.

**Alternatives considered**:
- *Per-tenant `users` tables* — strong isolation but breaks fastapi-users
  and forces a join across schemas to know who someone is.
- *Single role column, no join table* — works for v1.0 (one admin per
  tenant) but forces a schema migration the moment a tenant wants
  two admins. Cheap to add now.

**Number**: No gate; covered by the tenant isolation regression test
(any auth path that returns rows MUST respect RLS).

---

## 11. Classifier label taxonomy

**Decision**: Five mutually exclusive labels —
`spam | faq | lead_intent | escalate | ambiguous`. The router dispatches
the first four to a dedicated path without invoking the LLM agent;
`ambiguous` is the only label that opens the LLM tool-loop. Trained
offline in `notebooks/` from a curated seed set + synthetic augmentation;
labels and seed sources recorded in `services/modelserver/model_card.yaml`.

**Rationale**:
- Mutually exclusive labels make macro-F1 a meaningful headline metric.
- The four direct-handled labels cover the high-volume, low-ambiguity
  cases — visitor wins by getting fast, deterministic responses; the
  platform wins by not spending LLM budget on obvious cases.
- `ambiguous` is the explicit "I don't know — ask the agent" channel,
  preventing miscategorisation under threshold.

**Alternatives considered**:
- *Two labels (`route_to_agent | direct_action`)* — collapses too much
  information; we lose the ability to drop spam without an LLM call.
- *Multi-label* — needlessly complicates training and the routing
  logic for negligible coverage gain.

**Number**: Gate — `classifier_macro_f1 ≥ 0.80` on the held-out test
set, committed to `eval_thresholds.yaml`. The chosen approach
(classical / DL / LLM zero-shot) is decided by the comparison in
`notebooks/05_compare_and_export.ipynb` and recorded in
`docs/DECISIONS.md`.

---

## Open items (to be resolved during slice work)

These do not block Phase 1 design but are flagged for slice owners to
record numbers in `docs/DECISIONS.md` as decisions are made:

- **Embedding model selection** (Slice B): runs the bake-off and records
  the winner and runner-up scores.
- **Reranker provider selection** (Slice B): same bake-off pattern.
- **Classifier algorithm selection** (Slice C): the three-way comparison
  (TF-IDF + logreg / small DL ONNX / LLM zero-shot) is committed to the
  notebook and the winner exported.
- **Streamlit auth flow** (Slice D): how the admin UI authenticates
  against the FastAPI auth surface. Default: same fastapi-users session
  cookie; admin UI calls the API as the logged-in user.

---

## Validation summary

| # | Decision | Status |
|---|----------|--------|
| 1 | Paragraph-aware chunking (400/50/600 tokens) — baseline; 3-way bake-off picks winner (§1a) | Threshold committed; bake-off due in Slice B |
| 2 | Cross-encoder rerank top-20 → top-5; A/B ship-rule ≥0.05 hit@5 lift (§2a) | Threshold committed; A/B test in Slice B |
| 3 | Anthropic claude-sonnet-4-6 default | Tool-selection gate committed |
| 4 | Hosted embeddings, provider TBD via bake-off | Threshold committed; pick in Slice B |
| 5 | Redis session TTL = 60 min, fixed expiry | Justified inline (no gate required) |
| 6 | Ed25519 JWT in Vault, 5-day overlap rotation | Documented decision (no gate) |
| 7 | `SET LOCAL app.tenant_id` + RLS policies | Cross-tenant red-team gate at 100% |
| 8 | Egress-side PII redactor via NeMo PII rail | Canary test required at 100% |
| 9 | SHA-256 boot-time artifact verification | Image build smoke test |
| 10 | fastapi-users + `user_tenant_roles` join | Covered by RLS gate |
| 11 | 5-label classifier taxonomy | Macro-F1 ≥ 0.80 committed |

All NEEDS CLARIFICATION items from the spec are resolved. Phase 1 may
proceed.
