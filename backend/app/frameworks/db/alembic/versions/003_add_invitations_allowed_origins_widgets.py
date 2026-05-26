"""add allowed_origins + widgets (invitations + users.role already in 001)

Revision ID: 003
Revises: 001
Create Date: 2026-05-26

Owner A (T116). Adds the allowed_origins and widgets tables with RLS + grants.
Per the migration reconciliation: invitations, audit_entries, the partial-unique
index on invitations, and users.role are all created in 001 and are NOT touched
here. down_revision is 001 (Owner B's 002 branches from 001 in parallel; a merge
revision reconciles heads when slices integrate).
"""

from __future__ import annotations

from alembic import op

revision = "003"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- allowed_origins ---
    op.execute(
        """
        CREATE TABLE allowed_origins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            origin TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_allowed_origin UNIQUE (tenant_id, origin)
        );
        """
    )
    # --- widgets (Owner D's entity; Owner A seeds the row at provisioning) ---
    op.execute(
        """
        CREATE TABLE widgets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
            public_id TEXT NOT NULL UNIQUE,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # --- grants ---
    op.execute("GRANT SELECT ON allowed_origins TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON allowed_origins TO concierge_manager;")
    op.execute("GRANT SELECT ON widgets TO concierge_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON widgets TO concierge_manager;")

    # --- RLS ---
    for tbl in ("allowed_origins", "widgets"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY app_{tbl}_tenant ON {tbl} FOR ALL TO concierge_app "
            "USING (tenant_id = current_setting('app.tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);"
        )
        op.execute(
            f"CREATE POLICY mgr_{tbl}_all ON {tbl} FOR ALL TO concierge_manager "
            "USING (true) WITH CHECK (true);"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS widgets CASCADE;")
    op.execute("DROP TABLE IF EXISTS allowed_origins CASCADE;")
