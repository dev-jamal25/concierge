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
- T129 complete (2026-05-29): `EraseTenantUseCase` now drives the full
  four-store cascade in a fixed order — Postgres + pgvector (via
  `TenantRepository.delete` cascade), Redis sessions
  (`SessionStore.delete_by_tenant`), and MinIO objects under the tenant prefix
  (`ObjectStorage.delete_prefix(tenant_id, "")`, which composes with the
  adapter's existing `tenant-{tenant_id}/` prefixing). The `tenant_erase_start`
  audit entry is written before any destructive work. The
  `tenant_erase_complete` audit entry now carries
  `details.stores_purged = ["pg", "vector", "redis", "minio"]` and a measured
  `details.duration_ms` (purge work only, excluding the start-audit write).
  `tests/integration/test_erasure_path.py` covers all four stores plus
  cross-tenant isolation for both Redis and MinIO.

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

## Remaining Owner A Follow-ups

T129 logic is fully wired across Postgres/pgvector, Redis, and MinIO. The
remaining items are factual and tracked as separate work:

- 1-hour erasure SLA load test (T129 SLA bullet) is not yet implemented as an
  automated assertion — the use case measures and audit-logs `duration_ms`, but
  there is no large-scale fixture that exercises the SLA budget. Track this as
  a follow-up ticket; do not retroactively reopen T129 for it.
- The MinIO adapter's underlying client wiring is owned by Owner D
  (`backend/app/adapters/storage/minio_object_storage.py`). Owner A's erasure
  path uses the `ObjectStorage` protocol and is unaffected by adapter-level
  follow-ups.

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
