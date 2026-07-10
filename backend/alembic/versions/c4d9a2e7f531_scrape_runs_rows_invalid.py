"""scrape_runs.rows_invalid: the row contract's reject counter.

Rows the contract rejects (job_finder.row_contract) are dropped before
they land, but never silently: each run records how many, so selector
drift and over-tight contracts both surface in the same run log that
already carries volume and failures.

Revision ID: c4d9a2e7f531
Revises: b8e3f6a1d924
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d9a2e7f531"
down_revision = "b8e3f6a1d924"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("rows_invalid", sa.Integer(), nullable=True, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("scrape_runs", "rows_invalid")
