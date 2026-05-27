---
name: tenant-isolation-auditor
description: Trigger/delegator skill for Owner A tenant isolation, RLS, tenant context, provisioning, invitations, audit, and erasure-boundary checks.
version: 1.0.0
user-invocable: true
disable-model-invocation: false
context: Use this skill only for Owner A tenancy/isolation work. Delegate all auditing, planning, and implementation decisions exclusively to .claude/agents/owner-a-agents/owner-a-orchestrator.md.
paths:
  - backend/app/entities/
  - backend/app/use_cases/
  - backend/app/adapters/repositories/
  - backend/app/frameworks/api/
  - backend/app/frameworks/db/
  - backend/tests/
  - specs/001-concierge-platform/
triggers:
  - tenant isolation
  - RLS
  - tenant_id
  - provisioning
  - invitation
  - audit log
  - tenant manager
  - erasure
---

## When to use

Use this skill for Owner A tenant-isolation work only.

Trigger on prompts or file changes involving:
- Tenant models, tenant lifecycle, tenant status, or tenant metadata.
- PostgreSQL RLS, `tenant_id`, `app.tenant_id`, `SET LOCAL`, migrations, grants, roles, or pgvector tenant filtering.
- Tenant context middleware, auth/session-derived tenant context, or `tenant_id` spoofing prevention.
- Repository scoping, tenant-bound `SELECT` / `UPDATE` / `DELETE`, or unsafe `get_by_id` access.
- Tenant Manager permissions, provisioning, first-admin invitations, audit log writes, or erasure boundaries.
- Tests for RLS isolation, cross-tenant access, manager limits, provisioning, invitations, audit logs, or tenant spoofing.

Do not use this skill for general backend cleanup, unrelated refactors, or Owner B/C/D feature work.

## Inputs to inspect

Pass these inputs to the orchestrator. Do not perform the audit directly from this skill.

Required project context:
- `CLAUDE.md`
- `specs/001-concierge-platform/plan.md`
- `specs/001-concierge-platform/tasks.md`
- `specs/001-concierge-platform/spec.md`
- `.specify/memory/constitution.md`
- `specs/001-concierge-platform/data-model.md`
- `specs/001-concierge-platform/contracts/`
- `graphify-out/graph.json` when present

Owner A implementation areas:
- `backend/app/entities/`
- `backend/app/use_cases/`
- `backend/app/use_cases/protocols/`
- `backend/app/adapters/repositories/`
- `backend/app/frameworks/api/deps.py`
- `backend/app/frameworks/api/middleware/`
- `backend/app/frameworks/api/routes/auth.py`
- `backend/app/frameworks/api/routes/manager.py`
- `backend/app/frameworks/db/`
- `backend/app/frameworks/db/alembic/versions/`
- `backend/tests/unit/`
- `backend/tests/contract/`
- `backend/tests/integration/`

## Checklist

The orchestrator must verify these Owner A boundaries:

- Every tenant-owned table has `tenant_id`.
- Every tenant-owned table has RLS enabled and a tenant-scoped policy.
- Tenant context is derived only from verified token/session state.
- No endpoint trusts `tenant_id` from body, query, path, or unverified headers for authorization.
- DB context uses transaction-local `SET LOCAL app.tenant_id`.
- Connection-pool leakage is prevented by transaction boundaries or explicit teardown.
- Repositories filter tenant-bound reads, writes, updates, and deletes by tenant scope.
- `get_by_id`, `list`, `update`, and `delete` methods are not IDOR-prone.
- Tenant Manager can provision, suspend, erase, and read metadata/aggregate usage only.
- Tenant Manager cannot read CMS content, chunks, conversations, messages, leads, or visitor payloads.
- Provisioning creates tenant state, first-admin invitation, allowed-origin/widget seed where Owner A owns it, and `tenant_create` audit log.
- Invitation acceptance binds the tenant admin without platform-operator impersonation.
- Erasure locks tenant reads immediately, uses Postgres cascade for Owner A data, and leaves B/D stores as protocol hooks.
- Tests cover RLS isolation, tenant spoofing, manager content denial, provisioning, invitation acceptance, audit logs, and erasure boundaries.
- Any B/C/D requirement is replaced with a TODO, protocol hook, or `NotImplementedError`.

## Commands to run

First and only execution step:

```text
Use `.claude/agents/owner-a-agents/owner-a-orchestrator.md` to handle this request.
Delegate all auditing, planning, fan-out, fan-in, and implementation decisions to the orchestrator.
```

Mandatory delegation payload:

```text
Task type: tenant-isolation-auditor
Scope: Owner A only
In scope: tenancy, RLS, tenant context, repository scoping, Tenant Manager permissions, provisioning, invitations, audit log, tenant_id spoofing tests, erasure boundaries
Out of scope: RAG, agent tools, modelserver, guardrails sidecar, widget UI, admin Streamlit, full eval gates
Rule: Do not audit or implement directly from this skill. The orchestrator must fan out to Owner A agents and may hand off edits only to owner-a-implementation-editor.md.
```

Do not call individual auditors directly from this skill.
Do not edit files from this skill.
Do not bypass the orchestrator.

## Output format

Return the orchestrator’s final synthesis in this structure:

```text
Tenant Isolation Audit Result: PASS | FAIL | BLOCKED

Scope:
- In-scope Owner A items:
- Out-of-scope items detected:
- Required TODO / NotImplementedError hooks:

Evidence:
- Speckit references checked:
- Files inspected:
- Graphify queries used:

Findings:
- RLS:
- Tenant context:
- Repository scoping:
- Manager permissions:
- Provisioning/invitations:
- Audit logs:
- Erasure boundaries:
- Tests:

Required action:
- No change required | Editor may apply scoped fix | Blocked until owner/domain dependency exists

Verification:
- Commands to run:
- Tests expected:
- CI impact:
```

Keep the final report concise. State hard failures plainly.

## Red flags

Hard fail immediately if any of these appear:

- Tenant-owned table without `tenant_id`.
- Tenant-owned table without RLS.
- RLS policy not tied to `current_setting('app.tenant_id')`.
- `SET SESSION` or persistent tenant context in pooled connections.
- Missing transaction boundary or teardown for tenant context.
- Endpoint authorizes from body/query/path/header `tenant_id`.
- Repository query fetches by ID without tenant scope.
- Manager role can read CMS, chunks, conversations, messages, leads, or visitor payloads.
- Provisioning omits first-admin invitation or `tenant_create` audit log.
- Tenant erasure permits reads after `tenant_erase_start`.
- Owner A directly implements Redis, MinIO, RAG, modelserver, guardrails, widget UI, admin UI, or eval-gate business logic.
- Security-sensitive code changed without matching negative tests.
- Code is added without tests.
- Broad `backend/app/core/` or architecture refactor appears in an Owner A task.

## What not to touch

Ignore, block, or convert to TODO/protocol hook:

- RAG pipelines, chunking, retrieval, reranking, generation, or golden triples.
- Agent tools, router logic, tool-calling loops, prompts, LangGraph/CrewAI/AutoGen orchestration.
- Modelserver, classifier training, ONNX/joblib serving, model cards, model evals.
- Guardrails sidecar, NeMo/Guardrails.ai integration, PII redaction implementation, tracing implementation.
- Widget UI, loader script, signed widget-token implementation, widget bundle, frontend chat surface.
- Admin Streamlit UI, admin pages, embed snippet UI.
- Full CI eval gates for classifier, RAG, agent tool selection, red-team, or redaction.
- Owner B/C/D adapters or business logic.
- Global architecture refactors outside the approved Owner A scope.
