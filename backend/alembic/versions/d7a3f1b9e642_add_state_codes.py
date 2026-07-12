"""applications.state_codes: the parsed US states a location names.

The place filter matches a typed state against this comma-wrapped field
(",AL,CT,VA,") instead of guessing states from prose in SQL, which a
review proved unsafe (a query-time tokenizer can't tell "office in
Austin, TX" from an availability list, nor keep "Virginia" from matching
"West Virginia"). Parsing happens in Python at save time; this migration
adds the column and backfills existing rows with the same parser.

Revision ID: d7a3f1b9e642
Revises: c4d9a2e7f531
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7a3f1b9e642"
down_revision = "c4d9a2e7f531"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("state_codes", sa.String(length=200), server_default="", nullable=True),
    )
    op.create_index("ix_applications_state_codes", "applications", ["state_codes"])

    # Backfill with the same parser save_application uses, so existing rows
    # are searchable immediately instead of only after their next re-scrape.
    import sys
    from pathlib import Path

    src = str(Path(__file__).resolve().parents[3] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from job_finder.us_states import state_codes_field

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, location FROM applications "
            "WHERE location IS NOT NULL AND location != ''"
        )
    ).fetchall()
    for row_id, location in rows:
        codes = state_codes_field(location)
        if codes:
            bind.execute(
                sa.text("UPDATE applications SET state_codes = :c WHERE id = :i"),
                {"c": codes, "i": row_id},
            )


def downgrade() -> None:
    op.drop_index("ix_applications_state_codes", table_name="applications")
    op.drop_column("applications", "state_codes")
