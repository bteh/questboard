"""add source-independent company taxonomy to applications

Revision ID: 91c4e8a7b2d6
Revises: 688237703e75
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "91c4e8a7b2d6"
down_revision = "688237703e75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("industry_tags", sa.Text(), nullable=True, server_default="[]"),
    )
    op.add_column(
        "applications",
        sa.Column("ecosystem_tags", sa.Text(), nullable=True, server_default="[]"),
    )
    # Authoritative crypto-universe sources can be backfilled without model
    # inference. Known-company and ecosystem enrichment continues through the
    # deterministic ingest classifier on subsequent refreshes.
    op.execute(
        "UPDATE applications SET industry_tags = '[\"crypto\"]' "
        "WHERE lower(coalesce(source, '')) IN "
        "('cryptojobslist', 'web3career', 'getro', 'consider')"
    )


def downgrade() -> None:
    op.drop_column("applications", "ecosystem_tags")
    op.drop_column("applications", "industry_tags")
