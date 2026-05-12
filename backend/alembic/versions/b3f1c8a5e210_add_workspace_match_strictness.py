"""add workspace match_strictness

Revision ID: b3f1c8a5e210
Revises: 9c1e4d6a2f10
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3f1c8a5e210"
down_revision = "9c1e4d6a2f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_preferences",
        sa.Column(
            "match_strictness",
            sa.String(length=16),
            nullable=True,
            server_default="loose",
        ),
    )
    op.execute(
        "UPDATE workspace_preferences "
        "SET match_strictness = COALESCE(match_strictness, 'loose')"
    )


def downgrade() -> None:
    op.drop_column("workspace_preferences", "match_strictness")
