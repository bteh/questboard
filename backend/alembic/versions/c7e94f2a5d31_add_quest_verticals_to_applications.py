"""add quest verticals to applications

One board, one table: applications rows gain a vertical (career, camera,
study, lens, party; matches packages/ui/src/tokens.ts), event dates for dated
quests, a rolling-signup flag, a beginner-friendly flag, and a quest_json
detail column. server_default='career' backfills every existing row in place.

Revision ID: c7e94f2a5d31
Revises: f3c2a9d47b18
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7e94f2a5d31"
down_revision = "f3c2a9d47b18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("vertical", sa.String(length=20), nullable=False, server_default="career"),
    )
    op.add_column("applications", sa.Column("event_start", sa.DateTime(), nullable=True))
    op.add_column("applications", sa.Column("event_end", sa.DateTime(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("is_rolling", sa.Boolean(), nullable=True, server_default=sa.text("0")),
    )
    op.add_column(
        "applications",
        sa.Column("first_quest_ok", sa.Boolean(), nullable=True, server_default=sa.text("0")),
    )
    op.add_column(
        "applications",
        sa.Column("quest_json", sa.Text(), nullable=True, server_default=""),
    )
    op.create_index("ix_applications_vertical", "applications", ["vertical"], unique=False)
    op.create_index(
        "ix_applications_vertical_status", "applications", ["vertical", "status"], unique=False
    )
    op.create_index("ix_applications_event_start", "applications", ["event_start"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_applications_event_start", table_name="applications")
    op.drop_index("ix_applications_vertical_status", table_name="applications")
    op.drop_index("ix_applications_vertical", table_name="applications")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("quest_json")
        batch_op.drop_column("first_quest_ok")
        batch_op.drop_column("is_rolling")
        batch_op.drop_column("event_end")
        batch_op.drop_column("event_start")
        batch_op.drop_column("vertical")
