"""add applications.date_updated

When the source last said it edited the posting (Greenhouse updated_at),
stored in the same calendar shape as date_posted. The board's freshness gate
reads it so an older posting the employer is still maintaining stays on the
board (Natera, Airbnb, Stripe, Oct 1 2026).

Revision ID: b7e2d9c4a1f6
Revises: e2b7c4d9a1f3
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e2d9c4a1f6"
down_revision = "e2b7c4d9a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("date_updated", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("date_updated")
