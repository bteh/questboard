"""add agent_role_proposals table

Stage 2a: the connected assistant proposes role changes instead of silently
rewriting saved preferences. propose_career_preferences writes only here;
decide_role_proposal is the sole path that ever patches workspace_preferences
from an accepted proposal, and only after re-checking base_roles_json against
the current saved roles for drift.

Revision ID: 688237703e75
Revises: d4b7e2a9c561
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "688237703e75"
down_revision = "d4b7e2a9c561"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_role_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("base_roles_json", sa.Text(), nullable=True),
        sa.Column("proposed_roles_json", sa.Text(), nullable=True),
        sa.Column("rationale", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_role_proposals_workspace_id"),
        "agent_role_proposals",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_role_proposals_workspace_id"), table_name="agent_role_proposals"
    )
    op.drop_table("agent_role_proposals")
