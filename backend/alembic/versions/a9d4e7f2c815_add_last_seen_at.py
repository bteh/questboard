"""add applications.last_seen_at for healthy-run-gated expiry

When a row's own source last CONFIRMED it. Fed by every re-scrape
(save_application), read by job_finder.expiry to tombstone rows the
source stopped listing (absence rule) or stopped confirming (staleness
rule). Backfilled from date_found: existing rows were last confirmed
when they were found, and NULL would exempt them from expiry forever.

Revision ID: a9d4e7f2c815
Revises: f2c8d5a1b307
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9d4e7f2c815"
down_revision = "f2c8d5a1b307"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.create_index("ix_applications_last_seen_at", "applications", ["last_seen_at"], unique=False)
    op.execute("UPDATE applications SET last_seen_at = date_found WHERE last_seen_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_applications_last_seen_at", table_name="applications")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("last_seen_at")
