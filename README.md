# Concierge

Multi-tenant AI SaaS for embeddable, tenant-isolated concierge agents. Businesses
will be able to connect content, answer visitor questions, capture leads, and
escalate to humans. The wall between tenants is the core guarantee.

## Prerequisites

- Docker and Docker Compose
- Python 3.11
- `uv`
- GNU Make

## Local Runtime

Create a local environment file from the checked-in example:

```sh
cp .env.example .env
```

Then start the shared development stack:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio vault api
```

Apply migrations and bootstrap a manager account:

```sh
make migrate
make bootstrap-manager
```

The API exposes `GET /healthz` and `GET /readyz` on `http://localhost:8000`.

## Project Docs

- Quickstart: `specs/001-concierge-platform/quickstart.md`
- Implementation plan: `specs/001-concierge-platform/plan.md`
- Handoff notes: `docs/HANDOFF.md`
- Operations runbook: `docs/RUNBOOK.md`
