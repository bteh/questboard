"""add workspace target companies meta cache

Caches the resolved ATS board (ats/slug/job_count/careers_url) for each
watched company name in target_companies_json, so the desktop pull scrapes a
confirmed board directly (including exotic Workday / BILL tokens) instead of
re-discovering names every run.

Revision ID: c2e5b9a7f130
Revises: f4b8c1d2e6a0
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2e5b9a7f130"
down_revision = "f4b8c1d2e6a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_preferences",
        sa.Column("target_companies_meta_json", sa.Text(), nullable=True, server_default="[]"),
    )
    op.execute(
        "UPDATE workspace_preferences "
        "SET target_companies_meta_json = COALESCE(target_companies_meta_json, '[]')"
    )


def downgrade() -> None:
    op.drop_column("workspace_preferences", "target_companies_meta_json")
