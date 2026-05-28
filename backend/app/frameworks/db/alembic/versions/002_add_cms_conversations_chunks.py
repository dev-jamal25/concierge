"""add cms_pages, conversations, messages, chunks, leads

Revision ID: 002
Revises: 001
Create Date: 2026-05-27

Owner B (T088). Creates the Agent/RAG tables with tenant_id RLS, pgvector
HNSW index on chunks.embedding, and B-tree indexes for query-time filtering.

down_revision is 001. Migration 003 (Owner A) also branches from 001.
A merge revision will reconcile the two heads when slices integrate.
"""

from __future__ import annotations

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- cms_pages ---
    op.execute(
        """
        CREATE TABLE cms_pages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL,
            state       TEXT NOT NULL DEFAULT 'draft'
                            CHECK (state IN ('draft','published','unpublished')),
            slug        TEXT NOT NULL,
            published_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, slug)
        );
        """
    )
    op.execute("CREATE INDEX ix_cms_pages_tenant_state ON cms_pages (tenant_id, state);")

    op.execute("ALTER TABLE cms_pages ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY cms_pages_tenant_isolation ON cms_pages
            FOR ALL TO concierge_app
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON cms_pages TO concierge_app;")

    # --- conversations ---
    op.execute(
        """
        CREATE TABLE conversations (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            widget_id        UUID NOT NULL REFERENCES widgets(id),
            visitor_session  TEXT NOT NULL,
            escalated_at     TIMESTAMPTZ,
            escalation_reason TEXT,
            started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_turn_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_conversations_tenant ON conversations (tenant_id, started_at);")

    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY conversations_tenant_isolation ON conversations
            FOR ALL TO concierge_app
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON conversations TO concierge_app;")

    # --- messages ---
    op.execute(
        """
        CREATE TABLE messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK (role IN ('visitor','agent','tool','system')),
            router_label    TEXT,
            content         TEXT NOT NULL,
            tool_calls      JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_messages_conversation ON messages (conversation_id, created_at);"
    )

    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY messages_tenant_isolation ON messages
            FOR ALL TO concierge_app
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON messages TO concierge_app;")

    # --- chunks (pgvector) ---
    op.execute(
        """
        CREATE TABLE chunks (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            cms_page_id  UUID NOT NULL REFERENCES cms_pages(id) ON DELETE CASCADE,
            chunk_index  INTEGER NOT NULL,
            content      TEXT NOT NULL,
            embedding    vector(1024) NOT NULL,
            metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (cms_page_id, chunk_index)
        );
        """
    )
    # B-tree for query-time tenant filter (planner applies BEFORE the ANN scan)
    op.execute("CREATE INDEX ix_chunks_tenant ON chunks (tenant_id);")
    # HNSW index for cosine ANN — applied after tenant filter reduces candidates
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    op.execute("ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY chunks_tenant_isolation ON chunks
            FOR ALL TO concierge_app
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON chunks TO concierge_app;")

    # --- leads ---
    op.execute(
        """
        CREATE TABLE leads (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL REFERENCES conversations(id),
            name            TEXT,
            contact         TEXT NOT NULL,
            intent          TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_leads_tenant_created ON leads (tenant_id, created_at DESC);"
    )

    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY leads_tenant_isolation ON leads
            FOR ALL TO concierge_app
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads TO concierge_app;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leads CASCADE;")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS messages CASCADE;")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE;")
    op.execute("DROP TABLE IF EXISTS cms_pages CASCADE;")
