"""applications.agent_fit_json: the connected assistant's own fit verdict.

`set_work_fit` stores one JSON blob per row from the last headless run
({rank, verdict, why, caveat, run_id, at}), which is what the board and the
results panel read to show a ranking. The desktop path got the column from
`_migrate_db`, so the gap only showed on a hosted install: the first ORM
SELECT naming the column would fail against an alembic-built schema.

Revision ID: d4b7e2a9c561
Revises: c2e5b9a7f130
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4b7e2a9c561"
down_revision = "c2e5b9a7f130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("agent_fit_json", sa.Text(), server_default="", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "agent_fit_json")
