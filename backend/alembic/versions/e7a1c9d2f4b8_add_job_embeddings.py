"""job_embeddings: dense vectors for semantic resume->job matching.

Ships dark. One row per application, written only by the batch indexer
(job_finder.embeddings_index) when the optional embedding model is installed,
and read by nothing until the hybrid ranker turns on. The vector is raw
little-endian float32 bytes; content_hash gates re-embedding on re-scrape.

Revision ID: e7a1c9d2f4b8
Revises: c9f3a6e1d582
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7a1c9d2f4b8"
down_revision = "c9f3a6e1d582"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_embeddings",
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("application_id"),
    )


def downgrade() -> None:
    op.drop_table("job_embeddings")
