"""backfill applications schema drift

Eight ApplicationRecord columns (and one index) shipped in the model without
an alembic revision, so alembic-managed databases were missing them and the
first ORM SELECT naming them would fail. tests/test_alembic_model_parity.py
now asserts head == model, which surfaced this drift; this revision closes it.

Revision ID: f3c2a9d47b18
Revises: d1f7c3b9e240
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3c2a9d47b18"
down_revision = "d1f7c3b9e240"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("salary_source", sa.String(length=40), nullable=True))
    op.add_column("applications", sa.Column("score_evidence_json", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("evaluation_report_json", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("first_seen_run_id", sa.String(length=12), nullable=True))
    op.add_column("applications", sa.Column("user_feedback", sa.String(length=8), nullable=True))
    op.add_column("applications", sa.Column("feedback_notes", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("date_posted", sa.String(length=40), nullable=True))
    op.add_column("applications", sa.Column("date_confidence", sa.String(length=20), nullable=True))
    op.create_index(
        op.f("ix_applications_first_seen_run_id"),
        "applications",
        ["first_seen_run_id"],
        unique=False,
    )
    # Mirror src _migrate_db: rows that already carried a run id keep it as
    # their original-discovery run.
    op.execute(
        "UPDATE applications SET first_seen_run_id = search_run_id "
        "WHERE first_seen_run_id IS NULL AND search_run_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_applications_first_seen_run_id"), table_name="applications")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("date_confidence")
        batch_op.drop_column("date_posted")
        batch_op.drop_column("feedback_notes")
        batch_op.drop_column("user_feedback")
        batch_op.drop_column("first_seen_run_id")
        batch_op.drop_column("evaluation_report_json")
        batch_op.drop_column("score_evidence_json")
        batch_op.drop_column("salary_source")
