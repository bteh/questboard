"""drop schedules table

Removes the recurring-search Schedule feature. The table was unused in
practice; deleting it removes the embedded scheduler service and its
associated tech debt.

Revision ID: 9c1e4d6a2f10
Revises: 7d4aa0b1d9f1
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9c1e4d6a2f10"
down_revision: Union[str, Sequence[str], None] = "7d4aa0b1d9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "schedules" in inspector.get_table_names():
        op.drop_table("schedules")


def downgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("interval_hours", sa.Float(), nullable=True),
        sa.Column("mode", sa.String(length=50), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_jobs_found", sa.Integer(), nullable=True),
        sa.Column("last_run_new_jobs", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile"),
    )
