"""add proposed_keywords_json to agent_role_proposals

A proposal only ever carried roles, so a connected assistant could not fill
in search keywords from the resume. Accepting a proposal now merges these
into the saved keywords.

Revision ID: e2b7c4d9a1f3
Revises: 91c4e8a7b2d6
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2b7c4d9a1f3"
down_revision = "91c4e8a7b2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_role_proposals",
        sa.Column("proposed_keywords_json", sa.Text(), nullable=True, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agent_role_proposals", "proposed_keywords_json")
