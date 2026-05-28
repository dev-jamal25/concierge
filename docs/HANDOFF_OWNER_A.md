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
- T129 Redis half complete (2026-05-28): `EraseTenantUseCase` now injects and
  calls `SessionStore.delete_by_tenant(tenant_id)` after the Postgres cascade
  delete, via Owner B's published `SessionStore` protocol (T029/T191). The
  `tenant_erase_start` audit entry is written before any destructive work.
  `stores_purged` in the completion audit entry is now `["pg", "vector", "redis"]`.
  Three new tests cover: `delete_by_tenant` is called, cross-tenant sessions
  survive, and `tenant_erase_start` is recorded.

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

## Remaining Blockers (Owner A T129 — MinIO half)

T129 is **partially complete**. The Postgres + pgvector + Redis halves are done.
MinIO prefix purge remains blocked on Owner D:

| Blocker | Owner | File | Status |
| --- | --- | --- | --- |
| `ObjectStorage.delete_prefix` wiring | D | `backend/app/adapters/storage/minio_object_storage.py` | All methods raise `NotImplementedError` |

When Owner D delivers the real MinIO client:
1. Inject `ObjectStorage` into `EraseTenantUseCase` alongside `SessionStore`.
2. Call `await self._object_storage.delete_prefix(tenant_id, "")` after the Redis purge.
3. Append `"minio"` to `stores_purged` in the completion audit entry.
4. Remove the inline `TODO(owner-d, T031/T050)` comment in `erase_tenant.py`.

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
