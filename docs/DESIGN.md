# DESIGN (stub — Owner A, T054)

To be populated as Slice A completes (T154). Sections:

- **Isolation strategy** — RLS (`app.tenant_id` GUC) + repository-layer scoping + middleware.
- **Scaling story** — single compose stack for PoC; sharding paths deferred.
- **Cost-per-tenant model** — embeddings, LLM, storage per tenant at scale.
- **Role model** — `tenant_manager` (global, elevated reads on tenants + audit + usage aggregate only) /
  `tenant_admin` (per-tenant via `user_tenant_roles`) / `visitor` (session-only).
- **Erasure path** — cross-store purge (Postgres cascade, Redis, MinIO, pgvector) with ≤1h SLA.
