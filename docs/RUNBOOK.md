# RUNBOOK (stub - Owner A + D, T056)

## Compose-Up

Copy `.env.example` to `.env`, then start the shared development services:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio vault api
```

The shared stack provides Postgres with pgvector, Redis, MinIO, Vault, and the
FastAPI backend. Owner C/D sidecars are intentionally left as documented
placeholders until those owners publish their adapters.

## Migrations

Run migrations from the repository root:

```sh
make migrate
```

The target runs Alembic from `backend/` with the table-owning
`MIGRATION_DATABASE_URL`.

## Postgres Roles

Compose initializes three principals:

- `concierge`: migration owner, created by the Postgres image.
- `concierge_app`: RLS-bound application role.
- `concierge_manager`: elevated manager role for tenants, users, invitations,
  allowed origins, widgets, and aggregate audit/usage surfaces.

`db/init/01-roles.sh` creates or updates the app and manager role passwords from
`CONCIERGE_APP_PASSWORD` and `CONCIERGE_MANAGER_PASSWORD`. Migrations still keep
the standalone fallback role creation and table grants.

## Vault Dev Mode

The dev compose override starts Vault with `VAULT_DEV_ROOT_TOKEN_ID`. The app uses
KV v2 at `secret/`; the widget signing key path is
`secret/jwt/widget/active`.

## Bootstrap Manager

Set `BOOTSTRAP_MANAGER_EMAIL` and `BOOTSTRAP_MANAGER_PASSWORD` in `.env`, then run:

```sh
make bootstrap-manager
```

The command is idempotent by email.

## Restore

Backup and restore procedures for Postgres, pgvector data, Redis, and MinIO are
still pending the Owner D operational pass.

## On-Call

Common alerts and remediation steps are still pending the Owner D operational
pass.
