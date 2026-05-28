# Shared Foundation Handoff

## Done

- Owner A vertical slice is present: tenant entities, repositories, RLS-backed
  migrations, tenant context middleware, origin-check stub, manager routes,
  invitation acceptance, audit logging, and Vault client.
- Shared runtime foundation is present: Dockerfile, compose files, env example,
  Make targets, pgvector Postgres role bootstrap, eval thresholds, manager
  bootstrap CLI, and import-linter Clean Architecture contracts.
- Composition root remains in `backend/app/frameworks/api/deps.py` and wires
  Owner A adapters. B/C/D provider hooks are explicit `NotImplementedError`
  placeholders.

## Baseline CI Scaffold

`.github/workflows/ci.yml` now runs on pull requests to `main` and pushes to
`main`. It currently checks:

- Python 3.11 backend setup with `uv`.
- Backend dependency installation from `backend/pyproject.toml` with the `dev`
  extra.
- Backend lint:
  - `uv run --extra dev ruff check .`
  - `uv run --extra dev lint-imports`
- Backend unit and contract tests:
  - `uv run --extra dev pytest tests/unit tests/contract`
- Root compose config validity:
  - `docker compose -f docker-compose.yml -f docker-compose.dev.yml config`
  - Falls back to `docker-compose` when the Docker Compose plugin is not
    available.

No secrets, deployment credentials, eval gates, image-size gates, or frontend /
sidecar build checks are configured in this baseline.

## Blocking Matrix Status

| Consumer | Needs from A | Task | Status |
| --- | --- | --- | --- |
| B / C / D | TenantContextMiddleware | T033 | done |
| B / D | TenantRepository and origin scoping | T111 | done |
| B / C | Vault client | T038 | done |
| B | tenant/user/audit/vault protocols | T019-T021, T032 | done |
| D | OriginCheck middleware stub | T034 | done |

## Still Owned Elsewhere

- Structured logging is T040 and remains pending Owner C/shared work.
- PII redaction is T035 and remains pending Owner C work.
- Tracing is T041 and remains pending Owner C work.
- Token signing is T049 and remains pending Owner D work.
- Modelserver, guardrails, admin, and widget containers are placeholders only.
- Owner D still owns expanding CI to full eval gates, stack smoke tests,
  modelserver/guardrails/widget/admin build checks, deployment workflows, and
  production secret wiring once those surfaces exist.

Do not add `backend/app/core/`. Shared settings stay in
`backend/app/frameworks/config.py`; logging/redaction/security work belongs in
the framework-layer files named by the Speckit tasks.

## Day-1 Owner Checklist

Owner B publishes its protocol interfaces and fakes for conversation, chunks,
leads, LLM, embeddings, and sessions before building story logic.

Owner C publishes classifier and guardrails protocols/adapters, plus
redaction/logging/tracing surfaces.

Owner D publishes token signing, object storage, CI, widget, and admin scaffolds.
