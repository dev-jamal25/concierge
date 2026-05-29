"""merge cms/rag and widget schema heads

Revision ID: 004
Revises: 002, 003
Create Date: 2026-05-29

This merge revision reconciles the parallel Owner B and Owner A migration
heads so `alembic upgrade head` has a single target. It intentionally performs
no schema changes.
"""

from __future__ import annotations

revision = "004"
down_revision = ("002", "003")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
