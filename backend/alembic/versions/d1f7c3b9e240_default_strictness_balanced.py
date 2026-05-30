"""normalize workspace match_strictness default to balanced

The previous migration (b3f1c8a5e210) added ``match_strictness`` with
``server_default='loose'`` and backfilled every existing row to 'loose'. As a
result, returning users searched with 'loose' strictness even though the
product default is now 'balanced' (pipeline ``_DEFAULT_STRICTNESS`` and the ORM
model default both say 'balanced'). ``_clean_strictness`` only rescues
empty/NULL values, so a literal 'loose' leaked straight through.

Every current 'loose'/NULL/'' value originated from that automatic backfill —
no UI to choose 'loose' existed before the column was introduced — so it is
safe to treat them all as the unintended default and reset to 'balanced'. An
explicit 'strict' (or 'balanced') choice is preserved.

New rows already get 'balanced' from the SQLAlchemy model default (applied on
INSERT), so the DB column server_default ('loose') is never reached in
practice; we leave it untouched to avoid a SQLite table rebuild.

Revision ID: d1f7c3b9e240
Revises: b3f1c8a5e210
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1f7c3b9e240"
down_revision = "b3f1c8a5e210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE workspace_preferences "
        "SET match_strictness = 'balanced' "
        "WHERE match_strictness IS NULL "
        "OR match_strictness = '' "
        "OR match_strictness = 'loose'"
    )


def downgrade() -> None:
    # No-op: reset rows are indistinguishable from rows that were 'loose' to
    # begin with, so there is nothing safe to revert.
    pass
