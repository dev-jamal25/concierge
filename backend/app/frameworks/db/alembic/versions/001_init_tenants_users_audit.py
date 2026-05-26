"""init tenants, users, user_tenant_roles, invitations, audit_entries

Revision ID: 001
Revises:
Create Date: 2026-05-26

Owner A (T018). Creates the identity/tenancy tables, installs extensions, sets up
the concierge_app (RLS-bound) and concierge_manager (elevated) roles, and applies
explicit, per-table RLS policies. `users.role` is created here (kept aligned with
the ORM model — not deferred to migration 003).
"""

from __future__ import annotations

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extensions ---
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    # --- Roles (idempotent) ---
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'concierge_app') THEN
                CREATE ROLE concierge_app LOGIN PASSWORD 'concierge_app';
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'concierge_manager') THEN
                CREATE ROLE concierge_manager LOGIN PASSWORD 'concierge_manager';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format("
        "'GRANT CONNECT ON DATABASE %I TO concierge_app, concierge_manager', "
        "current_database()); END $$;"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO concierge_app, concierge_manager;")

    # --- Tables ---
    op.execute(
        """
        CREATE TABLE tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'poc',
            persona_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            theme_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            guardrail_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_verified BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE user_tenant_roles (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, tenant_id)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_invitations_pending ON invitations (tenant_id, email) "
        "WHERE accepted_at IS NULL;"
    )
    op.execute(
        """
        CREATE TABLE audit_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_user_id UUID REFERENCES users(id),
            target_tenant_id UUID,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_target_tenant ON audit_entries (target_tenant_id, created_at DESC);"
    )
    op.execute("CREATE INDEX ix_audit_actor ON audit_entries (actor_user_id, created_at DESC);")

    # --- Privilege grants (RLS filters rows; grants gate table access) ---
    op.execute("GRANT SELECT, UPDATE ON tenants TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants TO concierge_manager;")
    op.execute("GRANT SELECT, UPDATE ON users TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users TO concierge_manager;")
    op.execute("GRANT SELECT, INSERT, DELETE ON user_tenant_roles TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_tenant_roles TO concierge_manager;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON invitations TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invitations TO concierge_manager;")
    # audit_entries: manager reads + appends; app has NO access. Append-only.
    op.execute("REVOKE UPDATE, DELETE ON audit_entries FROM PUBLIC;")
    op.execute("GRANT SELECT, INSERT ON audit_entries TO concierge_manager;")

    # --- Row-Level Security ---
    for tbl in ("tenants", "users", "user_tenant_roles", "invitations", "audit_entries"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")

    # tenants: tenant_admin reads/updates only its own row; manager sees all.
    op.execute(
        "CREATE POLICY app_tenants_select ON tenants FOR SELECT TO concierge_app "
        "USING (id = current_setting('app.tenant_id', true)::uuid);"
    )
    op.execute(
        "CREATE POLICY app_tenants_update ON tenants FOR UPDATE TO concierge_app "
        "USING (id = current_setting('app.tenant_id', true)::uuid) "
        "WITH CHECK (id = current_setting('app.tenant_id', true)::uuid);"
    )
    op.execute(
        "CREATE POLICY mgr_tenants_all ON tenants FOR ALL TO concierge_manager "
        "USING (true) WITH CHECK (true);"
    )

    # users: principal reads/writes only its own row; manager full.
    op.execute(
        "CREATE POLICY app_users_self ON users FOR ALL TO concierge_app "
        "USING (id = current_setting('app.user_id', true)::uuid) "
        "WITH CHECK (id = current_setting('app.user_id', true)::uuid);"
    )
    op.execute(
        "CREATE POLICY mgr_users_all ON users FOR ALL TO concierge_manager "
        "USING (true) WITH CHECK (true);"
    )

    # tenant-owned tables: filter by app.tenant_id; manager full (provisioning).
    for tbl in ("user_tenant_roles", "invitations"):
        op.execute(
            f"CREATE POLICY app_{tbl}_tenant ON {tbl} FOR ALL TO concierge_app "
            "USING (tenant_id = current_setting('app.tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);"
        )
        op.execute(
            f"CREATE POLICY mgr_{tbl}_all ON {tbl} FOR ALL TO concierge_manager "
            "USING (true) WITH CHECK (true);"
        )

    # audit_entries: manager-only (read + append). concierge_app gets no policy → denied.
    op.execute(
        "CREATE POLICY mgr_audit_select ON audit_entries FOR SELECT TO concierge_manager "
        "USING (true);"
    )
    op.execute(
        "CREATE POLICY mgr_audit_insert ON audit_entries FOR INSERT TO concierge_manager "
        "WITH CHECK (true);"
    )


def downgrade() -> None:
    for tbl in ("audit_entries", "invitations", "user_tenant_roles", "users", "tenants"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
    # Roles are intentionally left in place (may be shared across databases).
