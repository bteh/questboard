"""applications.remote_scope: the stated remote scope of a posting.

Remote does not mean remote-for-you: sources state "Remote, India" or
"Remote (UK Based only)" in the location text, and the place filter was
passing every remote row regardless. The scope ('us'/'worldwide'/'intl'/'')
is parsed in Python at save time from the location text; this migration
adds the column and backfills existing rows with the same parser, so a US
place filter stops passing international-only remote rows immediately.

Revision ID: a9e4c7d2b581
Revises: d7a3f1b9e642
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9e4c7d2b581"
down_revision = "d7a3f1b9e642"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("remote_scope", sa.String(length=12), server_default="", nullable=True),
    )
    op.create_index("ix_applications_remote_scope", "applications", ["remote_scope"])

    # Backfill with the same classifier save_application uses, so the filter
    # bites immediately instead of only after each row's next re-scrape.
    import sys
    from pathlib import Path

    src = str(Path(__file__).resolve().parents[3] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from job_finder.remote_scope import classify_remote_scope

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, location FROM applications "
            "WHERE location IS NOT NULL AND location != ''"
        )
    ).fetchall()
    for _id, _loc in rows:
        scope = classify_remote_scope(_loc)
        if scope:
            bind.execute(
                sa.text("UPDATE applications SET remote_scope = :s WHERE id = :i"),
                {"s": scope, "i": _id},
            )


def downgrade() -> None:
    op.drop_index("ix_applications_remote_scope", table_name="applications")
    op.drop_column("applications", "remote_scope")
