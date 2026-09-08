"""add workspace include linkedin jobs

Revision ID: 7d4aa0b1d9f1
Revises: 52d7d367e9fb
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d4aa0b1d9f1"
down_revision = "52d7d367e9fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_preferences",
        sa.Column("include_linkedin_jobs", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    # Raw `COALESCE(col, 0)` is SQLite-only: Postgres refuses to match a
    # boolean against an integer literal. Let SQLAlchemy render the literal
    # for whichever dialect is running.
    prefs = sa.table(
        "workspace_preferences",
        sa.column("include_linkedin_jobs", sa.Boolean()),
    )
    op.execute(
        prefs.update()
        .where(prefs.c.include_linkedin_jobs.is_(None))
        .values(include_linkedin_jobs=False)
    )


def downgrade() -> None:
    op.drop_column("workspace_preferences", "include_linkedin_jobs")
