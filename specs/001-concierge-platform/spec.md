# Feature Specification: Concierge Multi-Tenant AI SaaS Platform

**Feature Branch**: `001-concierge-platform`

**Created**: 2026-05-25

**Status**: Draft

**Input**: Build Concierge — a multi-tenant AI SaaS where any business signs up,
gets an isolated tenant, manages its website content in a CMS, and embeds an
AI agent on its public site.

## Clarifications

### Session 2026-05-25

- Q: Target scale for v1.0? → A: PoC scale — up to 10 tenants, ~200 CMS pages per tenant, 50 concurrent visitors platform-wide.
- Q: Availability target for v1.0? → A: Best-effort, no formal SLA. Single compose stack; downtime tolerated for restarts and recovery; daily backups; manual restore documented in `RUNBOOK.md`.
- Q: CMS page lifecycle? → A: Three explicit states — `draft` (saved, invisible to public site + agent), `published` (visible to both), `unpublished` (archived, invisible to both, recoverable). Transitions are admin-driven; no scheduled publishing in v1.0.
- Q: External-service (LLM / embeddings) failure-mode UX? → A: Bounded retry with exponential backoff inside the per-turn time budget; if still failing, fail closed with a clear "service temporarily unavailable" message AND auto-flag the conversation as escalated for tenant_admin follow-up. Never fabricate an answer.
- Q: Compliance jurisdiction posture? → A: GDPR-aligned (design only, no certification claimed). Design follows GDPR principles — lawful basis, right to access, right to erasure, data minimization, PII redaction in logs. Widget shows a one-line consent notice on first interaction. SOC 2 / CCPA are out of scope for v1.0.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visitor gets a useful, grounded answer from the tenant's AI agent (Priority: P1)

A visitor on a tenant's public website opens the embedded chat widget, asks a
question, and receives an answer grounded in that tenant's published content.
The system routes the visitor's message: clear FAQ questions are answered from
tenant content, sales/contact intent triggers a structured lead capture,
explicit "talk to a human" requests are flagged for follow-up, and spam is
silently dropped. Only ambiguous or multi-step turns are handed to the AI agent.

**Why this priority**: This is the core value loop of the product. Every other
capability exists to enable or improve this conversation. If this works, the
product has a story to sell; if it does not, nothing else matters.

**Independent Test**: With a seeded tenant containing a small set of CMS pages,
a visitor can open the embedded widget on a test host page, ask a question
answered by the seeded content, and receive a grounded reply that cites or
matches the seeded material — within five seconds.

**Acceptance Scenarios**:

1. **Given** a tenant with at least one published CMS page about its
   shipping policy, **When** a visitor asks "What's your return window?",
   **Then** the agent responds with the policy from that page, not a generic
   answer, and the response references content from that tenant only.
2. **Given** a visitor message clearly stating "I want to talk to someone in
   sales — here's my email", **When** it is processed, **Then** the system
   captures the visitor's name, contact, and stated intent into the tenant's
   leads record, confirms capture to the visitor, and skips invoking the
   agent's broader reasoning loop.
3. **Given** an obvious spam message ("buy cheap watches at ..."),
   **When** it arrives, **Then** the system drops it silently without
   consuming agent capacity and without producing a reply.
4. **Given** a visitor on Tenant A's site, **When** the visitor asks a
   question whose only published answer exists in Tenant B's CMS,
   **Then** the agent MUST NOT use Tenant B's content and MUST respond
   based only on Tenant A's content (or admit it doesn't know).
5. **Given** a visitor explicitly says "let me talk to a human",
   **When** that message is processed, **Then** the conversation is flagged
   for human escalation and the tenant_admin can see it in their dashboard.

---

### User Story 2 - Tenant admin manages CMS content that powers both the public site and the agent (Priority: P1)

A tenant_admin signs into their tenant dashboard, creates and edits CMS
content (pages such as FAQ, policies, product information). The same content
both renders on the tenant's public website surfaces and seeds the AI agent's
knowledge base. Content changes flow through to the agent within a bounded
time so the agent stays in sync.

**Why this priority**: The agent cannot deliver grounded answers without
content. CMS authoring is therefore on the critical path of US1 and must
ship in the same release.

**Independent Test**: A tenant_admin can create, edit, publish, and unpublish
a page from the dashboard; published content becomes retrievable by the agent
within a stated freshness window, and unpublished content stops being
retrievable.

**Acceptance Scenarios**:

1. **Given** a tenant_admin in their dashboard, **When** they publish a new
   page titled "Refund Policy" with a body, **Then** the page is rendered on
   the tenant's public site and becomes available to the agent's retrieval
   layer within the freshness window.
2. **Given** a published page, **When** the tenant_admin unpublishes it,
   **Then** the page is removed from the public site AND from the agent's
   retrievable content within the freshness window.
3. **Given** a tenant_admin in Tenant A, **When** they list, search, or open
   CMS pages, **Then** they see only Tenant A's pages and have no path to
   read, infer, or enumerate any other tenant's content.
4. **Given** a tenant_admin saves a new page as `draft`, **When** a visitor
   asks a question that would be answered by that page's body, **Then** the
   agent does not retrieve or use the draft content, and the page does not
   appear on the public site.

---

### User Story 3 - Tenant admin embeds the agent widget on their public site with one snippet (Priority: P2)

A tenant_admin copies a single embed snippet from their dashboard, pastes it
into their public website's HTML, and the agent widget appears for visitors.
The widget loads on the admin's permitted origins only; other origins are
rejected. The widget's theme and greeting reflect that tenant's configuration.

**Why this priority**: Without distribution, the agent has no visitors.
Embedding is small in surface area but blocks the visitor experience in US1
from reaching production.

**Independent Test**: A tenant_admin can copy a snippet, paste it into a
plain HTML test page hosted on a permitted origin, reload the page, and see
the widget appear with their tenant's branding and greeting. The same snippet
pasted on a non-permitted origin does not load.

**Acceptance Scenarios**:

1. **Given** a tenant with the embed snippet copied and pasted on a permitted
   origin, **When** a visitor loads that page, **Then** the widget appears
   themed and greeted per the tenant's configuration.
2. **Given** the embed snippet is pasted on an origin not in the tenant's
   allowed list, **When** a visitor loads that page, **Then** the widget
   refuses to operate and the server rejects chat requests from that origin
   with a clear failure.
3. **Given** a tenant_admin updates their widget theme or greeting,
   **When** a visitor next loads the widget, **Then** the change is reflected
   without the tenant_admin editing or re-pasting the snippet.

---

### User Story 4 - tenant_manager provisions a new tenant and invites its first admin (Priority: P2)

A platform-level tenant_manager creates a new tenant, configures its initial
boundary (name, plan, allowed origins seed), and sends an invitation to the
first tenant_admin email. The invited admin completes onboarding and takes
over configuration from there. Every tenant_manager action is recorded in an
audit log that the tenant_manager can review.

**Why this priority**: Without provisioning, no tenant exists. This story is
small but it gates the entire onboarding funnel.

**Independent Test**: A tenant_manager can create a tenant, send the
invitation, and the recipient can accept it and reach a working tenant_admin
dashboard for their tenant. Every step of the tenant_manager's flow appears
in the audit log.

**Acceptance Scenarios**:

1. **Given** a logged-in tenant_manager, **When** they create a tenant and
   invite an admin email, **Then** the new tenant exists in isolation, the
   invitation is delivered, and both actions appear in the audit log.
2. **Given** the invited email, **When** the recipient accepts and completes
   onboarding, **Then** they are signed in as tenant_admin of that tenant
   only and can begin configuration.
3. **Given** a tenant_manager, **When** they attempt to view any tenant's
   conversation transcripts or lead records, **Then** the system denies the
   access and records the attempt in the audit log.

---

### User Story 5 - Tenant admin reviews captured leads (Priority: P2)

A tenant_admin opens the Leads view in their dashboard, sees the leads the
agent has captured, can sort and filter them, and can export them. Leads are
strictly scoped to the tenant.

**Why this priority**: Lead capture is one of two side-effect actions the
agent performs; without a way to review captured leads the side effect has
no business value.

**Independent Test**: After a seeded set of conversations that include lead
captures, a tenant_admin can open the Leads view and see exactly the leads
captured for their tenant — no others.

**Acceptance Scenarios**:

1. **Given** N captured leads on Tenant A and M captured leads on Tenant B,
   **When** Tenant A's admin opens the Leads view, **Then** they see exactly
   N leads, none from Tenant B.
2. **Given** a captured lead, **When** the tenant_admin opens it,
   **Then** they see visitor name, contact, stated intent, timestamp, and the
   conversation it came from.
3. **Given** the Leads view, **When** the tenant_admin exports the list,
   **Then** the export contains only that tenant's leads in a standard
   format.

---

### User Story 6 - Tenant admin configures persona, guardrails, and theme (Priority: P3)

A tenant_admin opens settings and adjusts: the agent's persona (voice, tone),
greeting and theme, tenant-level guardrails (allowed/blocked topics, refusal
tone, which agent tools are enabled), and the list of allowed origins for
the widget. Platform-level safety rails (prompt injection, jailbreak,
cross-tenant refusal, PII redaction) are visible but cannot be weakened.

**Why this priority**: This sharpens the product but isn't required for an
end-to-end demo. Defaults exist and are usable as shipped.

**Independent Test**: A tenant_admin changes persona / greeting / theme /
allowed topics; the changes take effect on the next visitor turn or page
load without code deploys.

**Acceptance Scenarios**:

1. **Given** a tenant_admin changes the persona description from default to
   "warm and concise", **When** a visitor next interacts with the agent,
   **Then** responses reflect the new persona.
2. **Given** a tenant_admin blocks the topic "competitor pricing",
   **When** a visitor asks about a competitor's price, **Then** the agent
   refuses in the tenant's chosen refusal tone and does not consult the CMS
   for that topic.
3. **Given** a tenant_admin in any tenant, **When** they attempt to weaken,
   disable, or override a platform safety rail (e.g., turn off
   prompt-injection defense), **Then** the system refuses and the attempt is
   audit-logged.

---

### User Story 7 - tenant_manager fully erases a tenant on request (right to erasure) (Priority: P3)

A tenant_manager initiates erasure for a tenant. The system removes that
tenant's records from every store the platform uses — primary database rows,
vector embeddings, object storage blobs, and session memory — within a
stated SLA. The erasure operation is itself audit-logged, and post-erasure
no surface exposes the deleted tenant's data.

**Why this priority**: Required for compliance and trust, but not part of the
core demonstration value. Ships in v1.0 because it is a stated platform
requirement.

**Independent Test**: For a tenant with content, conversations, leads, and
an active session, a tenant_manager triggers erasure; an automated check
confirms zero residual data across all stores within the stated SLA, and
the erasure event appears in the audit log with operator, target tenant,
and timestamp.

**Acceptance Scenarios**:

1. **Given** a tenant with content, leads, and live sessions,
   **When** the tenant_manager confirms erasure, **Then** within the SLA all
   rows, embeddings, blobs, and sessions for that tenant are gone.
2. **Given** an erased tenant, **When** any system actor (widget loader,
   admin login, agent retrieval) attempts to use it, **Then** the system
   responds as if the tenant never existed.
3. **Given** any erasure operation, **When** it completes (or fails),
   **Then** the outcome is written to the audit log with operator identity,
   target tenant, start and end times, and stores that were purged.

---

### Edge Cases

- **Cross-tenant question on Tenant A**: a visitor asks about a topic where
  the only published answer exists on Tenant B — agent MUST decline rather
  than reveal anything from Tenant B.
- **Lead capture spam**: a single visitor session attempts to capture leads
  many times in seconds — the system rate-limits and the audit log records
  the attempts.
- **Token replay across tenants**: a chat token issued for Tenant A is sent
  to an endpoint with a body field claiming Tenant B — the server uses only
  the token's tenant identity and rejects (or ignores) the body claim.
- **Widget loaded in a hostile iframe**: an attacker tries to embed the
  widget in their own page to phish visitors — the server rejects the
  request based on origin / frame ancestor verification.
- **Prompt-injection in CMS content**: a tenant or contributor inserts
  hostile instructions into their own CMS page — platform rails still
  prevent the agent from leaking cross-tenant content or executing
  destructive tool calls beyond its scope.
- **PII pasted by a visitor**: a visitor pastes a real-looking API key or
  payment card into chat — it is redacted before any log, trace, memory
  store, or downstream call is written.
- **Erasure during active session**: a tenant is being erased while a
  visitor session is open — the visitor's next request fails clean (no
  partial data leak) and the audit log records the interrupted session.
- **Classifier ambiguity**: the router can't confidently classify a turn —
  the message is escalated to the agent rather than misrouted.
- **Bounded agent loop**: a hostile or pathological turn provokes runaway
  tool-calling — the loop terminates at the configured iteration / token cap
  and returns a graceful response.
- **Tenant_admin invitation expiry**: an invited admin never accepts —
  the invitation expires and the tenant_manager can re-invite.
- **Hosted LLM / embedding outage**: the upstream LLM or embedding API
  fails or times out — the system retries with bounded backoff inside the
  per-turn budget; on continued failure the visitor sees a clear
  "service temporarily unavailable" message with a contact path and the
  conversation is auto-flagged as escalated. No retrieval chunk is
  surfaced as a substitute answer.

## Requirements *(mandatory)*

### Functional Requirements

**Tenancy & Roles**

- **FR-001**: System MUST support exactly three roles: tenant_manager
  (platform-level), tenant_admin (per tenant), and visitor.
- **FR-002**: tenant_manager MUST be able to create and erase tenants and
  read platform-aggregate cost / usage; tenant_manager MUST NOT be able to
  read any tenant's conversations, leads, or CMS content.
- **FR-003**: tenant_admin MUST be able to manage CMS content, view leads,
  configure persona / guardrails / theme / allowed origins, and copy the
  embed snippet — for their own tenant only.
- **FR-004**: Every tenant_manager action MUST be written to a tamper-evident
  audit log, viewable by tenant_managers and not viewable by tenant_admins.
- **FR-005**: tenant_manager MUST be able to invite a first tenant_admin by
  email; tenant_admin MUST be able to invite additional admins to their own
  tenant.

**Tenant Isolation**

- **FR-006**: Every persistent record MUST carry a `tenant_id` and the
  system MUST enforce isolation at the database, application, and retrieval
  layers — no single layer is the only line of defense.
- **FR-007**: The `tenant_id` for any inbound request MUST be derived from
  the verified authentication token (widget JWT or service credential) ONLY,
  never from request body, query string, or client-supplied header.
- **FR-008**: Any request whose token-derived tenant disagrees with a
  body-supplied tenant MUST be rejected and logged.

**Agent & Router**

- **FR-009**: Inbound visitor messages MUST pass through a classifier-driven
  router before reaching the AI agent.
- **FR-010**: The router MUST handle these cases without invoking the agent:
  drop spam silently; for clear FAQ intent, retrieve and answer from tenant
  content; for clear contact / sales intent, capture a lead; for explicit
  escalation requests, flag the conversation.
- **FR-011**: Ambiguous or multi-step turns MUST be passed to the agent.
- **FR-012**: The agent MUST be a tool-calling assistant with exactly three
  tools: `rag_search` (retrieve tenant content and answer),
  `capture_lead` (write a lead — a real side effect), and
  `escalate` (flag conversation for a human).
- **FR-013**: The agent loop MUST be bounded — tool-call iterations and
  tokens per turn MUST be capped at configured limits, after which the loop
  terminates with a graceful response.
- **FR-014**: `capture_lead` MUST be schema-validated, rate-limited per
  visitor / session, and scoped to the token's tenant. A `capture_lead`
  attempt targeting any other tenant MUST be rejected.
- **FR-014a**: When a hosted dependency (LLM or embedding API) fails or
  exceeds the per-turn time budget, the system MUST: (a) perform a bounded
  retry with exponential backoff inside the budget, (b) if still failing,
  return a clear "service temporarily unavailable" message to the visitor
  with a contact path, (c) auto-flag the conversation as escalated for
  tenant_admin follow-up, and (d) NEVER fabricate an answer or return
  retrieval chunks as if they were a synthesized response.

**Content & Retrieval**

- **FR-015**: tenant_admin MUST be able to create, edit, publish, and
  unpublish CMS content. Each CMS page has exactly one of three states at
  any time: `draft` (saved, invisible to the public site and the agent),
  `published` (visible to the public site AND retrievable by the agent),
  or `unpublished` (archived, invisible to both, recoverable to `draft`
  or `published`). Only `published` content powers the public site and
  the agent's knowledge base. Scheduled publishing is out of scope for
  v1.0.
- **FR-016**: Content MUST be ingested into the agent's retrieval layer
  (chunked, embedded) such that published changes are retrievable within a
  stated freshness window (default: ≤ 5 minutes).
- **FR-017**: Retrieval MUST filter by `tenant_id` at query time and MUST
  NOT rely on post-filtering of returned results.
- **FR-018**: The chunking strategy used in retrieval MUST be a deliberate
  (non-naive) choice justified by a number on a documented golden set.
- **FR-019**: At least one retrieval-quality improvement (e.g. reranking,
  query rewriting, or metadata filtering) MUST be in production and
  justified by a number on the golden set.

**Classifier**

- **FR-020**: A real classifier MUST drive the router. It MUST be trained
  offline (notebook / training pipeline), not inside any service container.
- **FR-021**: Three approaches MUST be compared on a held-out test set —
  a classical ML baseline, a small deep-learning model exported for lean
  serving, and a zero-shot LLM baseline — on macro-F1, per-class F1,
  latency, and cost.
- **FR-022**: The chosen approach MUST be documented in a model card that
  records task, training data source and content hash, all three comparison
  results, deployment choice with rationale, and the deployed artifact's
  hash.
- **FR-023**: The classifier-serving component MUST refuse to start if the
  loaded artifact's hash does not match the hash declared in the model card.

**Memory & Prompts**

- **FR-024**: Short-term conversation memory MUST be scoped per conversation
  and per tenant and MUST expire after a stated TTL with a documented
  rationale.
- **FR-025**: Prompts MUST be version-controlled in a dedicated prompts
  directory. Tenant persona MUST be injected at runtime from tenant
  configuration; persona MUST NOT be hardcoded into prompt files.

**Widget & Embedding**

- **FR-026**: The widget MUST be embeddable with a single script tag carrying
  a tenant-public widget identifier.
- **FR-027**: A loader script MUST inject the widget UI and exchange the
  public widget identifier plus the host page's origin for a short-lived,
  tenant-scoped, signed authentication token.
- **FR-028**: Every chat request from the widget MUST carry that token. The
  server MUST validate the token AND the request's origin on every request.
  Mismatched or disallowed origins MUST be rejected with a 403.
- **FR-029**: Each tenant MUST maintain a list of allowed origins; this list
  drives both CORS and the widget's frame-ancestor policy. Changes by a
  tenant_admin take effect on the next request.
- **FR-030**: Widget theme and greeting MUST come from tenant configuration
  at runtime; no per-tenant rebuild is required to change them.

**Guardrails**

- **FR-031**: The system MUST run two layers of guardrails:
  *platform rails* (prompt-injection defense, jailbreak defense, cross-tenant
  refusal, PII redaction) — locked, identical for all tenants, and
  unweakenable by any tenant; and *tenant rails* (allowed/blocked topics,
  refusal tone, persona, enabled tools) — configurable per tenant.
- **FR-032**: Any attempt by a tenant_admin to weaken or override a platform
  rail MUST be refused and audit-logged.
- **FR-033**: Platform rails MUST be exercised by automated tests; a
  regression MUST fail the build (see Quality Gates).

**Security & Compliance**

- **FR-034**: PII MUST be redacted before any data leaves the
  request-handling service to logs, traces, memory, or downstream calls.
- **FR-035**: An automated test MUST prove that a synthetic, recognizable
  fake credential (e.g. fake API key, fake card number) pasted into a chat
  never appears unredacted in logs, traces, memory, or any other artifact.
- **FR-036**: Service-to-service calls MUST authenticate with credentials
  retrieved from the platform's secret store. No service credential MUST be
  committed to source control or embedded in container images.
- **FR-037**: Erasure of a tenant MUST purge every record for that tenant
  across all stores (primary database, vector index, object storage,
  session memory) within a stated SLA (default: ≤ 1 hour) and MUST be
  audit-logged.
- **FR-037a**: The widget MUST display a one-line consent notice on first
  interaction in a visitor session, stating that the conversation is
  processed by an AI and that personal data the visitor shares (e.g. via
  lead capture) is handled by the tenant. The visitor MUST be able to
  acknowledge and proceed; declining ends the interaction.
- **FR-037b**: The platform's design MUST align with GDPR principles —
  lawful basis, right of access (covered by tenant_admin's data + lead
  export views), right of erasure (FR-037), data minimization, and
  PII redaction in logs / traces / memory (FR-034 / FR-035). No
  certification is claimed; `SECURITY.md` MUST document this posture
  explicitly.

**Quality Gates**

- **FR-038**: The CI pipeline MUST enforce four evaluation gates with
  thresholds committed to `eval_thresholds.yaml`: classifier macro-F1,
  agent tool-selection on a golden set, retrieval quality on a golden set,
  and a red-team set covering prompt injection and cross-tenant probes.
- **FR-039**: Any regression below the committed threshold on any gate MUST
  block the merge until the regression is resolved or the threshold is
  lowered with a recorded decision.
- **FR-040**: A stack smoke test MUST verify that the compose stack starts
  cleanly from a fresh clone on every push.

**Documentation**

- **FR-041**: The repository MUST carry these documents, kept current with
  the code: `DESIGN.md` (isolation strategy, scaling story, cost-per-tenant
  model, role model, erasure path), one `SPEC.md` per major component,
  `DECISIONS.md` (every architectural choice backed by a number from
  evaluation), `RUNBOOK.md`, `EVALS.md`, and `SECURITY.md`.

### Key Entities *(include if feature involves data)*

- **Tenant**: the isolated workspace for a business; carries name, plan,
  allowed origins, persona configuration, theme, and guardrail
  configuration.
- **User**: an identity bound to one or more tenants with a role
  (tenant_manager, tenant_admin). tenant_managers have no per-tenant
  binding.
- **Visitor**: an anonymous (or pseudonymous) user of a tenant's public
  site interacting via the widget. Identified by session token only.
- **Conversation**: a sequence of turns between a visitor and the agent /
  router; carries tenant_id, session, transcript references, and an
  escalation flag.
- **CMSPage / Content**: a unit of tenant content; carries title, body,
  tenant_id, and exactly one publication state at any time — `draft`,
  `published`, or `unpublished`. Only `published` pages render on the
  public site AND seed the agent's knowledge base. Transitions:
  `draft → published`, `published → unpublished`, `unpublished → draft`,
  `unpublished → published` are all permitted; `draft → unpublished` is
  not (an unsaved-and-discarded draft is simply deleted).
- **Chunk**: a chunked + embedded fragment of CMS content used for
  retrieval; carries tenant_id, source content reference, embedding
  vector, and metadata for filtering.
- **Lead**: a captured visitor contact + intent record; tenant-scoped.
- **Widget**: the embedded chat surface; identified by a public widget_id
  the host pastes into their page.
- **AllowedOrigin**: one entry in a tenant's permitted-origin list; gates
  widget loading, CORS, and frame-ancestor policy.
- **AuditEntry**: a record of a tenant_manager action (provisioning,
  erasure, access attempt) with actor, target, timestamp, outcome.
- **ModelCard**: the offline-recorded description of the deployed
  classifier — task, training data, comparison results, deployment choice,
  artifact hash.
- **GuardrailConfig**: per-tenant configuration of tenant-controllable
  rails (topics, refusal tone, persona, enabled tools). Platform rails are
  global and not represented per tenant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 — Time-to-first-answer**: a brand-new tenant can be provisioned,
  load seed content, embed the widget on a test page, and receive a
  grounded answer from the agent in under 30 minutes of hands-on work by
  someone who has not seen the platform before.
- **SC-002 — Grounded answer rate**: on the retrieval golden set, at least
  85% of in-scope questions receive an answer rated as supported by the
  tenant's content.
- **SC-003 — Tenant isolation**: in the cross-tenant red-team set, 100% of
  probes targeting other tenants are correctly refused or fail closed. Any
  failure is a release blocker.
- **SC-004 — Prompt-injection defense**: at least 95% of prompt-injection
  probes in the red-team set are correctly resisted, and the threshold is
  committed; the remaining cases produce safe-by-default behavior.
- **SC-005 — Classifier accuracy**: the deployed router classifier reaches
  the macro-F1 threshold committed in `eval_thresholds.yaml` on the
  held-out test set.
- **SC-006 — Visitor responsiveness**: in normal operation, 95% of visitor
  turns receive a first user-visible response in under 5 seconds.
- **SC-007 — Lead capture integrity**: 100% of captured leads are
  schema-valid, are stored on the correct tenant, and respect the
  per-visitor / per-session rate limit; zero leads land on the wrong
  tenant.
- **SC-008 — PII redaction**: a synthetic API-key probe pasted into chat
  is redacted in 100% of log, trace, memory, and downstream artifacts on
  every CI run.
- **SC-009 — Erasure completeness**: an erased tenant has zero residual
  records in any store within 1 hour of the erasure request, verified by
  an automated post-erasure audit.
- **SC-010 — Stack reproducibility**: a fresh clone of the repository,
  followed by the single documented start command, brings up the full
  stack and passes the smoke test on every CI run.
- **SC-011 — CMS freshness**: a published or unpublished CMS change is
  reflected in agent retrieval within 5 minutes.

## Assumptions

- **Identity & onboarding**: tenant_admin and tenant_manager sign in with
  email + password (with standard email verification and password reset).
  Single sign-on (SSO / OAuth2) is out of scope for v1.0.
- **Billing**: the tenant_manager cost / usage view is a *read-only
  aggregate* — no in-product payment, invoicing, or plan-change flow ships
  in v1.0. Billing integration is a future feature.
- **Escalation handoff destination**: an escalated conversation is surfaced
  to the tenant_admin in the dashboard as a flagged conversation. External
  ticket-system integration (e.g., email, Slack, Zendesk) is out of scope
  for v1.0.
- **CMS authoring surface**: content is authored as structured pages with a
  title and a body field. Rich-media editing, drafts/versioning, and
  scheduled publishing are out of scope for v1.0.
- **Conversation transcripts**: full transcripts are retained server-side
  for tenant_admins to review (subject to PII redaction). Short-term
  in-flight memory has a separate, shorter TTL.
- **Language**: English-only v1.0. Multi-language is a future feature.
- **Inference**: LLM completions and embeddings are provided by hosted
  APIs; no model weights are shipped inside service containers (consistent
  with the constitution).
- **Erasure SLA default**: ≤ 1 hour from confirmation to fully purged
  state.
- **Freshness default**: published CMS changes are retrievable by the
  agent within ≤ 5 minutes of publication.
- **Widget JWT lifetime default**: short-lived (on the order of minutes)
  with refresh / re-issuance handled by the loader.
- **Tenant_manager is platform-internal**: tenant_managers are platform
  staff, not customer-facing self-service. The provisioning UI need only
  serve a small operator group.
- **v1.0 scale envelope (PoC scale)**: the platform is sized for up to
  10 tenants, approximately 200 CMS pages per tenant, and up to 50
  concurrent visitors across the entire platform. Architecture choices
  (database, vector index, modelserver) are sized to fit a single VM /
  compose stack at this scale. Growth- and production-scale sizing
  (sharding, replicas, HA) is explicitly out of scope for v1.0.
- **Availability — best-effort, no formal SLA**: v1.0 runs as a single
  compose stack. Downtime is tolerated for restarts, upgrades, and
  recovery. Daily automated backups of Postgres, the vector index, and
  object storage MUST be in place; manual restore steps MUST be documented
  in `RUNBOOK.md`. HA (replicas, hot-standby, automated failover) is
  explicitly out of scope for v1.0.
- **Compliance posture — GDPR-aligned, no certification claimed**: the
  product is designed to GDPR principles (lawful basis, right of access,
  right of erasure, data minimization, PII redaction). SOC 2, ISO 27001,
  HIPAA, and CCPA-specific controls are out of scope for v1.0. The
  jurisdictional posture is documented in `SECURITY.md`.
