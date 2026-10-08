"""add watched_pages

Places I'd work at: careers pages a local user pastes so every quest refresh
reads them (ELOREA's Shopify careers page, Oct 8 2026). Local-only data; the
table exists on hosted so the schema stays one shape.

Revision ID: c3d8a6f1e2b9
Revises: b7e2d9c4a1f6
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d8a6f1e2b9"
down_revision = "b7e2d9c4a1f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watched_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_found", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )


def downgrade() -> None:
    op.drop_table("watched_pages")
