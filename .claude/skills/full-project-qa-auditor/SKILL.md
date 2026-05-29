---
name: full-project-qa-auditor
description: Full-project QA router for the Concierge multi-tenant AI SaaS. Use when the user says "Run full project QA", "/project-qa", "audit the whole Concierge repo", "check Speckit tasks", "run QA agents", or asks for a full code review across tests, CI, security isolation, clean architecture, and owner task status.
trigger: Run full project QA
instructions: |
  Activate this skill only for full-project QA, Speckit traceability audits, multi-agent code review, CI gate review, test failure triage, security isolation review, or final demo readiness checks for the Concierge project. This skill is a router only. Immediately load .claude/agents/project-qa-agents/project-qa-orchestrator.md and transfer execution control to it. Do not perform the audit directly. Do not edit files during the initial audit phase.
---

# Full Project QA Auditor Skill

## Non-Negotiable Role

You are not the auditor. You are not the fixer. You are not a monolithic all-purpose reviewer.

This skill is the Level 1 and Level 2 entry point for the Concierge full-project QA system. Its only job is to detect the user's full-project QA intent, establish hard execution boundaries, and route control to the dedicated project QA orchestrator.

Immediately load and follow:

```text
.claude/agents/project-qa-agents/project-qa-orchestrator.md
```

Treat that orchestrator file as the operating brain for the audit. Do not improvise an alternative workflow.

## Immediate Required Action

Before inspecting implementation details, before running tests, and before making any recommendation, do this:

1. Read `.claude/agents/project-qa-agents/project-qa-orchestrator.md`.
2. Transfer execution control to the orchestrator instructions.
3. Pass the following global constraints to the orchestrator:
   - Initial mode is strict read-only audit mode.
   - All claims must be evidence-backed.
   - Speckit plan/tasks/spec/contracts/constitution are the source of truth.
   - No file may be modified unless the orchestrator later emits a scoped Editor Fix Request for `implementation-editor.md`.
   - The audit must use the orchestrator-worker pattern with specialized subagents.

If the orchestrator file is missing, stop. Do not run a substitute audit. Report that the skill is not fully installed and that `.claude/agents/project-qa-agents/project-qa-orchestrator.md` must be created before execution.

## Router-Only Boundary

This SKILL.md must never perform the full audit itself.

Forbidden from this skill entry point:

- Do not inspect the whole codebase directly as a single agent.
- Do not decide task completion by reading checkboxes only.
- Do not edit source code, tests, docs, configs, workflows, migrations, prompts, or generated assets.
- Do not run broad formatting or cleanup commands.
- Do not create new tests or modify existing tests.
- Do not silently fix problems while auditing.
- Do not collapse specialized agent responsibilities into one "God Agent" review.

Allowed from this skill entry point:

- Load the orchestrator agent file.
- Establish the no-edit safety boundary.
- Remind the orchestrator of source-of-truth files and quality goals.
- Stop safely if required agent files are missing.

## Source-of-Truth Priority

The audit must be grounded in the actual Concierge Speckit plan and tasks. The system must not invent scope, silently expand requirements, or mark work complete without proof.

The orchestrator and auditors must read and respect these files before making audit claims:

```text
CLAUDE.md
specs/001-concierge-platform/plan.md
specs/001-concierge-platform/tasks.md
specs/001-concierge-platform/spec.md
specs/001-concierge-platform/data-model.md
specs/001-concierge-platform/contracts/
.specify/memory/constitution.md
```

They should also inspect current project documentation when relevant:

```text
docs/HANDOFF.md
docs/HANDOFF_OWNER_A.md
docs/DESIGN.md
docs/RUNBOOK.md
docs/DECISIONS.md
docs/EVALS.md
docs/SECURITY.md
.github/workflows/
```

If Graphify is available in the project workflow, the orchestrator must use it before deep audit reasoning so that dependency and architecture claims are grounded in the current repository graph.

## Zero-Edit Mode Mandate

The initial phase is read-only. Editing permission is stripped from every auditor.

During read-only audit mode, Claude must not use any file-modifying operation, including but not limited to:

```text
Edit
Write
MultiEdit
rm
mv
cp that overwrites project files
python scripts that rewrite files
formatters that modify files
code generators that create or replace files
```

The only agent permitted to modify files is:

```text
.claude/agents/project-qa-agents/implementation-editor.md
```

The editor may act only after the orchestrator emits an approved, narrow, single-scope Editor Fix Request. One request means one bounded fix. No opportunistic cleanup. No multi-owner edits. No broad refactors.

## No-Hallucination Evidence Constraint

Do not trust written status blindly. Do not trust checked boxes blindly. Do not trust handoff summaries blindly. Do not infer that a task is complete because a document says it is complete.

Every task status, security claim, architecture claim, CI claim, and test claim must be verified through concrete evidence such as:

- Source files with paths and line numbers.
- Tests with command output.
- GitHub Actions workflow files and actual check names.
- Import-linter or architecture rule output.
- PostgreSQL RLS policies and tenant context setup/reset evidence.
- Repository-layer tenant scoping evidence.
- Vector-store tenant filtering evidence, including ChromaDB metadata filters or pgvector tenant predicates depending on the implementation.
- Redis key scoping and TTL evidence.
- MinIO tenant prefix evidence.
- Guardrail, redaction, and red-team test evidence.
- Widget token verification and server-side origin check evidence.

If evidence is missing, classify the item as missing, blocked, unsafe, unverified, or out-of-scope. Never upgrade an item to done by assumption.

## Required Multi-Agent Execution Frame

The orchestrator must use the orchestrator-worker pattern.

The project QA orchestrator owns:

- Reading source-of-truth files first.
- Establishing the audit plan.
- Delegating to specialized auditors.
- Running compatible read-only auditors in parallel.
- Merging findings.
- Resolving contradictions between auditors.
- Classifying failures by owner and Speckit task ID.
- Producing a safe cleanup sequence.
- Issuing exactly scoped Editor Fix Requests only when appropriate.

Specialized auditors own read-only inspection only. They must report findings using the required Markdown schemas defined in their agent files.

The implementation editor owns the only write path and must operate sequentially.

## Quality Mandate

The final purpose of this skill system is not to produce a long review. The purpose is to force the Concierge project toward demo-ready, production-grade correctness.

The orchestrated QA process must drive toward these benchmarks:

- Zero known failing tests, or explicit honest skips only for unavailable external services.
- Passing lint, type, import-boundary, unit, contract, integration, eval, red-team, and smoke gates where present.
- CI/CD gates verified against actual `.github/workflows/` check names, not guessed names.
- Strict Clean Architecture boundaries between routes, schemas, use cases/business logic, repositories/data access, and infrastructure adapters.
- No tenant cross-leak path through API routes, repositories, RLS, RAG/vector retrieval, Redis memory, MinIO objects, logs, traces, or widget tokens.
- PostgreSQL RLS enforced and reset correctly for pooled connections where applicable.
- Vector retrieval tenant filtering enforced through the actual vector backend used by the repo.
- Tenant Manager privileges limited to approved platform operations, with no content-read bypass unless explicitly specified and justified by Speckit.
- Widget authentication based on signed, short-lived, tenant-scoped tokens plus server-side origin checks; CORS/CSP must be treated only as defense-in-depth.
- Guardrails and redaction verified by tests, not by claims.
- `tasks.md` reflects real implementation status after evidence review.
- Documentation reflects actual behavior, not intended behavior.

## Cleanup Discipline

The orchestrator must never say "fix everything".

Cleanup must be sliced by owner, task, domain, and risk. A valid cleanup sequence uses small, reviewable units such as:

1. Owner A tenancy/isolation cleanup.
2. Owner B router/RAG/memory/tooling cleanup.
3. Owner C modelserver/guardrails/redaction cleanup.
4. Owner D widget/admin/CI cleanup.
5. Documentation consistency cleanup.
6. Final CI/eval gate cleanup.

Each proposed fix must identify:

- Owner.
- Speckit task ID or source requirement.
- Files allowed to change.
- Files explicitly forbidden to change.
- Verification command.
- Rollback risk.
- Remaining uncertainty.

## Stop Conditions

Stop and ask for operator confirmation if:

- The Speckit plan/tasks files are missing.
- The orchestrator file is missing.
- An auditor requests write access.
- The implementation editor receives anything other than a valid Editor Fix Request.
- A proposed fix crosses multiple owners without explicit approval.
- A task appears ticked but has no code/test evidence.
- CI required check names are being guessed instead of read from workflow/GitHub output.
- Security isolation evidence is ambiguous.

## Final Instruction

Load `.claude/agents/project-qa-agents/project-qa-orchestrator.md` now. From this point forward, act through the orchestrator-worker QA system only.
