"""refile clinicaltrials rows from the study lane to body

A clinical trial rents your body (screenings, confinement, doses); focus
groups sell your opinion. The communities self-sorted the same way, so
the clinicaltrials source moved from the think lane (legacy vertical
"study") to the body kind. New rows already store vertical="body"; this
refiles the existing ones so one source never straddles two lanes.

Revision ID: f2c8d5a1b307
Revises: e5b2a8c4d719
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "f2c8d5a1b307"
down_revision = "e5b2a8c4d719"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE applications SET vertical = 'body' "
        "WHERE source = 'clinicaltrials' AND vertical = 'study'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE applications SET vertical = 'study' "
        "WHERE source = 'clinicaltrials' AND vertical = 'body'"
    )
