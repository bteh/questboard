"""add workspace target companies

Revision ID: 52d7d367e9fb
Revises: a8877b7c16ec
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "52d7d367e9fb"
down_revision = "a8877b7c16ec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_preferences",
        sa.Column("target_companies_json", sa.Text(), nullable=True, server_default="[]"),
    )
    op.execute(
        "UPDATE workspace_preferences "
        "SET target_companies_json = COALESCE(target_companies_json, '[]')"
    )


def downgrade() -> None:
    op.drop_column("workspace_preferences", "target_companies_json")
