# Demo Blocker Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two demo blockers so Friday's end-to-end demo runs clean from `docker compose down -v`.

**Architecture:** Blocker 1 is a missing DB grant — a forward-only Alembic migration adds `INSERT, DELETE` to `concierge_app` on `allowed_origins` (RLS WITH CHECK policy already exists). Blocker 2 is a double-fault in the LLM-failure path — guard `update_escalation` against a None row and wrap the escalation call in `chat.py` so the intended 503 always fires.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy asyncio, Alembic, pytest-asyncio, pytest TestClient

---

## File Map

| File | Change |
|---|---|
| `backend/app/frameworks/db/alembic/versions/005_grant_app_origins_write.py` | **Create** — migration that adds INSERT/DELETE grant |
| `backend/app/adapters/repositories/conversation_repository.py` | **Modify** — None guard in `update_escalation` |
| `backend/app/frameworks/api/routes/chat.py` | **Modify** — wrap escalation call in try/except |
| `backend/tests/unit/adapters/test_conversation_repository.py` | **Create** — unit test for None guard |
| `backend/tests/contract/test_chat_503.py` | **Create** — contract test for 503 on agent failure |

---

## Task 1: Migration — grant INSERT, DELETE on allowed_origins to concierge_app

**Files:**
- Create: `backend/app/frameworks/db/alembic/versions/005_grant_app_origins_write.py`

**Context:** Migration 003 only granted `SELECT` to `concierge_app` on `allowed_origins`. The RLS `WITH CHECK` policy (`app_allowed_origins_tenant`) already restricts inserts to the calling tenant, so the grant is safe to add. `UPDATE` is NOT needed (no update route exists for origins).

- [ ] **Step 1: Write the migration**

```python
"""grant concierge_app INSERT and DELETE on allowed_origins

Revision ID: 005
Revises: 004
Create Date: 2026-05-30

Migration 003 granted only SELECT to concierge_app on allowed_origins.
The admin route for POST /admin/origins and DELETE /admin/origins/{id}
both run as concierge_app and need INSERT and DELETE respectively.
The RLS WITH CHECK policy already tenant-scopes all writes.
"""

from __future__ import annotations

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT INSERT, DELETE ON allowed_origins TO concierge_app;")


def downgrade() -> None:
    op.execute("REVOKE INSERT, DELETE ON allowed_origins FROM concierge_app;")
```

- [ ] **Step 2: Run the migration**

```bash
cd backend
uv run alembic -c app/frameworks/db/alembic.ini upgrade head
```

Expected output ends with: `Running upgrade 004 -> 005, grant concierge_app INSERT and DELETE on allowed_origins`

- [ ] **Step 3: Verify the grant directly**

```bash
docker compose exec postgres psql -U concierge -d concierge -c "\dp allowed_origins"
```

Expected: `concierge_app` column shows `arwd` (at minimum `arid` — `a` = INSERT, `r` = SELECT, `d` = DELETE).

---

## Task 2: Fix update_escalation — guard against None row

**Files:**
- Modify: `backend/app/adapters/repositories/conversation_repository.py` (lines 63–79)

**Context:** After the `UPDATE` statement, `session.get(ConversationModel, conversation_id)` can return `None` when RLS or a bad session state blocks the lookup. Calling `_to_entity(None)` crashes with `AttributeError`. Raise `LookupError` instead so callers handle it deliberately.

- [ ] **Step 1: Write the failing test first** (create `backend/tests/unit/adapters/test_conversation_repository.py`)

```python
"""Unit tests for PostgresConversationRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.adapters.repositories.conversation_repository import PostgresConversationRepository


@pytest.mark.asyncio
async def test_update_escalation_raises_when_row_not_found() -> None:
    """update_escalation raises LookupError (not AttributeError) if the row
    cannot be fetched after the UPDATE — e.g. session expired or RLS blocked."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=None)  # simulate missing row

    repo = PostgresConversationRepository(session)
    with pytest.raises(LookupError, match=str(uuid4())[:8] or ""):
        await repo.update_escalation(
            conversation_id=uuid4(),
            tenant_id=uuid4(),
            reason="llm_unavailable",
        )
```

Run to confirm it fails:
```bash
cd backend
uv run --extra dev pytest tests/unit/adapters/test_conversation_repository.py -v
```

Expected: `FAILED ... AttributeError: 'NoneType' object has no attribute 'id'`

- [ ] **Step 2: Apply the fix**

In `backend/app/adapters/repositories/conversation_repository.py`, replace lines 78–79:

```python
        row = await self._s.get(ConversationModel, conversation_id)
        return _to_entity(row)  # type: ignore[arg-type]
```

With:

```python
        row = await self._s.get(ConversationModel, conversation_id)
        if row is None:
            raise LookupError(
                f"Conversation {conversation_id} not found after escalation update"
            )
        return _to_entity(row)
```

- [ ] **Step 3: Run the test to confirm it passes**

```bash
cd backend
uv run --extra dev pytest tests/unit/adapters/test_conversation_repository.py -v
```

Expected: `PASSED`

---

## Task 3: Fix chat.py — make escalation call best-effort

**Files:**
- Modify: `backend/app/frameworks/api/routes/chat.py` (the `except Exception` block inside `chat()`)

**Context:** When `agent_turn_uc.execute()` raises (e.g. no LLM key), the `except Exception` handler calls `escalate_uc.execute()` which can itself raise (Task 2's LookupError, or an expired-session error). That second raise means the `HTTPException(503)` line is never reached and the caller gets an unhandled 500.

The fix wraps escalation in a nested try/except. Escalation is always best-effort in the failure path.

- [ ] **Step 1: Apply the fix**

In `backend/app/frameworks/api/routes/chat.py`, replace the `except Exception` block (around line 321):

```python
    except Exception:
        await escalate_uc.execute(
            conversation_id=body.conversation_id,
            tenant_id=tenant_id,
            reason="llm_unavailable",
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Service temporarily unavailable. Please try again shortly.",
                "escalated": True,
            },
        )
```

With:

```python
    except Exception:
        try:
            await escalate_uc.execute(
                conversation_id=body.conversation_id,
                tenant_id=tenant_id,
                reason="llm_unavailable",
            )
        except Exception:
            pass  # best-effort — don't mask the 503
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Service temporarily unavailable. Please try again shortly.",
                "escalated": True,
            },
        )
```

---

## Task 4: Contract test — chat handler returns 503 when agent fails

**Files:**
- Create: `backend/tests/contract/test_chat_503.py`

**Context:** Verify the full HTTP path: agent raises → escalation raises (via LookupError in repo) → caller still gets 503, not 500. Uses `TestClient` with all deps overridden so no real DB or LLM is needed.

- [ ] **Step 1: Write the test**

```python
"""Contract test: /chat returns 503 (not 500) when the agent path fails.

Overrides all DB/LLM/session-store deps with fakes so no external
services are needed. Verifies the escalation error handler in chat.py
correctly absorbs a secondary failure and returns the intended 503.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token-chat-503")

from app.frameworks.api.deps import (  # noqa: E402
    db_session,
    get_app_settings,
    get_current_widget_context,
    get_session_store,
)
from app.frameworks.api.main import create_app  # noqa: E402


class _FailingSessionStore:
    async def store(self, key, value, ttl): pass
    async def retrieve(self, key): return None
    async def delete(self, key): pass
    async def delete_by_tenant(self, tenant_id): pass


class _FakeSession:
    """Minimal AsyncSession stand-in. execute() always succeeds; get() returns None."""

    async def execute(self, *a, **kw):
        from unittest.mock import MagicMock
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    async def get(self, model, pk):
        return None

    async def flush(self): pass
    async def refresh(self, obj): pass

    def add(self, obj): pass


@pytest.fixture
def client_503() -> TestClient:
    from app.frameworks.api.deps import WidgetTokenContext

    app = create_app()
    tenant_id = str(uuid4())
    widget_id = str(uuid4())

    async def fake_widget_context() -> WidgetTokenContext:
        return WidgetTokenContext(
            tenant_id=tenant_id,
            widget_id=widget_id,
            origin="http://localhost:3001",
        )

    async def fake_db_session() -> AsyncIterator:
        yield _FakeSession()

    from app.frameworks.config import Settings

    def fake_settings() -> Settings:
        return Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            manager_database_url="postgresql+asyncpg://x:x@localhost/x",
            migration_database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="",
            embedding_api_key="",
            service_token="test-token-chat-503",
        )

    async def fake_session_store():
        return _FailingSessionStore()

    app.dependency_overrides[get_current_widget_context] = fake_widget_context
    app.dependency_overrides[db_session] = fake_db_session
    app.dependency_overrides[get_app_settings] = fake_settings
    app.dependency_overrides[get_session_store] = fake_session_store

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_chat_agent_failure_returns_503_not_500(client_503: TestClient) -> None:
    """When the agent path fails (no LLM key) and escalation also fails
    (conversation not found in session), /chat must return 503, not 500."""
    resp = client_503.post(
        "/chat",
        headers={
            "Authorization": "Bearer fake-widget-token",
            "Origin": "http://localhost:3001",
        },
        json={
            "conversation_id": str(uuid4()),
            "message": "What are Helix Analytics private API secrets?",
        },
    )
    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("detail", {}).get("escalated") is True
```

- [ ] **Step 2: Run all unit + contract tests**

```bash
cd backend
uv run --extra dev pytest tests/unit tests/contract -v
```

Expected: all pass (including the new `test_conversation_repository` and `test_chat_503` tests).

---

## Task 5: Run full verification suite

- [ ] **Step 1: Lint**

```bash
cd backend
uv run --extra dev ruff check .
uv run --extra dev lint-imports
```

Expected: no errors.

- [ ] **Step 2: Run targeted integration tests** (requires compose stack)

```bash
cd backend
uv run --extra dev pytest tests/integration/test_admin_origins.py -v
uv run --extra dev pytest tests/integration/test_widget_token_origin.py -v
```

Expected: all pass — `test_add_origin_success`, `test_delete_origin_success`, and `test_delete_origin_cross_tenant_denied` all green.

- [ ] **Step 3: Clean-state smoke test**

```bash
# From repo root
docker compose down -v
docker compose up --build -d --wait
cd backend
uv run python -m app.frameworks.cli.seed_demo_tenants
uv run python -m app.frameworks.cli.seed_demo_users
uv run --extra dev pytest ../tests/smoke_test.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Verify POST /admin/origins returns 201**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@lumiere-coffee.example.com","password":"demo-admin-2025"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8000/admin/origins \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"origin":"http://localhost:4000"}'
```

Expected: `HTTP 201`.

---

## Remaining blockers (env-only, no code changes)

After these fixes the only remaining demo gaps are environment variables that must be set in `.env`:

| Variable | Effect if missing |
|---|---|
| `ANTHROPIC_API_KEY` | Agent/ambiguous chat route returns 503 (now clean, not 500) |
| `EMBEDDING_API_KEY` | CMS publish returns 500; `chunks` table stays empty; RAG ungrounded |
