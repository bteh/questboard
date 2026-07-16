"""applications: internal hybrid ordering and explainable match metadata.

Revision ID: f4b8c1d2e6a0
Revises: e7a1c9d2f4b8
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4b8c1d2e6a0"
down_revision = "e7a1c9d2f4b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("rank_score", sa.Float(), nullable=True))
    op.add_column("applications", sa.Column("rank_source", sa.String(length=20), nullable=True))
    op.add_column("applications", sa.Column("match_bucket", sa.String(length=20), nullable=True))
    op.add_column("applications", sa.Column("match_reasons_json", sa.Text(), nullable=True))
    # Earlier code had no uniqueness guard. Collapse any duplicate counter
    # identities before enforcing the atomic upsert key.
    op.execute(
        "DELETE FROM usage_counters WHERE id NOT IN ("
        "SELECT MIN(id) FROM usage_counters GROUP BY workspace_id, metric, period_key"
        ")"
    )
    op.create_index(
        "ix_applications_workspace_rank",
        "applications",
        ["workspace_id", "vertical", "match_bucket", "rank_score"],
        unique=False,
    )
    op.create_index(
        "uq_usage_counters_workspace_metric_period",
        "usage_counters",
        ["workspace_id", "metric", "period_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_usage_counters_workspace_metric_period", table_name="usage_counters")
    op.drop_index("ix_applications_workspace_rank", table_name="applications")
    op.drop_column("applications", "match_reasons_json")
    op.drop_column("applications", "match_bucket")
    op.drop_column("applications", "rank_source")
    op.drop_column("applications", "rank_score")
