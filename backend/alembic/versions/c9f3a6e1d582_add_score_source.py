"""applications.score_source: which scale scored the row.

The LLM scorer and the keyword fallback share one recommendation label
space but not one scale: keyword scoring runs structurally low, so its
STRONG_APPLY threshold is lenient (strong_apply * 0.65). Without
provenance the board sorts and badges both alike and a keyword guess
wears AI-grade confidence. This adds 'ai' | 'keyword' | NULL (unscored)
and backfills existing rows from the stored reasoning format: the
keyword/baseline scorer writes "Scoring (...)" reasoning, the LLM writes
prose, and a score with empty reasoning also came from the keyword scorer.

Revision ID: c9f3a6e1d582
Revises: a9e4c7d2b581
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9f3a6e1d582"
down_revision = "a9e4c7d2b581"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("score_source", sa.String(length=40), nullable=True),
    )

    # Same heuristic the startup backfill uses, so hosted rows carry honest
    # provenance immediately instead of only after their next re-score.
    op.execute(
        sa.text(
            "UPDATE applications SET score_source = CASE "
            "WHEN score_reasoning LIKE 'Scoring (%' THEN 'keyword' "
            "WHEN score_reasoning IS NOT NULL AND score_reasoning != '' THEN 'ai' "
            "ELSE 'keyword' END "
            "WHERE overall_score IS NOT NULL "
            "AND (score_source IS NULL OR score_source = '')"
        )
    )


def downgrade() -> None:
    op.drop_column("applications", "score_source")
