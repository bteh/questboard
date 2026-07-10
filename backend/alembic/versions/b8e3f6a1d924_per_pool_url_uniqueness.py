"""Per-pool URL uniqueness: the hosted shared board needs copies.

The global UNIQUE on applications.job_url assumed one pool. Hosted mode
has many: the shared quest pool (workspace_id NULL, the felt every
visitor reads) and per-workspace pools (career rows and clone-on-touch
copies of shared quest rows, which carry the SAME url as their original
by design). Uniqueness becomes:

- uq_applications_url_workspace: one row per URL inside a workspace
  (NULLs compare distinct, so this alone leaves the shared pool open);
- uq_applications_shared_url: partial unique index, one row per URL
  where workspace_id IS NULL (the shared/local pool keeps the old
  guarantee exactly).

SQLite cannot drop an inline column constraint, so the upgrade rebuilds
the table from a reflected copy with that constraint removed (batch
mode), then creates the two indexes.

Revision ID: b8e3f6a1d924
Revises: a9d4e7f2c815
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e3f6a1d924"
down_revision = "a9d4e7f2c815"
branch_labels = None
depends_on = None


def _reflected_without_url_unique(bind) -> sa.Table:
    meta = sa.MetaData()
    table = sa.Table("applications", meta, autoload_with=bind)
    doomed = [
        c
        for c in table.constraints
        if isinstance(c, sa.UniqueConstraint)
        and [col.name for col in c.columns] == ["job_url"]
    ]
    for c in doomed:
        table.constraints.discard(c)
    # the old implicit unique may also reflect as a unique index
    for ix in list(table.indexes):
        if ix.unique and [col.name for col in ix.columns] == ["job_url"]:
            table.indexes.discard(ix)
    return table


def upgrade() -> None:
    bind = op.get_bind()
    copy_from = _reflected_without_url_unique(bind)
    with op.batch_alter_table(
        "applications", copy_from=copy_from, recreate="always"
    ):
        pass
    op.create_index(
        "uq_applications_url_workspace",
        "applications",
        ["job_url", "workspace_id"],
        unique=True,
    )
    op.create_index(
        "uq_applications_shared_url",
        "applications",
        ["job_url"],
        unique=True,
        sqlite_where=sa.text("workspace_id IS NULL"),
        postgresql_where=sa.text("workspace_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_applications_shared_url", table_name="applications")
    op.drop_index("uq_applications_url_workspace", table_name="applications")
    # restoring the global unique would fail if copies exist; the partial
    # index was the old guarantee for the only pool the old world had, so
    # downgrade recreates exactly that.
    op.create_index(
        "uq_applications_job_url_global",
        "applications",
        ["job_url"],
        unique=True,
    )
