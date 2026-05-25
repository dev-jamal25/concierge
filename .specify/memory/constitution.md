<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (uninitialized) → 1.0.0
Bump rationale: Initial ratification. No prior numbered version existed; the
                file was a placeholder template. First concrete content is
                published as 1.0.0 per the project's semantic-versioning policy.

Principles defined (all new):
  I.   Clean Architecture & The Dependency Rule (NON-NEGOTIABLE)
  II.  SOLID via Dependency Inversion
  III. Tenant Isolation (NON-NEGOTIABLE)
  IV.  Hosted Inference, Lean Containers
  V.   Defense-in-Depth Security
  VI.  Evals as CI Gates
  VII. Spec-Driven, No Vibe Coding

Sections added:
  - Core Principles (I–VII)
  - Technical Constraints
  - Development Workflow & Quality Gates
  - Governance

Sections removed: none (template placeholders replaced).

Templates / docs requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check section is a
     generic stub ("[Gates determined based on constitution file]"); it will
     be expanded against these principles when /speckit-plan next runs against
     a feature. No structural change required now.
  ✅ .specify/templates/spec-template.md — no change needed; spec template is
     principle-agnostic and already accommodates the required-docs discipline
     introduced by Principle VII.
  ✅ .specify/templates/tasks-template.md — no change needed; task categories
     already cover setup, foundational, story, polish phases that Principle VI
     (eval gates) and Principle VII (spec-driven) naturally slot into.
  ⚠ CLAUDE.md — currently a stub. Recommend a follow-up amendment to point at
     this constitution and the required-docs set (DESIGN.md, SPEC.md,
     DECISIONS.md, RUNBOOK.md, EVALS.md, SECURITY.md). Not required for v1.0.0.
  ⚠ eval_thresholds.yaml — Principle VI references this file. It does not yet
     exist in the repo. Must be created before the first CI gate runs;
     tracked as a deferred item, not a constitution defect.

Deferred TODOs: none in the constitution body. All placeholders resolved.
-->

# Concierge Constitution

Concierge is a multi-tenant AI SaaS. The principles below are the load-bearing
rules that every contributor, every PR, and every architectural decision must
respect. Two principles are explicitly NON-NEGOTIABLE; violating either is
grounds to block a merge regardless of demo quality.

## Core Principles

### I. Clean Architecture & The Dependency Rule (NON-NEGOTIABLE)

The codebase is organized into four concentric layers. Source-code dependencies
MUST point only inward; nothing in an inner layer may import from any outer
layer. The layers, from innermost to outermost, are:

1. **Entities** — pure Python dataclasses: `Tenant`, `Lead`, `Conversation`,
   `Chunk`, `Widget`. No DB imports, no FastAPI imports, no third-party
   libraries beyond the standard library.
2. **Use Cases** — `CaptureLeadUseCase`, `RAGSearchUseCase`, `EscalateUseCase`,
   `ClassifyMessageUseCase`, `ProvisionTenantUseCase`. Business logic only.
   Use cases MUST depend on abstract repository / adapter interfaces, never on
   SQLAlchemy, FastAPI, or any other framework.
3. **Interface Adapters** — concrete `TenantRepository`, `LeadRepository`,
   `ChunkRepository`, `ConversationRepository`, plus the LLM, embedding,
   classifier, and guardrails adapters. Each repository owns exactly one
   aggregate. Adapters translate between use cases and infrastructure.
4. **Frameworks & Drivers** — FastAPI routes, SQLAlchemy models, pgvector,
   Redis, MinIO, Vault, the NeMo sidecar, and the modelserver container. Only
   this layer is permitted to know that any specific infrastructure exists.

Rationale: the dependency rule is what makes the system testable, swappable,
and survivable as vendors and frameworks change. Compromise it and the codebase
collapses into the framework it sits on.

### II. SOLID via Dependency Inversion

- **Single Responsibility**: each repository owns one aggregate; each use case
  does one thing end-to-end.
- **Open/Closed**: LLM and embedding adapters implement abstract interfaces;
  swapping providers MUST NOT require touching any use case.
- **Dependency Inversion**: use cases depend on abstract interfaces; concrete
  implementations are injected at process startup (composition root). Use
  cases MUST NOT import concrete adapters, repositories, or framework types.

Rationale: vendors, models, and stores will change. The seams defined by these
principles are what let those changes be reversible.

### III. Tenant Isolation (NON-NEGOTIABLE)

This is the #1 rule. A working agent that leaks data across tenants is worth
less than a plain agent that holds the wall.

- Every persistent table MUST carry `tenant_id` as a UUID column.
- Postgres Row-Level Security MUST enforce isolation at the database layer.
  Each request sets `app.tenant_id` via `SET CONFIG` and the value MUST be
  reset at the end of the request — no exceptions, no leaked sessions.
- The repository layer MUST scope every query by `tenant_id` as a second,
  independent layer of defense (belt and braces with RLS).
- pgvector retrieval MUST filter by `tenant_id` at query time, not as a
  post-filter on returned rows.
- `tenant_id` MUST be derived from the verified authentication token (widget
  JWT or service credential) on every request. It MUST NEVER be read from the
  request body, query string, or any client-supplied header.
- A merge that weakens any of the above — including "temporarily for a demo" —
  is rejected outright.

Rationale: cross-tenant leakage is the one failure mode that cannot be
apologized away. Defense in depth (token → RLS → repository scope → vector
filter) is non-optional.

### IV. Hosted Inference, Lean Containers

- No container in this project may include `torch` or any GPU runtime.
- LLM and embedding calls MUST go to hosted APIs.
- Classifiers MUST be trained offline (notebook / Colab), exported to ONNX or
  joblib, and served by a lean `modelserver` container using `onnxruntime`
  and `scikit-learn`. The container image MUST stay under 500 MB.

Rationale: bloated images and accidental GPU dependencies destroy iteration
speed and inflate cost. Keeping inference at hosted APIs and the
classifier-serving layer minimal keeps the system shippable.

### V. Defense-in-Depth Security

- CORS is not authentication. The widget MUST authenticate with a signed,
  short-lived JWT, and the server MUST perform an origin check against the
  tenant's allowed origins on every request.
- CORS headers and CSP `frame-ancestors` are defense-in-depth controls only;
  they are never the sole gate.
- Service-to-service calls MUST use a shared service credential fetched from
  Vault. Credentials MUST NOT be hardcoded, baked into images, or stored in
  environment files committed to the repo.
- Platform guardrail rails (prompt-injection defenses, jailbreak defenses,
  cross-tenant defenses) are locked. A tenant configuration MUST NOT be able
  to weaken or disable them.

Rationale: every layer must assume the others can fail. Single-point security
in a multi-tenant system is a future incident.

### VI. Evals as CI Gates

Four CI gates MUST run on every PR, with thresholds committed in
`eval_thresholds.yaml` at the repo root:

1. **Classifier macro-F1** — the routing/classification model on a held-out set.
2. **Agent tool-selection golden set** — 15 examples covering tool routing.
3. **RAG golden set** — 15 (query, expected-doc, expected-answer) triples.
4. **Red-team set** — prompt injection plus cross-tenant probes.

Any regression below the committed threshold blocks the merge. Thresholds may
only be lowered with an accompanying entry in `DECISIONS.md` justifying the
change with numbers. A polished demo with broken or absent gates is worth less
than a rough one with working gates.

Rationale: without committed evaluation numbers, "it works" is opinion. The
gates make quality regressions visible and reversible.

### VII. Spec-Driven, No Vibe Coding

- Every major component MUST have a `SPEC.md` committed before any
  implementation code lands.
- Every architectural decision MUST be recorded in `DECISIONS.md` and backed by
  a number from a held-out or golden-set evaluation. "We tried it and it felt
  right" is not a decision record.
- The required document set for the project is: `DESIGN.md`, `SPEC.md`,
  `DECISIONS.md`, `RUNBOOK.md`, `EVALS.md`, `SECURITY.md`. These are owned by
  the team, not by any single contributor.
- Prompts live under `prompts/` and are version-controlled. Tenant persona,
  tone, and policy MUST be injected at runtime from tenant config; they MUST
  NOT be hardcoded into prompt templates.
- Spec-driven or AI-scaffolded, every teammate owns every line of code they
  ship and MUST be able to explain any part of the system on Friday.

Rationale: the team's velocity is bounded by its shared understanding. Specs,
decisions, and versioned prompts are how that understanding scales past one
head.

## Technical Constraints

- **Language & runtime**: Python (server side); the widget is a separate
  browser bundle.
- **Storage**: Postgres with pgvector for embeddings; MinIO for object
  storage; Redis for ephemeral state. Postgres RLS is mandatory (see
  Principle III).
- **Secrets**: Vault is the single source of truth for service credentials and
  signing keys. No secret may live in `.env` files committed to the repo, in
  container images, or in code.
- **Inference**: hosted-API LLM and embeddings only. The `modelserver`
  container hosts ONNX / joblib classifiers under 500 MB.
- **Guardrails**: a sidecar (NeMo or equivalent) enforces locked platform
  rails. Tenants configure persona and content policy via tenant config, never
  by editing rails.
- **Prompts**: live in `prompts/`, version-controlled, with runtime injection
  of tenant persona and policy.

## Development Workflow & Quality Gates

- **Branching**: feature branches per `/speckit-git-feature`. Merges to `main`
  require a passing CI run.
- **CI gates** (in addition to standard lint/type/test): the four eval gates
  defined in Principle VI, plus a tenant-isolation regression test that
  exercises RLS and repository-layer scoping. A failure of any gate is a hard
  block.
- **Required docs before merge**: any PR introducing a new component MUST land
  with its `SPEC.md`. Any PR encoding an architectural choice MUST update
  `DECISIONS.md` with the supporting number.
- **Code review**: at least one reviewer who is not the author. The reviewer
  is expected to verify constitution compliance, not just code mechanics.
- **Complexity**: complexity that violates a principle MUST be recorded in the
  plan's Complexity Tracking table with a concrete reason and the simpler
  alternative that was rejected. Unjustified complexity is rejected.

## Governance

- This constitution supersedes ad-hoc convention. Where this document and a
  README, comment, or chat message disagree, this document wins until
  formally amended.
- **Amendments** require: (a) a PR that edits this file, (b) a Sync Impact
  Report at the top of the file describing what changed and which templates
  / docs need updating, and (c) a reviewer who is not the author.
- **Versioning policy** for this constitution follows semantic versioning:
  - **MAJOR**: a principle is removed, redefined incompatibly, or governance
    is changed in a way that invalidates prior decisions.
  - **MINOR**: a new principle or major section is added, or existing
    guidance is materially expanded.
  - **PATCH**: clarifications, wording fixes, or non-semantic refinements.
- **Compliance review**: every PR review MUST verify the change does not
  violate a NON-NEGOTIABLE principle (I and III). Reviewers MUST decline
  merges that weaken tenant isolation or break the dependency rule, even when
  the change is otherwise small.
- **Runtime guidance**: contributors use the templates under
  `.specify/templates/` and the commands under `/speckit-*` for spec, plan,
  task, and analysis workflows. `CLAUDE.md` (and any equivalent agent guide)
  must point at this constitution and the required-docs set.

**Version**: 1.0.0 | **Ratified**: 2026-05-25 | **Last Amended**: 2026-05-25
