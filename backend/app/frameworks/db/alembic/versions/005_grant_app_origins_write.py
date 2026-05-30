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
