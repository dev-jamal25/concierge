# RUNBOOK (stub — Owner A + D, T056)

To be populated (T161). Sections:

- **Compose-up** — bring up Postgres, Redis, MinIO, Vault, API, sidecars.
- **Migrations** — `alembic -c app/frameworks/db/alembic.ini upgrade head` (run from `backend/`,
  as the table-owning role).
- **Postgres roles** — migrations create `concierge_app` (RLS-bound) and `concierge_manager`
  (elevated reads on tenants + audit_entries + provisioning tables; no content-table access).
- **Vault dev-mode** — bootstrap with `VAULT_DEV_ROOT_TOKEN_ID`; KV v2 at `secret/`; widget signing
  key at `secret/jwt/widget/active`.
- **Restore** — backup/restore Postgres + pgvector + Redis + MinIO.
- **On-call** — common alerts and remediation.
