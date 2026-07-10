"""add scrape_runs run log

One row per source per fetch. The trust layer's foundation: a source that
silently breaks (0 rows after a site redesign, a soft block, a hang) is
indistinguishable from a quiet day without this record. Health verdicts
are computed from it in job_finder.source_health.

Revision ID: e5b2a8c4d719
Revises: c7e94f2a5d31
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5b2a8c4d719"
down_revision = "c7e94f2a5d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("vertical", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("rows_found", sa.Integer(), nullable=True),
        sa.Column("error_sample", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_id", "scrape_runs", ["id"], unique=False)
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"], unique=False)
    op.create_index("ix_scrape_runs_started_at", "scrape_runs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_started_at", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_source", table_name="scrape_runs")
    op.drop_index("ix_scrape_runs_id", table_name="scrape_runs")
    op.drop_table("scrape_runs")
